import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional


# ---------------------------------------------------------------------------
# Generieke, configureerbare check-functies
# ---------------------------------------------------------------------------

def check_keyword_forbidden(criterion: dict, section: dict, db_connection=None):
    """
    Controleert dat bepaalde woorden NIET voorkomen in de sectie.
    Keywords worden gelezen uit criterion['parameters'] als JSON: {"keywords": ["ik", "mij", ...]}.
    """
    raw = section.get('content', '')
    if not raw and db_connection and section.get('db_id'):
        raw = get_section_content_from_db(db_connection, section['db_id'])
    content = raw.lower() if isinstance(raw, str) else ''

    try:
        params = json.loads(criterion.get('parameters') or '{}')
    except (json.JSONDecodeError, TypeError):
        params = {}
    keywords = params.get('keywords', [])

    if not keywords:
        return None

    found = [kw for kw in keywords if re.search(r'\b' + re.escape(kw) + r'\b', content)]
    if not found:
        return {
            'criteria_id': criterion.get('id'),
            'criteria_name': criterion.get('name'),
            'section_id': section.get('db_id'),
            'section_name': section.get('name', ''),
            'status': 'ok',
            'message': f"Geen verboden woorden gevonden in '{section.get('name', '')}'.",
            'suggestion': '',
            'location': f"Sectie: {section.get('name', '')}",
            'confidence': 1.0,
            'color': '#84A98C',
            'offending_snippet': None,
            'check_type': 'keyword',
        }

    # Zoek de eerste REGEL (één Word-paragraaf) die een verboden woord bevat als snippet.
    # Gebruik regelsplitsing (niet zinssplitsing) zodat het snippet altijd overeenkomt
    # met precies één p.text in het Word-document.
    offending_snippet = None
    for line in re.split(r'\n+', raw.strip()):
        line = line.strip()
        if not line:
            continue
        if any(re.search(r'\b' + re.escape(kw) + r'\b', line, re.IGNORECASE) for kw in found):
            offending_snippet = line[:200]
            break

    return {
        'criteria_id': criterion.get('id'),
        'criteria_name': criterion.get('name'),
        'section_id': section.get('db_id'),
        'section_name': section.get('name', ''),
        'status': criterion.get('severity', 'warning'),
        'message': criterion.get('error_message') or
                   f"Verboden woorden gevonden in '{section.get('name', '')}': {', '.join(found)}.",
        'suggestion': criterion.get('fixed_feedback_text') or
                      f"Verwijder of vervang: {', '.join(found)}.",
        'location': f"Sectie: {section.get('name', '')}",
        'confidence': 0.9,
        'color': criterion.get('color', '#FFD700'),
        'offending_snippet': offending_snippet,
        'check_type': 'keyword',
    }


def check_keyword_required(criterion: dict, section: dict, db_connection=None):
    """
    Controleert dat bepaalde woorden WEL voorkomen in de sectie.
    Keywords worden gelezen uit criterion['parameters'] als JSON: {"keywords": ["output", "outcome", ...]}.
    """
    raw = section.get('content', '')
    if not raw and db_connection and section.get('db_id'):
        raw = get_section_content_from_db(db_connection, section['db_id'])
    content = raw.lower() if isinstance(raw, str) else ''

    try:
        params = json.loads(criterion.get('parameters') or '{}')
    except (json.JSONDecodeError, TypeError):
        params = {}
    keywords = params.get('keywords', [])

    if not keywords:
        return None

    missing = [kw for kw in keywords if not re.search(r'\b' + re.escape(kw) + r'\b', content)]
    if not missing:
        return {
            'criteria_id': criterion.get('id'),
            'criteria_name': criterion.get('name'),
            'section_id': section.get('db_id'),
            'section_name': section.get('name', ''),
            'status': 'ok',
            'message': f"Alle vereiste woorden gevonden in '{section.get('name', '')}'.",
            'suggestion': '',
            'location': f"Sectie: {section.get('name', '')}",
            'confidence': 1.0,
            'color': '#84A98C',
            'offending_snippet': None,
            'check_type': 'keyword',
        }

    # Gebruik de eerste REGEL van de sectie als snippet (één Word-paragraaf)
    offending_snippet = None
    for line in re.split(r'\n+', raw.strip()):
        line = line.strip()
        if len(line) >= 10:
            offending_snippet = line[:200]
            break

    return {
        'criteria_id': criterion.get('id'),
        'criteria_name': criterion.get('name'),
        'section_id': section.get('db_id'),
        'section_name': section.get('name', ''),
        'status': criterion.get('severity', 'warning'),
        'message': criterion.get('error_message') or
                   f"Vereiste woorden ontbreken in '{section.get('name', '')}': {', '.join(missing)}.",
        'suggestion': criterion.get('fixed_feedback_text') or
                      f"Voeg de volgende woorden toe: {', '.join(missing)}.",
        'location': f"Sectie: {section.get('name', '')}",
        'confidence': 0.85,
        'color': criterion.get('color', '#FFD700'),
        'offending_snippet': offending_snippet,
        'check_type': 'keyword',
    }


# ---------------------------------------------------------------------------
# Check-type Registry
# Elke entry: check_type_naam → check-functie
# Voeg hier nieuwe check-typen toe zonder generate_feedback() aan te passen.
# ---------------------------------------------------------------------------
# Wordt gevuld nadat alle functies gedefinieerd zijn (zie onderaan dit bestand).
CHECK_REGISTRY: dict = {}


def get_criterion_value(criterion, key: str, default=None):
    """Veilige toegang tot criterion kolommen met fallback naar default waarde.

    Behandelt zowel ontbrekende sleutels (KeyError) als SQL NULL-waarden (None)
    als 'niet aanwezig' en retourneert de default.
    """
    try:
        value = criterion[key]
    except (KeyError, IndexError):
        return default
    # SQL NULL → gebruik default (anders zou severity=NULL 'ok' tonen in de UI)
    if value is None:
        return default
    return value

def get_section_content_from_db(db_connection: sqlite3.Connection, section_id: int) -> str:
    """Haalt de content van een sectie op uit de database."""
    if not section_id:
        return ""
    
    cursor = db_connection.cursor()
    cursor.execute('SELECT content FROM sections WHERE id = ?', (section_id,))
    result = cursor.fetchone()
    
    if result and result[0]:
        return result[0]
    return ""

def get_section_content(section: dict, db_connection: sqlite3.Connection = None) -> str:
    """Haalt de content van een sectie op, eerst uit het geheugen, dan uit de database."""
    # Probeer eerst uit het geheugen
    content = section.get('content', '')
    if content:
        return content
    
    # Als geen content in geheugen en database verbinding beschikbaar, probeer database
    if db_connection and section.get('db_id'):
        return get_section_content_from_db(db_connection, section['db_id'])
    
    return ""

# --- Hulpfuncties voor Sectie Mappings en Toepasselijkheid ---

def get_criterion_section_mappings(db_connection: sqlite3.Connection, criterion_id: int):
    """
    Haalt mappings op uit de database voor een specifiek criterium (documenttype is nu onderdeel van het criterium).
    Let op: deze functie wordt idealiter al aangeroepen door get_criteria_for_document_type
    in db_utils.py om de criteria_list te verrijken voordat deze naar generate_feedback gaat.
    """
    cursor = db_connection.cursor()
    cursor.execute("""
        SELECT
            csm.section_id,
            s.identifier AS section_identifier,
            s.name AS section_name,
            csm.is_excluded,
            csm.weight
        FROM criteria_section_mappings csm
        JOIN sections s ON csm.section_id = s.id
        WHERE csm.criteria_id = ?
    """, (criterion_id,))
    # Gebruik dict(row) om SQLite Row objecten om te zetten naar normale dictionaries
    return [dict(row) for row in cursor.fetchall()]

def get_default_sections_for_criterion(criterion: dict):
    """Bepaalt standaard secties voor een criterium type als er geen specifieke mappings zijn."""
    # Deze default identifiers komen overeen met de 'identifier' kolom in de 'sections' tabel.
    defaults = {
        'tekstueel': ['inleiding', 'probleemstelling', 'doelstelling', 'methode', 'conclusie', 'aanbevelingen', 'samenvatting'],
        'structureel': ['inleiding', 'probleemstelling', 'doelstelling', 'onderzoeksvragen', 'methode', 'planning', 'conclusie', 'aanbevelingen', 'bijlagen', 'literatuur'],
        'inhoudelijk': ['probleemstelling', 'doelstelling', 'onderzoeksvragen', 'methode', 'resultaten', 'discussie', 'conclusie'],
        'referenties': ['literatuur']
    }
    # Valt terug op 'tekstueel' als rule_type onbekend is
    return defaults.get(get_criterion_value(criterion, 'rule_type', 'tekstueel'), [])

def get_applicable_sections(criterion: dict, all_recognized_sections: list, document_type_id: int, db_connection: sqlite3.Connection):
    """
    Bepaalt op welke secties een criterium van toepassing is, gebaseerd op de 'application_scope'
    en eventuele `section_mappings` die al in het criterium object aanwezig zijn.
    """
    applicable_sections = []

    # Haal mappings op uit het criterium object. db_utils.get_criteria_for_document_type
    # zou deze al moeten hebben toegevoegd.
    mappings = get_criterion_value(criterion, 'section_mappings', [])

    # Maak een dictionary van all_recognized_sections voor snelle lookup op identifier
    # Gebruik .get('found', False) om alleen gevonden secties mee te nemen
    sections_dict = {s['identifier']: s for s in all_recognized_sections if s.get('found', False)}

    if get_criterion_value(criterion, 'application_scope') == 'all':
        # Criterium geldt voor alle herkende secties (behalve de virtuele 'document' sectie).
        applicable_sections = [s for s in all_recognized_sections if s.get('found', False) and s['identifier'] != 'document']

    elif get_criterion_value(criterion, 'application_scope') == 'specific_sections':
        if mappings:
            mapped_identifiers = {m['section_identifier'] for m in mappings if not m['is_excluded']}
            for identifier in mapped_identifiers:
                if identifier in sections_dict:
                    applicable_sections.append(sections_dict[identifier])
        else:
            # Geen mappings: criterium niet uitvoeren.
            # (Vroeger: fallback op alle secties — onjuist gedrag.)
            applicable_sections = []

    elif get_criterion_value(criterion, 'application_scope') == 'exclude_sections':
        # Criterium geldt voor alle secties behalve uitgesloten.
        excluded_identifiers = {m['section_identifier'] for m in mappings if m['is_excluded']}
        applicable_sections = [s for s in all_recognized_sections if s['identifier'] not in excluded_identifiers and s.get('found', False) and s['identifier'] != 'document']
    
    # Filter uitgesloten secties als mappings aanwezig zijn (redundante check, maar veilig)
    if mappings:
        excluded_by_mapping = {m['section_identifier'] for m in mappings if m['is_excluded']}
        applicable_sections = [s for s in applicable_sections if s['identifier'] not in excluded_by_mapping]

    return applicable_sections

# --- Check Functies voor Specifieke Criteria ---

def check_word_count(criterion: dict, section: dict, db_connection: sqlite3.Connection = None):
    """Controleert woordtelling. Kan op sectie-niveau of alinea-niveau werken."""
    frequency_unit = get_criterion_value(criterion, 'frequency_unit')

    # Als het op alinea-niveau moet, roep de speciale functie aan
    if frequency_unit == 'paragraph':
        return check_paragraph_word_count(criterion, section, db_connection)

    # Anders: sectie-niveau (standaard)
    content = get_section_content(section, db_connection)
    word_count = len(re.findall(r'\b\w+\b', content)) # Robuustere telling

    # Haal het verwachte minimum en maximum aantal woorden uit de criterium metadata
    expected_min_words = get_criterion_value(criterion, 'expected_value_min')
    expected_max_words = get_criterion_value(criterion, 'expected_value_max')

    feedback = None

    if expected_min_words is not None and word_count < expected_min_words:
        feedback = {
            'criteria_id': get_criterion_value(criterion, 'id'),
            'criteria_name': get_criterion_value(criterion, 'name'),
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': get_criterion_value(criterion, 'severity', 'warning'),
            'message': get_criterion_value(criterion, 'error_message', f"Sectie '{section['name']}' heeft {word_count} woorden, minimaal {expected_min_words} vereist."),
            'suggestion': f"Breid de {section['name']} sectie uit. Huidig: {word_count} woorden, Vereist: {expected_min_words} woorden.",
            'location': f"Sectie: {section['name']}",
            'confidence': 0.8,
            'color': get_criterion_value(criterion, 'color', '#FFD700'),
            'check_type': 'structural',
        }
    elif expected_max_words is not None and word_count > expected_max_words:
        feedback = {
            'criteria_id': get_criterion_value(criterion, 'id'),
            'criteria_name': get_criterion_value(criterion, 'name'),
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': get_criterion_value(criterion, 'severity', 'warning'),
            'message': get_criterion_value(criterion, 'error_message', f"Sectie '{section['name']}' heeft {word_count} woorden, maximaal {expected_max_words} toegestaan."),
            'suggestion': f"Verkort de {section['name']} sectie. Huidig: {word_count} woorden, Maximaal: {expected_max_words} woorden.",
            'location': f"Sectie: {section['name']}",
            'confidence': 0.8,
            'color': get_criterion_value(criterion, 'color', '#FFD700'),
            'check_type': 'structural',
        }
    elif expected_min_words is not None or expected_max_words is not None:
        feedback = {
            'criteria_id': get_criterion_value(criterion, 'id'),
            'criteria_name': get_criterion_value(criterion, 'name'),
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': 'ok',
            'message': f"De woordtelling van '{section['name']}' is binnen de gestelde grenzen ({word_count} woorden).",
            'suggestion': "",
            'location': f"Sectie: {section['name']}",
            'confidence': 1.0,
            'color': '#84A98C',
            'check_type': 'structural',
        }

    return feedback


def check_paragraph_word_count(criterion: dict, section: dict, db_connection: sqlite3.Connection = None):
    """Controleert woordtelling van ELKE individuele alinea in een sectie.

    Alinea-detectie: Een alinea = een blok tekst tussen enters/newlines.
    Dit werkt direct op de document-structuur."""
    content = get_section_content(section, db_connection)

    # Normaliseer line breaks naar Unix-stijl
    content = content.replace('\r\n', '\n').replace('\r', '\n')

    def is_heading_like(text: str) -> bool:
        """Detecteer koptekst-achtige blokken die geen echte alinea zijn.
        Kenmerken: kort (<= 10 woorden) EN eindigt NIET op een zin-afsluitend leesteken."""
        words = re.findall(r'\b\w+\b', text)
        ends_with_sentence = bool(re.search(r'[.!?]$', text.strip()))
        return len(words) <= 10 and not ends_with_sentence

    # Bouw set van uitgesloten sub-sectie-namen op basis van de criterium-mappings.
    # Doel: als de parent-sectie (bijv. 'Inleiding') alle sub-secties bevat, moet de
    # alinea-check NIET kijken naar alinea's die vallen onder uitgesloten sub-secties
    # (bijv. 'Deelvragen'). Korte deelvragen zijn van nature kort en mogen niet worden
    # geflagd als de sectie 'deelvragen' is uitgesloten van dit criterium.
    excluded_sub_names: set[str] = set()
    for m in (get_criterion_value(criterion, 'section_mappings') or []):
        if m.get('is_excluded'):
            sn = (m.get('section_name') or '').lower()
            sn = re.sub(r'[\d.()\[\]]', '', sn).strip()
            if len(sn) >= 4:
                excluded_sub_names.add(sn)

    def _is_excluded_subheading(heading_line: str) -> bool:
        """True als deze heading het begin markeert van een uitgesloten sub-sectie."""
        cleaned = re.sub(r'^[\d.]+\s*', '', heading_line.lower()).strip()
        cleaned = re.sub(r'\s*\(.*?\)\s*', '', cleaned).strip()
        cleaned = re.sub(r'[\d.()\[\]]', '', cleaned).strip()
        for pat in excluded_sub_names:
            if re.search(r'\b' + re.escape(pat) + r'\b', cleaned):
                return True
        return False

    # document_parsing.py slaat echte alinea's op met \n\n als scheidingsteken
    # en koppen/lege regels met enkele \n — split hierop voor betrouwbare alinea-detectie
    raw_blocks = re.split(r'\n\n+', content)
    paragraphs = []
    in_excluded_sub = False  # Bijhouden of we in een uitgesloten sub-sectie zitten
    for block in raw_blocks:
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if not lines:
            continue

        # Detecteer sub-sectie-overgang via de eerste heading-achtige regel.
        # Een heading in het blok geeft aan dat we een nieuwe sub-sectie ingaan.
        if is_heading_like(lines[0]):
            if _is_excluded_subheading(lines[0]):
                in_excluded_sub = True
            else:
                # Alleen uitsluitingstatus resetten als:
                # - We NIET in een uitgesloten sub-sectie zitten (normaal geval), OF
                # - De koptekst een genummerd sectie-prefix heeft (bv. "1.4 Doelstelling"),
                #   wat een nieuwe sectie op hetzelfde of hoger niveau aangeeft.
                # Onnummerde sub-koppen (bv. "Deelvragen", "Hoofdvraag") binnen een
                # uitgesloten sectie resetten de status NIET — zij behoren tot de
                # uitgesloten sectie en mogen de vlag niet wissen.
                _has_section_num = bool(re.match(r'^\s*\d+[\.\s]', lines[0]))
                if not in_excluded_sub or _has_section_num:
                    in_excluded_sub = False

        # Sla alinea's in uitgesloten sub-secties over
        if in_excluded_sub:
            continue

        # document_parsing.py slaat sub-kopjes op met enkelvoudige \n, waardoor een
        # sub-kopje en de volgende alinea in hetzelfde blok terechtkomen na de \n\n+-split.
        # Fix: strip leading heading-achtige regels zodat de snippet altijd matcht
        # met de werkelijke Word-paragraaf p.text.
        start = 0
        while start < len(lines) - 1 and is_heading_like(lines[start]):
            start += 1
        content_lines = lines[start:]
        para_text = ' '.join(content_lines)
        # Sla heading-achtige blokken over (sectietitels, tussenkopjes zonder inhoud)
        if not is_heading_like(para_text):
            paragraphs.append(para_text)

    # Voeg index toe aan elke alinea
    paragraphs = [(p, idx) for idx, p in enumerate(paragraphs)]

    # Haal grenzen op
    expected_min_words = get_criterion_value(criterion, 'expected_value_min')
    expected_max_words = get_criterion_value(criterion, 'expected_value_max')

    feedback_list = []

    # Check ELKE alinea afzonderlijk
    for para_text, para_idx in paragraphs:
        word_count = len(re.findall(r'\b\w+\b', para_text))

        if expected_min_words is not None and word_count < expected_min_words:
            custom_msg = get_criterion_value(criterion, 'error_message')
            custom_fix = get_criterion_value(criterion, 'fixed_feedback_text')
            message    = custom_msg or "Deze alinea is te kort."
            suggestion = custom_fix or f"Breid deze alinea uit naar minimaal {int(expected_min_words)} woorden."
            feedback_list.append({
                'criteria_id':    get_criterion_value(criterion, 'id'),
                'criteria_name':  get_criterion_value(criterion, 'name'),
                'section_id':     section.get('db_id'),
                'section_name':   section['name'],
                'status':         get_criterion_value(criterion, 'severity', 'warning'),
                'message':        message,
                'suggestion':     suggestion,
                'location':       f"Sectie '{section['name']}'",
                'offending_snippet': para_text[:120],
                'confidence':     0.85,
                'color':          get_criterion_value(criterion, 'color', '#FFD700'),
                'check_type':     'structural',
            })
        elif expected_max_words is not None and word_count > expected_max_words:
            custom_msg = get_criterion_value(criterion, 'error_message')
            custom_fix = get_criterion_value(criterion, 'fixed_feedback_text')
            message    = custom_msg or "Deze alinea is te lang."
            suggestion = custom_fix or f"Verkort deze alinea naar maximaal {int(expected_max_words)} woorden."
            feedback_list.append({
                'criteria_id':    get_criterion_value(criterion, 'id'),
                'criteria_name':  get_criterion_value(criterion, 'name'),
                'section_id':     section.get('db_id'),
                'section_name':   section['name'],
                'status':         get_criterion_value(criterion, 'severity', 'warning'),
                'message':        message,
                'suggestion':     suggestion,
                'location':       f"Sectie '{section['name']}'",
                'offending_snippet': para_text[:120],
                'confidence':     0.85,
                'color':          get_criterion_value(criterion, 'color', '#FFD700'),
                'check_type':     'structural',
            })

    # Als alles OK is, retourneer één OK-feedback
    if not feedback_list and (expected_min_words is not None or expected_max_words is not None):
        return {
            'criteria_id': get_criterion_value(criterion, 'id'),
            'criteria_name': get_criterion_value(criterion, 'name'),
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': 'ok',
            'message': f"Alle alinea's in '{section['name']}' voldoen aan de woordtelling grenzen.",
            'suggestion': "",
            'location': f"Sectie: {section['name']}",
            'confidence': 1.0,
            'color': '#84A98C',
            'check_type': 'structural',
        }

    return feedback_list if feedback_list else None


# ---------------------------------------------------------------------------
# AI (LLM) beoordeling via Claude
# ---------------------------------------------------------------------------

# Taalrichtlijnen voor de AI: modern, helder Nederlands — geen archaïsch of Vlaams taalgebruik
_NL_TAALGEBRUIK = """
TAALGEBRUIK IN JE FEEDBACK — verplichte richtlijnen:
Schrijf helder, modern Nederlands zoals dat in het Nederlandse hoger onderwijs gangbaar is.
Vermijd de volgende woorden en vervang ze door het correcte alternatief:
• "imprecies" → gebruik "onnauwkeurig"
• "onsubstantieerd" → gebruik "onbeargumenteerd" of "zonder onderbouwing"
• "concretelijk" → gebruik "concreet"
• "citatie" → gebruik "citaat"
• "malplaatje" → gebruik "sjabloon" of "generieke opzet"
• "bevrijding", "bevrijd" in abstracte zin → vermijd; gebruik "ruimte bieden" of "de mogelijkheid geven"
• Vermijd Belgisch-Nederlandse uitdrukkingen en archaïsch formeel Nederlands
Schrijf verder:
• Actief en direct: "De student onderbouwt de keuze niet" in plaats van "Er ontbreekt onderbouwing"
• Juridisch jargon alleen waar dat inhoudelijk gepast en verwacht is
• Zelfstandige naamwoorden met het juiste bijvoeglijk naamwoord: "kritieke tekortkoming" (niet "kritiek tekortkoming")

COACHENDE TON — verplicht voor alle feedback:
Formuleer feedback altijd coachend en constructief. Benoem het probleem, leg uit waarom het ertoe doet voor de kwaliteit van het document, en geef richting zonder de student de volledige oplossing te geven. Vermijd harde, definitieve taal — gebruik formuleringen als "overweeg", "het zou sterker zijn als", "een aandachtspunt is". De student moet worden uitgenodigd tot reflectie, niet ontmoedigd.
""".strip()

# Standaard AI-stijldetectie prompt-blok (optioneel meegestuurd per criterium)
_AI_STYLE_PROMPT_NL = """
AI-STIJLDETECTIE — let naast de bovenstaande criteria ook op deze kenmerken die wijzen op AI-gegenereerde tekst:
• Overmatige opsommingen en bulletpoints waar doorlopende analytische tekst verwacht wordt
• Generieke openingszinnen ("In het huidige digitale tijdperk...", "Het is van cruciaal belang dat...")
• Symmetrische alineastructuur: elke alinea even lang, zelfde opbouw, geen variatie in toon
• Ontbreken van concrete voorbeelden, casuïstiek, namen of datums
• Samenvattende stijl zonder eigen analytisch standpunt of argumentatie
• Tautologieën en redundante formuleringen ("het is duidelijk dat dit duidelijk blijkt")
• Overmatig gebruik van Nederlandse formele verbindingswoorden: "tevens", "voorts", "derhalve", "in dit verband", "teneinde"
• Verwijzingen naar bronnen die niet concreet worden aangehaald of toegepast
• Ontbreken van fouten, inconsistenties of persoonlijk perspectief — de tekst klinkt te perfect
• Gebrek aan eigen juridische of vakinhoudelijke redenering: begrippen worden gedefinieerd maar niet toegepast
• Hyperbolisch en wervend taalgebruik: onnodig gebruik van versterkende woorden als "cruciaal", "essentieel",
  "fundamenteel", "baanbrekend", "ongekend", "van het grootste belang" — zonder dat de argumentatie of
  bronvermelding dat rechtvaardigt; de tekst klinkt als marketingcopy of websitetekst, niet als onderbouwd onderzoek
• Ontbreken van academische voorzichtigheid: geen gebruik van hedging zoals "lijkt erop dat", "suggereert",
  "mogelijk", "in bepaalde gevallen" — stellingen worden als absolute waarheid gepresenteerd zonder voorbehoud
• Het belang of de ernst van het onderwerp wordt groter voorgesteld dan het geleverde bewijs rechtvaardigt
""".strip()

_LLM_RESPONSE_SCHEMA = """
Geef je beoordeling UITSLUITEND als geldige JSON in dit formaat — geen tekst erbuiten:
{
  "oordeel": "onvoldoende" | "matig" | "voldoende" | "goed",
  "problemen": [
    {
      "citaat": "<exact geciteerde tekst uit de sectie, max 200 tekens>",
      "probleem": "<wat er mis is, concreet en specifiek>",
      "suggestie": "<concrete verbetering voor de student>"
    }
  ],
  "samenvatting": "<overkoepelende beoordeling in 1-2 zinnen>"
}
REGELS:
- Geef MAXIMAAL 3 problemen — alleen de zwaarst wegende inhoudelijke tekortkomingen.
- Beoordeel elke zin ALTIJD in de context van de volledige alinea. Als een zin onvolledig of vaag lijkt maar de volgende zin(nen) in dezelfde alinea dit direct concretiseren of uitwerken, vlag de eerste zin dan NIET — beoordeel de alinea als geheel.
- Vlag GEEN grammatica, spelling of woordkeuze — die vallen buiten deze beoordeling en worden apart gecheckt.
- Combineer vergelijkbare problemen in één item.
- Als de sectie voldoet aan de criteria, geef een leeg "problemen"-array en oordeel "voldoende" of "goed".
""".strip()

# Variant zonder suggesties — gebruikt wanneer show_suggestions=False voor het documenttype.
# Het weglaten van het "suggestie"-veld bespaart 30-60 output-tokens per probleem.
_LLM_RESPONSE_SCHEMA_NO_SUGGESTIONS = """
Geef je beoordeling UITSLUITEND als geldige JSON in dit formaat — geen tekst erbuiten:
{
  "oordeel": "onvoldoende" | "matig" | "voldoende" | "goed",
  "problemen": [
    {
      "citaat": "<exact geciteerde tekst uit de sectie, max 200 tekens>",
      "probleem": "<wat er mis is, concreet en specifiek>"
    }
  ],
  "samenvatting": "<overkoepelende beoordeling in 1-2 zinnen>"
}
REGELS:
- Geef MAXIMAAL 3 problemen — alleen de zwaarst wegende inhoudelijke tekortkomingen.
- Beoordeel elke zin ALTIJD in de context van de volledige alinea. Als een zin onvolledig of vaag lijkt maar de volgende zin(nen) in dezelfde alinea dit direct concretiseren of uitwerken, vlag de eerste zin dan NIET — beoordeel de alinea als geheel.
- Vlag GEEN grammatica, spelling of woordkeuze — die vallen buiten deze beoordeling en worden apart gecheckt.
- Combineer vergelijkbare problemen in één item.
- Als de sectie voldoet aan de criteria, geef een leeg "problemen"-array en oordeel "voldoende" of "goed".
- Formuleer GEEN verbeteradviezen of suggesties — het "suggestie"-veld bestaat niet in dit formaat.
""".strip()

_OORDEEL_TO_STATUS = {
    'onvoldoende': 'violation',
    'matig':       'warning',
    'voldoende':   'info',
    'goed':        'ok',
}


# ---------------------------------------------------------------------------
# Universele LLM-caller: ondersteunt Anthropic (claude-*) én Google Gemini (gemini-*)
# ---------------------------------------------------------------------------

def _extract_json(raw: str) -> dict:
    """
    Extraheer een JSON-object uit een LLM-respons op een robuuste manier.

    Handelt de volgende gevallen af:
    - Markdown code-fences (```json ... ```)
    - Denktekst / preambule vóór de JSON (Gemini thinking-modellen)
    - Naambule tekst na de JSON
    - Geneste accolades (vindt het buitenste complete object)

    Strategie: probeer van het meest rechtse '{' naar links — Gemini-denktekst
    staat vrijwel altijd VOOR de daadwerkelijke JSON-payload.
    """
    import logging as _l
    _log = _l.getLogger('docucheck')

    # Stap 1: verwijder markdown code-fences
    text = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
    text = re.sub(r'\s*```\s*$', '', text, flags=re.MULTILINE).strip()

    # Stap 2: directe parse (happy path — geen preambule)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Stap 3: vind alle complete JSON-objecten (links naar rechts).
    # Gebruik een string-aware nesting-teller zodat { in strings niet meetellen.
    # Geef voorkeur aan het grootste object dat de verwachte sleutels bevat
    # ('oordeel' + 'problemen'), anders het grootste geldige object.
    brace_positions = [i for i, c in enumerate(text) if c == '{']
    candidates = []
    for start in brace_positions:
        depth = 0
        end = -1
        in_string = False
        escape_next = False
        for j in range(start, len(text)):
            ch = text[j]
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end > start:
            candidate = text[start:end + 1]
            try:
                parsed = json.loads(candidate)
                candidates.append((end - start, parsed))  # (grootte, object)
            except json.JSONDecodeError:
                continue

    if candidates:
        # Geef voorkeur aan het grootste object met de verwachte sleutels
        schema_matches = [
            (size, obj) for size, obj in candidates
            if 'oordeel' in obj and 'problemen' in obj
        ]
        if schema_matches:
            return max(schema_matches, key=lambda x: x[0])[1]
        # Geen schema-match: geef het grootste geldige object terug
        return max(candidates, key=lambda x: x[0])[1]

    _log.warning(f"[JSON-PARSE] Geen geldig JSON-object gevonden. Eerste 400 tekens:\n{raw[:400]!r}")
    raise ValueError(f"Geen geldige JSON in LLM-response (lengte={len(raw)})")


def _call_llm(
    model: str,
    role_prompt: str,
    cached_text: str,
    uncached_text: str,
    max_tokens: int = 4096,
) -> dict:
    """
    Voert één LLM-call uit en geeft een uniform resultaat-dict terug:
      {
        'text': str,           # ruwe tekstoutput van het model
        'input_tokens': int,
        'output_tokens': int,
        'cache_created': int,  # altijd 0 voor Gemini
        'cache_read': int,     # altijd 0 voor Gemini
      }

    Routering:
      model begint met 'gemini-' → Google Generative AI SDK
      anders                     → Anthropic (met prompt-caching)

    Raises een Exception bij API-fouten zodat de aanroepende code retry kan doen.
    """
    if model.startswith('gemini'):
        import os
        import google.generativeai as _genai

        # API-sleutel ophalen (ook via .env als die nog niet geladen is)
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            try:
                from dotenv import load_dotenv
                load_dotenv()
                api_key = os.environ.get('GEMINI_API_KEY')
            except ImportError:
                pass
        if not api_key:
            raise RuntimeError('GEMINI_API_KEY niet gevonden in omgevingsvariabelen.')

        _genai.configure(api_key=api_key)
        gmodel = _genai.GenerativeModel(
            model_name=model,
            system_instruction=role_prompt,
        )
        # Gemini kent geen prompt-caching via de messages-API op deze manier;
        # we sturen cached_text en uncached_text gewoon aaneengesloten als één prompt.
        combined_prompt = cached_text + '\n\n' + uncached_text
        resp = gmodel.generate_content(
            combined_prompt,
            generation_config=_genai.GenerationConfig(max_output_tokens=max_tokens),
        )
        usage = resp.usage_metadata
        return {
            'text':          resp.text,
            'input_tokens':  getattr(usage, 'prompt_token_count', 0) or 0,
            'output_tokens': getattr(usage, 'candidates_token_count', 0) or 0,
            'cache_created': 0,
            'cache_read':    0,
        }
    else:
        # Anthropic — met prompt-caching
        import anthropic as _anthropic
        from config import Config
        client = _anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=role_prompt,
            messages=[{
                'role': 'user',
                'content': [
                    {
                        'type': 'text',
                        'text': cached_text,
                        'cache_control': {'type': 'ephemeral'},
                    },
                    {
                        'type': 'text',
                        'text': uncached_text,
                    },
                ],
            }],
            extra_headers={'anthropic-beta': 'prompt-caching-2024-07-31'},
        )
        u = resp.usage
        return {
            'text':          resp.content[0].text,
            'input_tokens':  u.input_tokens,
            'output_tokens': u.output_tokens,
            'cache_created': getattr(u, 'cache_creation_input_tokens', 0) or 0,
            'cache_read':    getattr(u, 'cache_read_input_tokens', 0) or 0,
        }


def check_llm_review(criterion: dict, section: dict, db_connection: sqlite3.Connection = None):
    """
    Inhoudelijke beoordeling van een sectie via Claude (Anthropic API).

    Parameters (in criterion['parameters'] JSON):
        llm_role_prompt     : str  - Persona/expertise die het LLM aanneemt
        llm_criteria_prompt : str  - Beoordelingscriteria in vrije tekst
        llm_check_ai_style  : bool - Voeg AI-stijldetectie toe aan de prompt

    Retourneert een lijst van feedback-items (één per gevonden probleem),
    of één 'ok'-item als de sectie voldoet.
    """
    # --- Parameters ophalen ---
    try:
        params = json.loads(criterion.get('parameters') or '{}')
    except (json.JSONDecodeError, TypeError):
        params = {}

    # Rolprompt: criterium-specifiek → document-type standaard (via section) → hardcoded fallback
    role_prompt = (
        params.get('llm_role_prompt', '').strip()
        or section.get('_default_role_prompt', '')
        or 'Je bent een kritische Nederlandse docent die studentenwerk beoordeelt.'
    )
    # Voeg datum en taalrichtlijnen toe aan het systeemprompt
    # De datum voorkomt dat de LLM jaartallen uit de tekst ten onrechte als "toekomst" beoordeelt
    from datetime import date as _date
    _d = _date.today()
    _maanden = ['januari','februari','maart','april','mei','juni',
                'juli','augustus','september','oktober','november','december']
    _vandaag_str = f"{_d.day} {_maanden[_d.month - 1]} {_d.year}"
    role_prompt = (
        role_prompt.rstrip()
        + f'\n\nVANDAAG IS HET: {_vandaag_str}. '
        + 'Beoordeel data en jaartallen in de tekst altijd ten opzichte van deze datum. '
        + 'Een datum in 2025 of 2026 is dus NIET per definitie een toekomstige datum.\n\n'
        + _NL_TAALGEBRUIK
    )
    criteria_prompt    = params.get('llm_criteria_prompt', '').strip()
    check_ai_style     = bool(params.get('llm_check_ai_style', False))
    llm_model          = params.get('llm_model', '').strip() or 'claude-haiku-4-5'

    # show_suggestions: ingesteld op documenttype-niveau; default True.
    # False → slankere response-schema zonder "suggestie"-veld → bespaart ~30-60 output-tokens per probleem.
    show_suggestions   = bool(section.get('_show_suggestions', True))
    _response_schema   = _LLM_RESPONSE_SCHEMA if show_suggestions else _LLM_RESPONSE_SCHEMA_NO_SUGGESTIONS

    # --- Sectie-inhoud ophalen ---
    content = get_section_content(section, db_connection).strip()
    if len(content) < 30:
        return None   # sectie te kort / leeg

    # --- Bepaal welke content gecacht wordt ---
    # Standaard AAN: het volledige document als gecachte context voor alle criteria-calls.
    # Eén cache-entry wordt gedeeld door ALLE criteria-calls voor dit document →
    # maximale tokenbesparing. Uitschakelen kan per criterium via llm_use_full_doc_context=false.
    use_full_doc = bool(params.get('llm_use_full_doc_context', True))
    full_doc_text = (section.get('_full_doc_text') or '').strip()

    if use_full_doc and full_doc_text:
        # GECACHT blok: volledig document — identiek voor alle calls op dit document.
        cached_text = (
            f"[VOLLEDIG DOCUMENT — CONTEXT]\n{full_doc_text[:40000]}\n"
            f"[/VOLLEDIG DOCUMENT]"
        )
        # ONGECACHT blok: de te beoordelen sectie + criteria + cross-sectie-instructie.
        # De sectie-content staat hier expliciet zodat de LLM weet wat hij beoordeelt.
        section_block = (
            f"[TE BEOORDELEN SECTIE: '{section['name']}']\n"
            f"{content[:8000]}\n"
            f"[/TE BEOORDELEN SECTIE]"
        )
        cross_section_note = (
            "LET OP — SCOPE: Beoordeel uitsluitend de bovenstaande sectie aan dit criterium. "
            "Het volledige document staat hierboven als context. "
            "Als een vereist element elders in het document aanwezig is (buiten de te beoordelen sectie), "
            "benoem dit expliciet (bijv. 'Dit staat in sectie X, niet hier') — "
            "maar markeer het NIET als 'ontbrekend' voor de huidige sectie."
        )
        uncached_blocks = [section_block]
        if criteria_prompt:
            uncached_blocks.append(f"BEOORDELINGSCRITERIA:\n{criteria_prompt}")
        if check_ai_style:
            uncached_blocks.append(_AI_STYLE_PROMPT_NL)
        uncached_blocks.append(cross_section_note)
        uncached_blocks.append(_response_schema)
        uncached_text = '\n\n'.join(uncached_blocks)
    else:
        # Fallback: alleen de sectie-content gecacht (geen volledige documentcontext).
        cached_text = (
            f"[TE BEOORDELEN SECTIE — '{section['name']}']\n{content[:20000]}\n"
            f"[/TE BEOORDELEN SECTIE]"
        )
        uncached_blocks = []
        if criteria_prompt:
            uncached_blocks.append(f"BEOORDELINGSCRITERIA:\n{criteria_prompt}")
        if check_ai_style:
            uncached_blocks.append(_AI_STYLE_PROMPT_NL)
        uncached_blocks.append(_response_schema)
        uncached_text = '\n\n'.join(uncached_blocks)

    # --- LLM-call met retry bij rate-limiting (ondersteunt Anthropic én Gemini) ---
    import time as _time
    import logging as _log
    _logger = _log.getLogger('docucheck')

    llm_result = None
    last_exc   = None
    for _attempt in range(3):
        try:
            llm_result = _call_llm(llm_model, role_prompt, cached_text, uncached_text, max_tokens=4096)
            break
        except Exception as exc:
            last_exc = exc
            exc_str  = str(exc)
            if '429' in exc_str or 'rate_limit' in exc_str.lower() or 'quota' in exc_str.lower():
                wait = 15 * (2 ** _attempt)   # 15s, 30s, 60s
                _logger.warning(
                    f"[RATE LIMIT] criterium={get_criterion_value(criterion, 'name')} | "
                    f"sectie={section['name']} | poging {_attempt + 1}/3 | wacht {wait}s | "
                    f"fout: {exc_str[:300]}"
                )
                _time.sleep(wait)
            else:
                _logger.warning(
                    f"[LLM FOUT] criterium={get_criterion_value(criterion, 'name')} | "
                    f"sectie={section['name']} | fout: {exc_str[:300]}"
                )
                break  # niet-rate-limit fout: meteen stoppen

    if llm_result is None:
        return {
            'criteria_id':   get_criterion_value(criterion, 'id'),
            'criteria_name': get_criterion_value(criterion, 'name'),
            'section_id':    section.get('db_id'),
            'section_name':  section['name'],
            'status':        'warning',
            'message':       f"LLM-beoordeling mislukt: {last_exc}",
            'suggestion':    'Controleer de API-sleutel (ANTHROPIC_API_KEY / GEMINI_API_KEY).',
            'location':      f"Sectie: {section['name']}",
            'confidence':    0.0,
            'color':         '#F9C74F',
            'check_type':    'llm_review',
        }

    raw           = llm_result['text'].strip()
    cache_read    = llm_result['cache_read']
    cache_created = llm_result['cache_created']
    _logger.info(
        f"TOKEN-GEBRUIK | criterium={get_criterion_value(criterion, 'name')} | "
        f"model={llm_model} | sectie={section['name']} | "
        f"input={llm_result['input_tokens']} | output={llm_result['output_tokens']} | "
        f"cache_created={cache_created} | cache_read={cache_read} | "
        f"totaal={llm_result['input_tokens'] + llm_result['output_tokens']}"
    )

    # --- JSON-antwoord parsen ---
    try:
        result = _extract_json(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        import logging as _log2
        _log2.getLogger('docucheck').warning(
            f"[JSON-PARSE] criterium={get_criterion_value(criterion, 'name')} | "
            f"sectie={section['name']} | fout={exc} | "
            f"raw={raw!r}"
        )
        return {
            'criteria_id':   get_criterion_value(criterion, 'id'),
            'criteria_name': get_criterion_value(criterion, 'name'),
            'section_id':    section.get('db_id'),
            'section_name':  section['name'],
            'status':        'warning',
            'message':       'LLM-antwoord kon niet worden verwerkt (geen geldige JSON).',
            'suggestion':    f"Ruwe LLM-output: {raw[:300]}",
            'location':      f"Sectie: {section['name']}",
            'confidence':    0.0,
            'color':         '#F9C74F',
            'check_type':    'llm_review',
        }

    oordeel   = result.get('oordeel', 'matig').lower()
    problemen = result.get('problemen', [])
    samen     = result.get('samenvatting', '')

    # Status op basis van oordeel; respecteer criterion.severity als override
    base_status = _OORDEEL_TO_STATUS.get(oordeel, 'warning')
    crit_severity = get_criterion_value(criterion, 'severity')
    # Alleen overschrijven als de criterium-severity 'warning' is (standaard) of hoger
    if crit_severity in ('violation', 'error') and base_status == 'warning':
        base_status = crit_severity

    crit_id    = get_criterion_value(criterion, 'id')
    crit_name  = get_criterion_value(criterion, 'name')
    crit_color = get_criterion_value(criterion, 'color', '#4895EF')
    sec_id     = section.get('db_id')
    sec_name   = section['name']

    # --- Geen problemen gevonden ---
    if not problemen or base_status == 'ok':
        return {
            'criteria_id':   crit_id,
            'criteria_name': crit_name,
            'section_id':    sec_id,
            'section_name':  sec_name,
            'status':        'ok',
            'message':       samen or f"Sectie '{sec_name}' voldoet aan de beoordelingscriteria.",
            'suggestion':    '',
            'location':      f"Sectie: {sec_name}",
            'confidence':    0.95,
            'color':         '#84A98C',
            'check_type':    'llm_review',
        }

    # --- Eén feedback-item per probleem → elk krijgt zijn eigen Word-comment ---
    # Begrens op max 5 problemen (de LLM kan het schema negeren)
    problemen = problemen[:5]
    items = []
    for p in problemen:
        citaat    = (p.get('citaat') or '').strip()[:200]
        probleem  = (p.get('probleem') or '').strip()
        suggestie = (p.get('suggestie') or '').strip()
        items.append({
            'criteria_id':      crit_id,
            'criteria_name':    crit_name,
            'section_id':       sec_id,
            'section_name':     sec_name,
            'status':           base_status,
            'message':          probleem or samen,
            'suggestion':       suggestie,
            'location':         f"Sectie: {sec_name}",
            'confidence':       0.85,
            'color':            crit_color,
            'offending_snippet': citaat if len(citaat) >= 5 else None,
            'check_type':       'llm_review',
        })

    return items


def check_smart_formulation(criterion: dict, section: dict, db_connection: sqlite3.Connection = None):
    """Controleert of tekst SMART geformuleerd is."""
    content = get_section_content(section, db_connection).lower()

    smart_indicators = {
        'specifiek': ['specifiek', 'concreet', 'duidelijk', 'precies', 'afgebakend'],
        'meetbaar': ['meetbaar', 'kwantificeerbaar', 'cijfers', 'percentage', 'aantal', 'volume', 'hoeveelheid'],
        'acceptabel': ['acceptabel', 'haalbaar', 'relevant', 'bereikbaar', 'akkoord'],
        'realistisch': ['realistisch', 'haalbaar', 'mogelijk', 'uitvoerbaar'],
        'tijdgebonden': ['deadline', 'datum', 'week', 'maand', 'jaar', 'tijd', 'binnen']
    }

    found_aspects = []
    missing_aspects = []

    for aspect, indicators in smart_indicators.items():
        if any(indicator in content for indicator in indicators):
            found_aspects.append(aspect)
        else:
            missing_aspects.append(aspect)

    # Eerste zin als snippet voor commentplaatsing
    raw_smart = get_section_content(section, db_connection)
    smart_sentences = re.split(r'(?<=[.!?])\s+', raw_smart.strip())
    smart_snippet = smart_sentences[0].strip()[:200] if smart_sentences else None

    if len(missing_aspects) > 2:
        return {
            'criteria_id': get_criterion_value(criterion, 'id'),
            'criteria_name': get_criterion_value(criterion, 'name'),
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': get_criterion_value(criterion, 'severity', 'violation'),
            'message': get_criterion_value(criterion, 'error_message', f"De {section['name'].lower()} mist belangrijke SMART aspecten: {', '.join(missing_aspects)}"),
            'suggestion': f"Zorg dat de {section['name'].lower()} Specifiek, Meetbaar, Acceptabel, Realistisch en Tijdgebonden is. Ontbrekende: {', '.join(missing_aspects)}.",
            'location': f"Sectie: {section['name']}",
            'confidence': 0.9,
            'color': get_criterion_value(criterion, 'color', '#FF0000'),
            'offending_snippet': smart_snippet,
            'check_type': 'structural',
        }
    elif len(missing_aspects) > 0:
        return {
            'criteria_id': get_criterion_value(criterion, 'id'),
            'criteria_name': get_criterion_value(criterion, 'name'),
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': get_criterion_value(criterion, 'severity', 'warning'),
            'message': get_criterion_value(criterion, 'error_message', f"De {section['name'].lower()} zou kunnen verbeteren op: {', '.join(missing_aspects)}"),
            'suggestion': f"Overweeg om de {section['name'].lower()} completer te maken met betrekking tot: {', '.join(missing_aspects)}.",
            'location': f"Sectie: {section['name']}",
            'confidence': 0.6,
            'color': get_criterion_value(criterion, 'color', '#FFD700'),
            'offending_snippet': smart_snippet,
            'check_type': 'structural',
        }
    else:
        return {
            'criteria_id': get_criterion_value(criterion, 'id'),
            'criteria_name': get_criterion_value(criterion, 'name'),
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': 'ok',
            'message': f"De {section['name'].lower()} lijkt SMART geformuleerd te zijn.",
            'suggestion': "",
            'location': f"Sectie: {section['name']}",
            'confidence': 1.0,
            'color': '#84A98C',
            'check_type': 'structural',
        }

def check_textual_criterion(criterion: dict, section: dict, db_connection: sqlite3.Connection = None):
    """Controleert tekstuele criteria (woordgebruik, zinsbouw, etc.)"""
    feedback = None

    raw_content = get_section_content(section, db_connection)
    content = ""

    # Robuuste content conversie
    if isinstance(raw_content, list):
        content = " ".join(raw_content).lower()
    elif isinstance(raw_content, str):
        content = raw_content.lower()
    elif isinstance(raw_content, dict):
        try:
            content = json.dumps(raw_content, ensure_ascii=False).lower()
        except TypeError:
            content = str(raw_content).lower()
    else:
        content = str(raw_content).lower()

    # Specifieke check voor 'Persoonlijk taalgebruik'
    if 'persoonlijk taalgebruik' in get_criterion_value(criterion, 'name').lower() or \
       (get_criterion_value(criterion, 'rule_type') == 'tekstueel' and 'persoonlijk' in get_criterion_value(criterion, 'description', '').lower()):
        personal_pronouns = ['ik', 'mij', 'mijn', 'wij', 'ons', 'onze'] # Kan eventueel uit criterium parameters komen

        found_personal_pronouns = [p for p in personal_pronouns if re.search(r'\b' + re.escape(p) + r'\b', content)] # Gebruik regex voor hele woorden
        if found_personal_pronouns:
            # Zoek de eerste zin (uit de originele tekst) die een voornaamwoord bevat
            raw_content = get_section_content(section, db_connection)
            offending_snippet = None
            sentences = re.split(r'(?<=[.!?])\s+', raw_content.strip())
            for sent in sentences:
                if any(re.search(r'\b' + re.escape(p) + r'\b', sent, re.IGNORECASE)
                       for p in found_personal_pronouns):
                    offending_snippet = sent.strip()[:200]
                    break

            feedback = {
                'criteria_id': get_criterion_value(criterion, 'id'),
                'criteria_name': get_criterion_value(criterion, 'name'),
                'section_id': section.get('db_id'),
                'section_name': section['name'],
                'status': get_criterion_value(criterion, 'severity', 'warning'),
                'message': get_criterion_value(criterion, 'error_message', f"Persoonlijk taalgebruik gevonden in '{section['name']}': {', '.join(found_personal_pronouns)}."),
                'suggestion': get_criterion_value(criterion, 'fixed_feedback_text', "Hanteer een zakelijke schrijfstijl zonder persoonlijke voornaamwoorden."),
                'location': f"Sectie: {section['name']}",
                'confidence': 0.7,
                'color': get_criterion_value(criterion, 'color', '#FFD700'),
                'offending_snippet': offending_snippet,
                'check_type': 'textual',
            }
        else:
            # GEEN persoonlijk taalgebruik gevonden = OK status
            feedback = {
                'criteria_id': get_criterion_value(criterion, 'id'),
                'criteria_name': get_criterion_value(criterion, 'name'),
                'section_id': section.get('db_id'),
                'section_name': section['name'],
                'status': 'ok',
                'message': f"Geen persoonlijk taalgebruik gevonden in '{section['name']}'.",
                'suggestion': "",
                'location': f"Sectie: {section['name']}",
                'confidence': 1.0,
                'color': '#84A98C',
                'offending_snippet': None,
                'check_type': 'textual',
            }
    
    # Voeg hier meer 'elif' blokken toe voor andere specifieke tekstuele criteria
    # die je kunt identificeren op basis van 'get_criterion_value(criterion, 'name')' of een ander veld.

    return feedback

def check_structural_criterion(criterion: dict, section: dict, db_connection: sqlite3.Connection = None):
    """
    Controleert structurele criteria (lengte, opbouw, volgorde, kopjes, paragrafen)
    die op EEN specifieke sectie van toepassing zijn.
    """
    criterion_name = get_criterion_value(criterion, 'name').lower()

    # Woordtelling criteria (kan ook structureel zijn, als de structuur door lengte wordt beïnvloed)
    if 'woorden' in criterion_name or 'word' in criterion_name or 'lengte' in criterion_name:
        return check_word_count(criterion, section, db_connection)

    # Paragraaf criteria
    if 'paragraaf' in criterion_name or 'alinea' in criterion_name or 'paragrafen' in criterion_name:
        return check_paragraph_structure(criterion, section, db_connection)

    # Deelvragen structuur — controleer zinsopbouw (twee hoofdzinnen in één deelvraag)
    # MOET vóór de generieke 'structuur' check staan!
    if 'deelvra' in criterion_name:
        return check_deelvragen_structure(criterion, section, db_connection)

    # Kopjes/structuur criteria binnen een sectie
    if 'kopje' in criterion_name or 'structuur' in criterion_name or 'headings' in criterion_name:
        return check_heading_structure(criterion, section, db_connection)
    
    # Criteria voor sectie aanwezigheid (is_required in sections tabel)
    if get_criterion_value(criterion, 'rule_type') == 'structureel' and 'aanwezigheid' in criterion_name:
        # Dit is een check of de sectie zelf gevonden is.
        if section['identifier'] != 'document' and not section.get('found', False) and section.get('is_required', False): # 'is_required' komt uit de sectie definitie
            return {
                'criteria_id': get_criterion_value(criterion, 'id'),
                'criteria_name': get_criterion_value(criterion, 'name'),
                'section_id': section.get('db_id'),
                'section_name': section['name'],
                'status': get_criterion_value(criterion, 'severity', 'violation'),
                'message': get_criterion_value(criterion, 'error_message', f"De verplichte sectie '{section['name']}' is niet gevonden in het document."),
                'suggestion': get_criterion_value(criterion, 'fixed_feedback_text', f"Zorg ervoor dat de sectie '{section['name']}' duidelijk aanwezig is in het document."),
                'location': 'Document',
                'confidence': 1.0,
                'color': get_criterion_value(criterion, 'color', '#FF0000'),
                'check_type': 'structural',
            }
        elif section['identifier'] != 'document' and section.get('found', False) and section.get('is_required', False):
            return {
                'criteria_id': get_criterion_value(criterion, 'id'),
                'criteria_name': get_criterion_value(criterion, 'name'),
                'section_id': section.get('db_id'),
                'section_name': section['name'],
                'status': 'ok',
                'message': f"De verplichte sectie '{section['name']}' is gevonden.",
                'suggestion': "",
                'location': f"Sectie: {section['name']}",
                'confidence': 1.0,
                'color': '#84A98C',
                'check_type': 'structural',
            }

    return None

def check_paragraph_structure(criterion: dict, section: dict, db_connection: sqlite3.Connection = None):
    """Controleert paragraaf structuur van een sectie."""
    content = get_section_content(section, db_connection)
    # Gebruik een robuustere methode om paragrafen te splitsen
    paragraphs = re.split(r'\n\s*\n+', content) # Split op 2+ nieuwe regels met optionele spaties ertussen
    paragraphs = [p.strip() for p in paragraphs if p.strip()] # Verwijder lege paragrafen
    paragraph_count = len(paragraphs)

    # Haal min/max paragrafen op uit criterium parameters
    expected_min_paragraphs = get_criterion_value(criterion, 'expected_value_min')
    expected_max_paragraphs = get_criterion_value(criterion, 'expected_value_max')

    # Valideer en converteer naar int indien nodig
    if isinstance(expected_min_paragraphs, (int, float)):
        expected_min_paragraphs = int(expected_min_paragraphs)
    else:
        expected_min_paragraphs = None # Zorg dat het een numerieke waarde is of None

    if isinstance(expected_max_paragraphs, (int, float)):
        expected_max_paragraphs = int(expected_max_paragraphs)
    else:
        expected_max_paragraphs = None # Zorg dat het een numerieke waarde is of None

    feedback = None

    if expected_min_paragraphs is not None and paragraph_count < expected_min_paragraphs:
        feedback = {
            'criteria_id': get_criterion_value(criterion, 'id'),
            'criteria_name': get_criterion_value(criterion, 'name'),
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': get_criterion_value(criterion, 'severity', 'violation'),
            'message': get_criterion_value(criterion, 'error_message', f"Sectie '{section['name']}' heeft {paragraph_count} paragrafen, minimaal {expected_min_paragraphs} vereist."),
            'suggestion': get_criterion_value(criterion, 'fixed_feedback_text', f"Voeg meer paragrafen toe aan de '{section['name']}' sectie voor betere structuur. Huidig: {paragraph_count}, Vereist: {expected_min_paragraphs}."),
            'confidence': 0.9,
            'color': get_criterion_value(criterion, 'color', '#FF0000'),
            'check_type': 'structural',
        }
    elif expected_max_paragraphs is not None and paragraph_count > expected_max_paragraphs:
        feedback = {
            'criteria_id': get_criterion_value(criterion, 'id'),
            'criteria_name': get_criterion_value(criterion, 'name'),
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': get_criterion_value(criterion, 'severity', 'violation'),
            'message': get_criterion_value(criterion, 'error_message', f"Sectie '{section['name']}' heeft {paragraph_count} paragrafen, maximaal {expected_max_paragraphs} toegestaan."),
            'suggestion': get_criterion_value(criterion, 'fixed_feedback_text', f"Verkort het aantal paragrafen in de '{section['name']}' sectie. Huidig: {paragraph_count}, Maximaal: {expected_max_paragraphs}."),
            'confidence': 0.9,
            'color': get_criterion_value(criterion, 'color', '#FF0000'),
            'check_type': 'structural',
        }
    elif expected_min_paragraphs is not None or expected_max_paragraphs is not None:
        feedback = {
            'criteria_id': get_criterion_value(criterion, 'id'),
            'criteria_name': get_criterion_value(criterion, 'name'),
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': 'ok',
            'message': f"Het aantal paragrafen in '{section['name']}' is binnen de gestelde grenzen ({paragraph_count} paragrafen).",
            'suggestion': "",
            'location': f"Sectie: {section['name']}",
            'confidence': 1.0,
            'color': '#84A98C',
            'check_type': 'structural',
        }
    return feedback


def check_deelvragen_structure(criterion: dict, section: dict, db_connection: sqlite3.Connection = None):
    """
    Controleert de structuur van deelvragen.
    Detecteert deelvragen die twee volledige hoofdzinnen bevatten gescheiden door 'en'.
    Elke deelvraag moet één duidelijke vraag bevatten, niet twee samengevoegde vragen.
    """
    content = get_section_content(section, db_connection)
    if not content:
        return None

    # --- Stap 1: Splits de tekst in afzonderlijke deelvragen ---
    # Zoek genummerde items: "1.", "2.", "1)", "a.", etc. of regels die beginnen met een nummer/letter
    deelvragen = []
    # Patroon: nummer gevolgd door . of ) en dan tekst, of bullet-achtige patronen
    # We splitsen op patronen als "1.", "2.", "3." etc. aan het begin van een regel of na een newline
    parts = re.split(r'(?:^|\n)\s*(\d+[\.\)]\s*)', content)

    if len(parts) > 1:
        # Recombineer: parts[0] is tekst voor eerste nummer, dan afwisselend nummer en tekst
        for i in range(1, len(parts), 2):
            nummer = parts[i].strip()
            tekst = parts[i + 1].strip() if i + 1 < len(parts) else ''
            if tekst:
                deelvragen.append({'nummer': nummer, 'tekst': tekst})
    else:
        # Geen genummerde items — probeer bullet-punten (- of •) aan het begin van een regel
        bullet_parts = re.split(r'\n+\s*[-•*]\s*[\t ]*', content)
        if len(bullet_parts) > 1:
            # bullet_parts[0] is intro-tekst (hoofdvraag + label) — overslaan
            for i, tekst in enumerate(bullet_parts[1:], 1):
                tekst = tekst.strip()
                if len(tekst) >= 10:
                    deelvragen.append({'nummer': str(i), 'tekst': tekst})
        else:
            # Geen bullets gevonden — probeer zinnen als individuele deelvragen
            zinnen = re.split(r'(?<=[.!?])\s+', content.strip())
            for i, zin in enumerate(zinnen):
                if len(zin.strip()) >= 10:
                    deelvragen.append({'nummer': str(i + 1), 'tekst': zin.strip()})

    if not deelvragen:
        return None

    # --- Stap 2: Controleer elke deelvraag op twee samengestelde vragen ---
    # Een samengestelde deelvraag bevat "en" dat twee volledige deelvragen verbindt.
    # Betrouwbare heuristiek voor deelvragen: beide delen moeten een vraagwoord bevatten.
    # "de AVG en ISO 27001" → deel na heeft GEEN vraagwoord → geen samengestelde vraag
    # "hoeverre... en hoe kan..." → BEIDE delen hebben een vraagwoord → samengestelde vraag

    dutch_question_words = {
        'wie', 'wat', 'waar', 'wanneer', 'waarom', 'hoe', 'welk', 'welke',
        'hoeveel', 'waarvoor', 'waarbij', 'waarmee', 'waaraan', 'waartoe',
        'waaruit', 'waarover', 'hoeverre', 'waardoor', 'waarheen', 'waarop',
        'waarna', 'waartegen', 'welks', 'welker',
    }

    def _bevat_vraagwoord(tekst: str) -> bool:
        """
        Controleert of tekst een echte VRAAGZIN is:
        het vraagwoord moet in de eerste 5 woorden staan.
        Zo wordt 'waarbij cryptovaluta wordt gebruikt' (betrekkelijk voornaamwoord
        midden in een zin) NIET als vraagzin herkend, maar
        'Welke verplichtingen...' of 'Hoe verhouden...' WEL.
        """
        woorden = re.findall(r'\b\w+\b', tekst.lower())
        if not woorden:
            return False
        eerste_vijf = set(woorden[:5])
        return bool(eerste_vijf & dutch_question_words)

    problematic_deelvragen = []

    for dv in deelvragen:
        tekst = dv['tekst']
        # Verwijder vraagtekeneindigingen en extra whitespace
        tekst_clean = tekst.strip().rstrip('?').strip()

        # Zoek " en " als potentiële scheider van twee hoofdzinnen
        # We willen niet matchen op "en" in samenstellingen of korte opsommingen
        en_positions = [m.start() for m in re.finditer(r'\s+en\s+', tekst_clean, re.IGNORECASE)]

        for pos in en_positions:
            deel_voor = tekst_clean[:pos].strip()
            deel_na = tekst_clean[pos:].strip()
            # Verwijder het "en" van het begin van deel_na
            deel_na = re.sub(r'^en\s+', '', deel_na, flags=re.IGNORECASE).strip()

            woorden_voor = len(re.findall(r'\b\w+\b', deel_voor))
            woorden_na = len(re.findall(r'\b\w+\b', deel_na))

            # Beide delen moeten substantieel zijn (>= 4 woorden) én elk een vraagwoord bevatten.
            # Dit voorkomt false positives zoals "de AVG en ISO 27001" (geen vraagwoord in deel na).
            if woorden_voor >= 4 and woorden_na >= 4:
                if _bevat_vraagwoord(deel_voor) and _bevat_vraagwoord(deel_na):
                    problematic_deelvragen.append({
                        'nummer': dv['nummer'],
                        'tekst': tekst.strip(),
                        'deel_voor': deel_voor,
                        'deel_na': deel_na,
                    })
                    break  # Eén probleem per deelvraag is voldoende

    if problematic_deelvragen:
        # Geef één feedback item PER problematische deelvraag terug,
        # zodat elk een apart Word-comment op de juiste tekst krijgt.
        items = []
        for problematic in problematic_deelvragen:
            snippet = problematic['tekst'][:200]
            nummer = problematic['nummer'].rstrip('.')
            items.append({
                'criteria_id': get_criterion_value(criterion, 'id'),
                'criteria_name': get_criterion_value(criterion, 'name'),
                'section_id': section.get('db_id'),
                'section_name': section['name'],
                'status': get_criterion_value(criterion, 'severity', 'warning'),
                'message': get_criterion_value(criterion, 'error_message',
                    f"Deelvraag {nummer} bevat twee volledige hoofdzinnen gescheiden door 'en'. "
                    f"Elke deelvraag dient slechts één vraag te bevatten."),
                'suggestion': get_criterion_value(criterion, 'fixed_feedback_text',
                    f"Splits deelvraag {nummer} op in twee afzonderlijke deelvragen, "
                    f"zodat elke deelvraag één duidelijke vraag stelt."),
                'location': f"Sectie: {section['name']}",
                'confidence': 0.85,
                'color': get_criterion_value(criterion, 'color', '#FFD700'),
                'offending_snippet': snippet,
                'check_type': 'structural',
            })
        return items
    else:
        return {
            'criteria_id': get_criterion_value(criterion, 'id'),
            'criteria_name': get_criterion_value(criterion, 'name'),
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': 'ok',
            'message': f"De deelvragen in '{section['name']}' bevatten elk slechts één hoofdzin.",
            'suggestion': "",
            'location': f"Sectie: {section['name']}",
            'confidence': 0.9,
            'color': '#84A98C',
            'check_type': 'structural',
        }


def check_heading_structure(criterion: dict, section: dict, db_connection: sqlite3.Connection = None):
    """Controleert kopjes structuur van een sectie."""
    # Veronderstelt dat de `section` dict een lijst van `headings` bevat,
    # die de daadwerkelijke kopjes uit de geparste content zijn.
    headings = section.get('headings', [])

    feedback = None

    # Als het criterium specificeert dat er minimaal N kopjes moeten zijn
    expected_min_headings = get_criterion_value(criterion, 'expected_value_min')
    if isinstance(expected_min_headings, (int, float)):
        expected_min_headings = int(expected_min_headings)
    else:
        expected_min_headings = None

    if expected_min_headings is not None and len(headings) < expected_min_headings:
        feedback = {
            'criteria_id': get_criterion_value(criterion, 'id'),
            'criteria_name': get_criterion_value(criterion, 'name'),
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': get_criterion_value(criterion, 'severity', 'warning'),
            'message': get_criterion_value(criterion, 'error_message', f"Sectie '{section['name']}' heeft {len(headings)} subkopjes, minimaal {expected_min_headings} vereist."),
            'suggestion': get_criterion_value(criterion, 'fixed_feedback_text', "Overweeg subkopjes toe te voegen voor een betere structuur en leesbaarheid."),
            'location': f"Sectie: {section['name']}",
            'confidence': 0.7,
            'color': get_criterion_value(criterion, 'color', '#FFD700'),
            'check_type': 'structural',
        }
    elif expected_min_headings is not None: # Als er een minimum is ingesteld en het is OK
        feedback = {
            'criteria_id': get_criterion_value(criterion, 'id'),
            'criteria_name': get_criterion_value(criterion, 'name'),
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': 'ok',
            'message': f"De sectie '{section['name']}' heeft voldoende subkopjes ({len(headings)}).",
            'suggestion': "",
            'location': f"Sectie: {section['name']}",
            'confidence': 1.0,
            'color': '#84A98C',
            'check_type': 'structural',
        }
    elif not headings and ('structuur' in get_criterion_value(criterion, 'name', '').lower() or 'kopje' in get_criterion_value(criterion, 'name', '').lower()):
        # Generieke check als er geen specifieke min/max is, maar naam impliceert structuur
        feedback = {
            'criteria_id': get_criterion_value(criterion, 'id'),
            'criteria_name': get_criterion_value(criterion, 'name'),
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': get_criterion_value(criterion, 'severity', 'warning'),
            'message': get_criterion_value(criterion, 'error_message', f"Sectie '{section['name']}' heeft geen subkopjes, wat de leesbaarheid kan verminderen."),
            'suggestion': get_criterion_value(criterion, 'fixed_feedback_text', "Overweeg subkopjes toe te voegen voor een betere structuur en leesbaarheid."),
            'location': f"Sectie: {section['name']}",
            'confidence': 0.7,
            'color': get_criterion_value(criterion, 'color', '#FFD700'),
            'check_type': 'structural',
        }
    return feedback

def check_content_criterion(criterion: dict, section: dict, all_recognized_sections: list, db_connection: sqlite3.Connection):
    """
    Controleert inhoudelijke criteria (bijv. volledigheid, relevantie, etc.).
    Kan de `all_recognized_sections` lijst gebruiken voor context over andere secties.
    """
    content = section.get('content', '').lower()
    criterion_name = get_criterion_value(criterion, 'name', '').lower()

    # Voorbeeld: "Hoofdvraag aansluiting"
    if 'hoofdvraag aansluiting' in criterion_name and section.get('identifier') == 'onderzoeksvragen':
        # Haal de probleemstelling op (virtueel, dit zou in een echte implementatie van 'all_recognized_sections' komen)
        problem_statement_section = next((s for s in all_recognized_sections if s.get('identifier') == 'probleemstelling'), None)
        problem_statement_content = problem_statement_section.get('content', '').lower() if problem_statement_section else ''

        # Simpele dummy logica: check of hoofdvraag gerelateerde termen in beide secties voorkomen
        if not ("hoofdvraag" in content and "probleemstelling" in problem_statement_content):
            return {
                'criteria_id': get_criterion_value(criterion, 'id'),
                'criteria_name': get_criterion_value(criterion, 'name'),
                'section_id': section.get('db_id'),
                'section_name': section['name'],
                'status': get_criterion_value(criterion, 'severity', 'violation'),
                'message': get_criterion_value(criterion, 'error_message', f"De sectie 'Onderzoeksvragen' lijkt niet duidelijk aan te sluiten op de probleemstelling of mist een expliciete hoofdvraag."),
                'suggestion': get_criterion_value(criterion, 'fixed_feedback_text', "Zorg voor een duidelijke hoofdvraag die direct voortvloeit uit de probleemstelling en controleer de consistentie."),
                'location': f"Sectie: {section['name']}",
                'confidence': 0.6,
                'color': get_criterion_value(criterion, 'color', '#FF0000')
            }
        else:
            return {
                'criteria_id': get_criterion_value(criterion, 'id'),
                'criteria_name': get_criterion_value(criterion, 'name'),
                'section_id': section.get('db_id'),
                'section_name': section['name'],
                'status': 'ok',
                'message': f"De sectie 'Onderzoeksvragen' lijkt goed aan te sluiten op de probleemstelling.",
                'suggestion': "",
                'location': f"Sectie: {section['name']}",
                'confidence': 1.0,
                'color': '#84A98C'
            }

    # Voeg hier meer inhoudelijke checks toe
    return None

def check_document_wide_criterion(criterion: dict, doc_content: str, all_recognized_sections: list):
    """
    Controleert criteria die de hele documentcontext nodig hebben, zoals sectievolgorde
    of document-brede inhoudelijke analyses. Dit zijn checks die *niet* aan een specifieke
    sectie gekoppeld kunnen worden, maar aan het document als geheel.
    """
    feedback = None
    criterion_name = get_criterion_value(criterion, 'name').lower()

    # Voorbeeld: Sectie Volgorde Check
    if 'sectievolgorde' in criterion_name or 'section order' in criterion_name:
        # Dit vereist dat all_recognized_sections gesorteerd is op basis van hun voorkomen in het document
        # en dat je de 'order_index' uit de DB secties kent.
        
        # Aanname: `all_recognized_sections` is al gesorteerd op fysieke voorkomen OF
        # we halen de verwachte volgorde op en vergelijken de gevonden identifiers.
        
        # Voor een simpele demo: controleer of 'inleiding' voor 'methode' komt
        found_inleiding = next((s for s in all_recognized_sections if s.get('identifier') == 'inleiding' and s.get('found')), None)
        found_methode = next((s for s in all_recognized_sections if s.get('identifier') == 'methode' and s.get('found')), None)

        if found_inleiding and found_methode:
            # We moeten de *positie* in het originele document weten.
            # Nu hebben we alleen de content. section_recognition zou start/end indexen moeten geven.
            # Voor nu een simpele check op basis van de volgorde in de `all_recognized_sections` lijst
            # zoals die is binnengekomen (wat hopelijk de fysieke volgorde reflecteert).
            
            inleiding_index = -1
            methode_index = -1
            for i, sec in enumerate(all_recognized_sections):
                if sec.get('identifier') == 'inleiding':
                    inleiding_index = i
                if sec.get('identifier') == 'methode':
                    methode_index = i
            
            if inleiding_index != -1 and methode_index != -1 and inleiding_index > methode_index:
                feedback = {
                    'criteria_id': get_criterion_value(criterion, 'id'),
                    'criteria_name': get_criterion_value(criterion, 'name'),
                    'section_id': None, # Geldt voor hele document
                    'section_name': 'Hele Document',
                    'status': get_criterion_value(criterion, 'severity', 'violation'),
                    'message': get_criterion_value(criterion, 'error_message', f"De sectie 'Methode' lijkt vóór de sectie 'Inleiding' te staan, wat afwijkt van de verwachte volgorde."),
                    'suggestion': get_criterion_value(criterion, 'fixed_feedback_text', "Controleer de volgorde van de secties. Zorg dat de Inleiding voor de Methode-sectie komt."),
                    'location': 'Document Structuur',
                    'confidence': 0.9,
                    'color': get_criterion_value(criterion, 'color', '#FF0000')
                }
            else:
                feedback = {
                    'criteria_id': get_criterion_value(criterion, 'id'),
                    'criteria_name': get_criterion_value(criterion, 'name'),
                    'section_id': None,
                    'section_name': 'Hele Document',
                    'status': 'ok',
                    'message': f"De secties 'Inleiding' en 'Methode' lijken in de juiste volgorde te staan.",
                    'suggestion': "",
                    'location': 'Document Structuur',
                    'confidence': 1.0,
                    'color': '#84A98C'
                }
        # Als één van de secties niet gevonden is, geen feedback over volgorde
        elif (found_inleiding and not found_methode) or (not found_inleiding and found_methode):
            feedback = {
                'criteria_id': get_criterion_value(criterion, 'id'),
                'criteria_name': get_criterion_value(criterion, 'name'),
                'section_id': None,
                'section_name': 'Hele Document',
                'status': 'info',
                'message': f"Sectievolgorde check voor '{get_criterion_value(criterion, 'name')}' kon niet volledig worden uitgevoerd; één of meer relevante secties niet gevonden.",
                'suggestion': "Zorg dat alle verwachte secties aanwezig zijn.",
                'location': 'Document Structuur',
                'confidence': 0.5,
                'color': '#ADD8E6' # Lichtblauw voor info
            }

    # Meer document-brede checks hier
    # Bijvoorbeeld: "Algemeen taalgebruik", "Consistentie van terminologie"

    return feedback


# ---------------------------------------------------------------------------
# Holistische sectie-review
# ---------------------------------------------------------------------------

_HOLISTIC_CRITERIA_PROMPT = """
Beoordeel de algehele kwaliteit en inhoudelijke diepgang van deze sectie in de context van het volledige document.

Kijk naar:
1. Interne samenhang — bouwt de tekst logisch op? Sluiten alinea's op elkaar aan?
2. Volledigheid — worden de verwachte elementen voor dit type sectie behandeld?
3. Diepgang en onderbouwing — worden stellingen onderbouwd? Of blijft de tekst oppervlakkig?
4. Coherentie met het document — sluit de sectie inhoudelijk goed aan op de rest van het stuk?

Geef een integrale beoordeling van het geheel. Benoem wat goed gaat én wat beter kan.
Ga NIET in op spelfouten, opmaak of woordkeuze — die worden apart beoordeeld.
Geef maximaal 3 concrete aandachtspunten, elk met een citaat uit de tekst.
Formuleer elk aandachtspunt coachend en constructief: benoem het probleem, leg uit waarom het belangrijk is, en nodig de student uit tot reflectie. Gebruik formuleringen als "overweeg", "het zou sterker zijn als", "een aandachtspunt is" — vermijd harde of definitieve taal.
""".strip()


def run_holistic_section_reviews(
    recognized_sections: list,
    full_doc_text: str,
    llm_model: str = 'claude-haiku-4-5',
    min_words: int = 20,
    show_suggestions: bool = True,
) -> list:
    """
    Voert een holistische LLM-review uit voor elke gevonden sectie met voldoende content.
    Retourneert een lijst van feedback-items (kan leeg zijn bij fouten of te korte secties).

    Alle calls delen dezelfde gecachte documentblob → tokenkosten zijn minimaal.
    """
    from datetime import date as _date
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not full_doc_text:
        return []

    _d = _date.today()
    _maanden = ['januari','februari','maart','april','mei','juni',
                'juli','augustus','september','oktober','november','december']
    _vandaag_str = f"{_d.day} {_maanden[_d.month - 1]} {_d.year}"

    role_prompt = (
        'Je bent een kritische Nederlandse docent die de kwaliteit van studentwerk beoordeelt. '
        'Jij geeft een integrale, holistische beoordeling van een sectie — geen lijstje checkboxen.\n\n'
        f'VANDAAG IS HET: {_vandaag_str}. '
        'Beoordeel data en jaartallen altijd ten opzichte van deze datum.\n\n'
        + _NL_TAALGEBRUIK
    )

    # Gecacht blok: identiek voor alle holistische calls op dit document
    cached_text = (
        f"[VOLLEDIG DOCUMENT — CONTEXT]\n{full_doc_text[:40000]}\n"
        f"[/VOLLEDIG DOCUMENT]"
    )

    def _review_one(section: dict) -> list:
        if not section.get('found'):
            return []
        sec_content = (section.get('content') or '').strip()
        word_count = len(re.findall(r'\b\w+\b', sec_content))
        if word_count < min_words:
            return []

        sec_name = section.get('name', 'Onbekend')
        _schema  = _LLM_RESPONSE_SCHEMA if show_suggestions else _LLM_RESPONSE_SCHEMA_NO_SUGGESTIONS
        uncached_text = '\n\n'.join([
            f"[TE BEOORDELEN SECTIE: '{sec_name}']\n{sec_content[:8000]}\n[/TE BEOORDELEN SECTIE]",
            _HOLISTIC_CRITERIA_PROMPT,
            _schema,
        ])

        import time as _time
        import logging as _logging
        _hlog = _logging.getLogger('docucheck')

        llm_result = None
        for _attempt in range(3):
            try:
                llm_result = _call_llm(llm_model, role_prompt, cached_text, uncached_text, max_tokens=2048)
                break
            except Exception as exc:
                exc_str = str(exc)
                if '429' in exc_str or 'rate_limit' in exc_str.lower() or 'quota' in exc_str.lower():
                    wait = 15 * (2 ** _attempt)
                    _hlog.warning(f"[HOLISTISCH RATE LIMIT] sectie={sec_name} | poging {_attempt + 1}/3 | wacht {wait}s")
                    _time.sleep(wait)
                else:
                    _hlog.warning(f"[HOLISTISCH] LLM-fout voor sectie '{sec_name}': {exc}")
                    break

        if llm_result is None:
            return []

        _hlog.info(
            f"TOKEN-GEBRUIK | criterium=Holistische beoordeling | model={llm_model} | "
            f"sectie={sec_name} | input={llm_result['input_tokens']} | output={llm_result['output_tokens']} | "
            f"cache_created={llm_result['cache_created']} | cache_read={llm_result['cache_read']}"
        )
        raw = llm_result['text'].strip()

        try:
            result = _extract_json(raw)
        except (ValueError, json.JSONDecodeError):
            return []

        oordeel   = result.get('oordeel', 'matig').lower()
        problemen = result.get('problemen', [])
        samen     = result.get('samenvatting', '')
        status    = _OORDEEL_TO_STATUS.get(oordeel, 'warning')

        if not problemen or status == 'ok':
            return [{
                'criteria_id':       None,
                'criteria_name':     'Holistische beoordeling',
                'section_id':        section.get('db_id'),
                'section_name':      sec_name,
                'status':            'ok',
                'message':           samen or f"Sectie '{sec_name}' is kwalitatief goed.",
                'suggestion':        '',
                'location':          f"Sectie: {sec_name}",
                'confidence':        0.85,
                'color':             '#84A98C',
                'offending_snippet': None,
                'check_type':        'holistic',
            }]

        items = []
        for prob in problemen[:3]:
            items.append({
                'criteria_id':       None,
                'criteria_name':     'Holistische beoordeling',
                'section_id':        section.get('db_id'),
                'section_name':      sec_name,
                'status':            status,
                'message':           prob.get('probleem', ''),
                'suggestion':        prob.get('suggestie', ''),
                'location':          f"Sectie: {sec_name}",
                'confidence':        0.85,
                'color':             '#9B72CF',  # paars: onderscheidt holistische van criterium-feedback
                'offending_snippet': (prob.get('citaat') or '')[:200] or None,
                'check_type':        'holistic',
            })
        if samen:
            items[0]['message'] = f"{samen}\n\n{items[0]['message']}" if items else samen
        return items

    tasks = [s for s in recognized_sections if s.get('found') and s.get('identifier') != 'document']
    results = []
    if not tasks:
        return results

    import logging as _log_outer
    _olog = _log_outer.getLogger('docucheck')
    _olog.info(f"[HOLISTISCH] {len(tasks)} secties worden holistisch beoordeeld")
    with ThreadPoolExecutor(max_workers=1) as executor:
        future_map = {executor.submit(_review_one, sec): sec for sec in tasks}
        for future in as_completed(future_map):
            try:
                items = future.result()
                results.extend(items)
            except Exception as exc:
                _olog.warning(f"[HOLISTISCH] Onverwachte fout: {exc}")

    return results


# --- Hoofd Feedback Generatie Functie ---

def generate_feedback(doc_content: str, recognized_sections: list, criteria_list: list, db_connection: sqlite3.Connection, document_id: int, document_type_id: int, only_section_names: set = None, include_doc_wide: bool = True) -> list[dict]:
    """
    Genereert feedback op basis van de gehele documentinhoud, herkende secties en criteria.

    Args:
        doc_content: De volledige tekstuele inhoud van het document.
        recognized_sections: Lijst van herkende secties met hun metadata en content.
                             Belangrijk: elke sectie in deze lijst moet een 'content' veld hebben
                             en een 'db_id' veld (de id van de sectie in de database) of 'identifier'.
                             Ook 'headings' voor sectie-specifieke heading checks.
        criteria_list: Lijst van criteria uit de database, inclusief hun mappings.
        db_connection: De actieve database connectie.
        document_id: Het ID van het specifieke document dat wordt geanalyseerd (voor opslag in de database).
        document_type_id: Het ID van het documenttype dat wordt geanalyseerd (nodig voor sectie mappings).

    Returns:
        Lijst van feedback items dictionaries.
    """

    feedback_items = []
    # Deze dictionary houdt bij hoe vaak een criterium is voorgekomen binnen een bepaalde scope
    # Key formaat: (criterium_id, scope_key)
    occurrences_count = {}

    # Voetnoten/eindnoten uit doc_content extraheren en aan elke sectie toevoegen
    # zodat de LLM altijd de bronvermeldingen kan zien
    voetnoten_blok = ''
    if '[VOETNOTEN/EINDNOTEN]' in (doc_content or ''):
        try:
            v_start = doc_content.index('[VOETNOTEN/EINDNOTEN]')
            v_eind  = doc_content.index('[/VOETNOTEN/EINDNOTEN]', v_start) + len('[/VOETNOTEN/EINDNOTEN]')
            voetnoten_blok = '\n\n' + doc_content[v_start:v_eind]
        except ValueError:
            pass

    if voetnoten_blok:
        for sec in recognized_sections:
            if sec.get('content'):
                sec['content'] = sec['content'].rstrip() + voetnoten_blok

    # Haal de standaard LLM-rolprompt en show_suggestions op voor dit documenttype (eenmalig)
    _default_role_prompt = ''
    _show_suggestions    = True
    if db_connection and document_type_id:
        try:
            row = db_connection.execute(
                'SELECT default_llm_role_prompt, show_suggestions FROM document_types WHERE id=?',
                (document_type_id,)
            ).fetchone()
            if row:
                _default_role_prompt = (row[0] or '').strip()
                _show_suggestions    = bool(row[1]) if row[1] is not None else True
        except Exception:
            pass

    # Injecteer rolprompt, volledige documenttekst en show_suggestions in alle secties.
    # _show_suggestions bepaalt of de LLM suggesties genereert (effect op output-tokens).
    for s in recognized_sections:
        s['_default_role_prompt'] = _default_role_prompt
        s['_full_doc_text']       = doc_content
        s['_show_suggestions']    = _show_suggestions

    # Voeg een virtuele "hele document" sectie toe aan recognized_sections voor globale checks.
    # Deze sectie heeft 'document' als identifier en een db_id van None.
    # Let op: 'content' van de document_section is de volledige doc_content.
    document_section = {
        'identifier': 'document',
        'name': 'Hele Document',
        'content': doc_content,
        'found': True,
        'db_id': None,
        'word_count': len(re.findall(r'\b\w+\b', doc_content)),
        'confidence': 1.0,
        'headings': [],
        '_default_role_prompt': _default_role_prompt,
        '_full_doc_text': doc_content,
    }
    # Combineer de herkende secties met de virtuele 'hele document' sectie.
    # Bij gedeeltelijke heranalyse (only_section_names) worden niet-geselecteerde secties
    # en de document-sectie optioneel overgeslagen.
    section_pool = recognized_sections if only_section_names is None else [
        s for s in recognized_sections if s.get('name') in only_section_names
    ]
    if include_doc_wide:
        all_sections_for_processing = section_pool + [document_section]
    else:
        all_sections_for_processing = section_pool

    # -----------------------------------------------------------------------
    # Stap 1: Verzamel alle taken (criterium × sectie).
    #   - Snelle taken (niet-LLM) direct uitvoeren.
    #   - LLM-taken apart bewaren voor parallelle uitvoering.
    # -----------------------------------------------------------------------
    fast_raw: List[tuple] = []   # (criterion, section, result)
    llm_tasks: List[tuple] = []  # (criterion, section)

    for criterion in criteria_list:
        if not get_criterion_value(criterion, 'is_enabled', True):
            continue

        if get_criterion_value(criterion, 'application_scope') == 'document_only':
            check_type_doc = get_criterion_value(criterion, 'check_type', 'none') or 'none'
            if check_type_doc == 'llm_review':
                # LLM-check op heel het document: gebruik de virtuele document_section
                llm_tasks.append((criterion, document_section))
            else:
                result = check_document_wide_criterion(criterion, doc_content, all_sections_for_processing)
                fast_raw.append((criterion, None, result))
            continue

        applicable_sections = get_applicable_sections(
            criterion,
            [s for s in all_sections_for_processing if s['identifier'] != 'document'],
            document_type_id,
            db_connection,
        )

        check_type = get_criterion_value(criterion, 'check_type', 'none') or 'none'

        for section in applicable_sections:
            if check_type == 'llm_review':
                # Sla op voor parallelle uitvoering; content zit al in sectie-dict
                llm_tasks.append((criterion, section))
            else:
                # Snelle check: direct uitvoeren
                if check_type != 'none' and check_type in CHECK_REGISTRY:
                    result = CHECK_REGISTRY[check_type](criterion, section, db_connection)
                elif get_criterion_value(criterion, 'rule_type') == 'tekstueel':
                    result = check_textual_criterion(criterion, section, db_connection)
                elif get_criterion_value(criterion, 'rule_type') == 'structureel':
                    result = check_structural_criterion(criterion, section, db_connection)
                elif get_criterion_value(criterion, 'rule_type') == 'inhoudelijk':
                    result = check_content_criterion(criterion, section, all_sections_for_processing, db_connection)
                else:
                    print(f"    WAARSCHUWING: onbekend rule_type '{criterion['rule_type']}' "
                          f"voor criterium [{criterion['id']}] {criterion['name']!r}")
                    result = None
                fast_raw.append((criterion, section, result))

    # -----------------------------------------------------------------------
    # Stap 2: Voer LLM-taken parallel uit.
    #   db_connection=None is veilig: content zit al in de sectie-dict.
    # -----------------------------------------------------------------------
    llm_raw: List[tuple] = []  # (criterion, section, result)
    if llm_tasks:
        # 1 worker: serieel uitvoeren voorkomt token-per-minuut rate limits bij Anthropic.
        # Met prompt-caching is de overhead per call klein genoeg dat serieel acceptabel is.
        max_workers = 1
        print(f"[LLM-PARALLEL] {len(llm_tasks)} taken gestart met max {max_workers} workers")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(check_llm_review, crit, sec, None): (crit, sec)
                for crit, sec in llm_tasks
            }
            for future in as_completed(future_map):
                crit, sec = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:
                    print(f"[LLM-PARALLEL] Fout bij criterium "
                          f"{get_criterion_value(crit, 'name')}: {exc}")
                    result = None
                llm_raw.append((crit, sec, result))

    # -----------------------------------------------------------------------
    # Stap 3: Post-processing op alle resultaten (snelle + LLM).
    # -----------------------------------------------------------------------
    def _post_process(criterion, section, raw_result):
        """Verwerk één raw resultaat: show_suggestion, snippet, frequentiebeperking."""
        if isinstance(raw_result, list):
            candidates = raw_result
        elif raw_result is not None:
            candidates = [raw_result]
        else:
            return

        for item in candidates:
            # show_suggestion uitschakelen indien geconfigureerd
            try:
                crit_params = json.loads(criterion.get('parameters') or '{}')
                if not crit_params.get('show_suggestion', True):
                    item['suggestion'] = ''
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass

            # Automatisch offending_snippet invullen als het ontbreekt
            if item.get('status') not in ('ok', None) and not item.get('offending_snippet'):
                sec = section or {}
                sec_content = get_section_content(sec, db_connection) if sec else ''
                if sec_content:
                    sents = re.split(r'(?<=[.!?])\s+', sec_content.strip())
                    for sent in sents:
                        if len(sent.strip()) >= 10:
                            item['offending_snippet'] = sent.strip()[:150]
                            break

            # Frequentiebeperking
            if section is not None:
                frequency_unit = get_criterion_value(criterion, 'frequency_unit')
                if frequency_unit == 'document':
                    scope_key = 'document'
                elif frequency_unit == 'section':
                    scope_key = section.get('identifier', 'document_fallback_section')
                elif frequency_unit == 'paragraph':
                    scope_key = f"paragraph_in_{section.get('identifier', 'document_fallback_paragraph')}"
                else:
                    scope_key = 'document_fallback_unknown_unit'
            else:
                scope_key = 'document'

            crit_id = get_criterion_value(criterion, 'id')
            current_count = occurrences_count.get((crit_id, scope_key), 0)
            max_mentions = get_criterion_value(criterion, 'max_mentions_per', 0)

            if item['status'] == 'ok' or max_mentions == 0 or current_count < max_mentions:
                feedback_items.append(item)
                occurrences_count[(crit_id, scope_key)] = current_count + 1

    for criterion, section, result in fast_raw:
        _post_process(criterion, section, result)

    for criterion, section, result in llm_raw:
        _post_process(criterion, section, result)

    return feedback_items


# ---------------------------------------------------------------------------
# Vul CHECK_REGISTRY in — pas hier toe nadat alle functies zijn gedefinieerd.
# Nieuwe check-typen toevoegen = één regel hier.
# ---------------------------------------------------------------------------
CHECK_REGISTRY.update({
    'keyword_forbidden':  check_keyword_forbidden,
    'keyword_required':   check_keyword_required,
    'compound_question':  check_deelvragen_structure,
    'word_count':         check_word_count,
    'paragraph_count':    check_paragraph_structure,
    'heading_count':      check_heading_structure,
    'smart_check':        check_smart_formulation,
    'llm_review':         check_llm_review,
})
