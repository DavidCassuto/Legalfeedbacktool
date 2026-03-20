import json
import re
import sqlite3
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
        from criterion_checking import get_section_content_from_db
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
        }

    # Zoek de eerste zin die een verboden woord bevat als snippet
    offending_snippet = None
    for sent in re.split(r'(?<=[.!?])\s+', raw.strip()):
        if any(re.search(r'\b' + re.escape(kw) + r'\b', sent, re.IGNORECASE) for kw in found):
            offending_snippet = sent.strip()[:200]
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
    }


def check_keyword_required(criterion: dict, section: dict, db_connection=None):
    """
    Controleert dat bepaalde woorden WEL voorkomen in de sectie.
    Keywords worden gelezen uit criterion['parameters'] als JSON: {"keywords": ["output", "outcome", ...]}.
    """
    raw = section.get('content', '')
    if not raw and db_connection and section.get('db_id'):
        from criterion_checking import get_section_content_from_db
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
        }

    # Gebruik de eerste zin van de sectie als snippet
    offending_snippet = None
    for sent in re.split(r'(?<=[.!?])\s+', raw.strip()):
        if len(sent.strip()) >= 10:
            offending_snippet = sent.strip()[:200]
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
            # Fallback: geen mappings beschikbaar, gebruik alle gevonden secties
            applicable_sections = list(sections_dict.values())

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
            'color': get_criterion_value(criterion, 'color', '#FFD700')
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
            'color': get_criterion_value(criterion, 'color', '#FFD700')
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
            'color': '#84A98C'
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

    # document_parsing.py slaat echte alinea's op met \n\n als scheidingsteken
    # en koppen/lege regels met enkele \n — split hierop voor betrouwbare alinea-detectie
    raw_blocks = re.split(r'\n\n+', content)
    paragraphs = []
    for block in raw_blocks:
        # Voeg eventuele interne regelombrekingen samen tot één alineatekst
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if not lines:
            continue
        para_text = ' '.join(lines)
        # Sla heading-achtige blokken over (sectietitels, tussenkopjes)
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
            feedback_list.append({
                'criteria_id': get_criterion_value(criterion, 'id'),
                'criteria_name': get_criterion_value(criterion, 'name'),
                'section_id': section.get('db_id'),
                'section_name': section['name'],
                'status': get_criterion_value(criterion, 'severity', 'warning'),
                'message': f"Alinea {para_idx + 1} heeft {word_count} woorden, minimaal {expected_min_words} vereist.",
                'suggestion': f"Breid deze alinea uit van {word_count} naar minimaal {expected_min_words} woorden.",
                'location': f"Sectie '{section['name']}', alinea {para_idx + 1}",
                'offending_snippet': para_text[:120],
                'confidence': 0.85,
                'color': get_criterion_value(criterion, 'color', '#FFD700')
            })
        elif expected_max_words is not None and word_count > expected_max_words:
            feedback_list.append({
                'criteria_id': get_criterion_value(criterion, 'id'),
                'criteria_name': get_criterion_value(criterion, 'name'),
                'section_id': section.get('db_id'),
                'section_name': section['name'],
                'status': get_criterion_value(criterion, 'severity', 'warning'),
                'message': f"Alinea {para_idx + 1} heeft {word_count} woorden, maximaal {expected_max_words} toegestaan.",
                'suggestion': f"Verkort deze alinea van {word_count} naar maximaal {expected_max_words} woorden.",
                'location': f"Sectie '{section['name']}', alinea {para_idx + 1}",
                'offending_snippet': para_text[:120],
                'confidence': 0.85,
                'color': get_criterion_value(criterion, 'color', '#FFD700')
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
            'color': '#84A98C'
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
Als de sectie voldoet, geef dan een leeg "problemen"-array en oordeel "voldoende" of "goed".
""".strip()

_OORDEEL_TO_STATUS = {
    'onvoldoende': 'violation',
    'matig':       'warning',
    'voldoende':   'info',
    'goed':        'ok',
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
    import anthropic as _anthropic
    from config import Config

    # --- Parameters ophalen ---
    try:
        params = json.loads(criterion.get('parameters') or '{}')
    except (json.JSONDecodeError, TypeError):
        params = {}

    role_prompt        = (params.get('llm_role_prompt') or
                          'Je bent een kritische Nederlandse docent die studentenwerk beoordeelt.')
    # Voeg altijd de taalrichtlijnen toe aan het systeemprompt
    role_prompt = role_prompt.rstrip() + '\n\n' + _NL_TAALGEBRUIK
    criteria_prompt    = params.get('llm_criteria_prompt', '').strip()
    check_ai_style     = bool(params.get('llm_check_ai_style', False))

    # --- Sectie-inhoud ophalen ---
    content = get_section_content(section, db_connection).strip()
    if len(content) < 30:
        return None   # sectie te kort / leeg

    # --- Prompt samenstellen ---
    user_blocks = []

    if criteria_prompt:
        user_blocks.append(f"BEOORDELINGSCRITERIA:\n{criteria_prompt}")

    if check_ai_style:
        user_blocks.append(_AI_STYLE_PROMPT_NL)

    user_blocks.append(
        f"TE BEOORDELEN SECTIE — '{section['name']}':\n{content[:3000]}"
    )
    user_blocks.append(_LLM_RESPONSE_SCHEMA)

    user_msg = '\n\n'.join(user_blocks)

    # --- Claude API-call ---
    try:
        client = _anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model='claude-haiku-4-5',
            max_tokens=2048,
            system=role_prompt,
            messages=[{'role': 'user', 'content': user_msg}],
        )
        raw = response.content[0].text.strip()
    except Exception as exc:
        # API-fout → één waarschuwing als feedback
        return {
            'criteria_id':   get_criterion_value(criterion, 'id'),
            'criteria_name': get_criterion_value(criterion, 'name'),
            'section_id':    section.get('db_id'),
            'section_name':  section['name'],
            'status':        'warning',
            'message':       f"LLM-beoordeling mislukt: {exc}",
            'suggestion':    'Controleer de ANTHROPIC_API_KEY omgevingsvariabele.',
            'location':      f"Sectie: {section['name']}",
            'confidence':    0.0,
            'color':         '#F9C74F',
        }

    # --- JSON-antwoord parsen ---
    try:
        # Verwijder eventuele markdown code-blokken
        clean = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        clean = re.sub(r'\s*```\s*$', '', clean, flags=re.MULTILINE).strip()
        # Zoek de JSON als de LLM toch wat tekst voor/na heeft gezet
        match = re.search(r'\{.*\}', clean, flags=re.DOTALL)
        result = json.loads(match.group(0) if match else clean)
    except (json.JSONDecodeError, AttributeError) as exc:
        return {
            'criteria_id':   get_criterion_value(criterion, 'id'),
            'criteria_name': get_criterion_value(criterion, 'name'),
            'section_id':    section.get('db_id'),
            'section_name':  section['name'],
            'status':        'warning',
            'message':       'LLM-antwoord kon niet worden verwerkt (geen geldige JSON).',
            'suggestion':    f"Ruwe LLM-output: {raw[:200]}",
            'location':      f"Sectie: {section['name']}",
            'confidence':    0.0,
            'color':         '#F9C74F',
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
        }

    # --- Eén feedback-item per probleem → elk krijgt zijn eigen Word-comment ---
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
            'color': '#84A98C' # Groen voor OK
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
                'color': get_criterion_value(criterion, 'color', '#FF0000')
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
                'color': '#84A98C'
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
            'color': get_criterion_value(criterion, 'color', '#FF0000')
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
            'color': get_criterion_value(criterion, 'color', '#FF0000')
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
            'color': '#84A98C'
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
        # Geen genummerde items gevonden — probeer zinnen als individuele deelvragen
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
        """Controleert of een stuk tekst een Nederlands vraagwoord bevat."""
        woorden = set(re.findall(r'\b\w+\b', tekst.lower()))
        return bool(woorden & dutch_question_words)

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
            'color': get_criterion_value(criterion, 'color', '#FFD700')
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
            'color': '#84A98C'
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
            'color': get_criterion_value(criterion, 'color', '#FFD700')
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


# --- Hoofd Feedback Generatie Functie ---

def generate_feedback(doc_content: str, recognized_sections: list, criteria_list: list, db_connection: sqlite3.Connection, document_id: int, document_type_id: int) -> list[dict]:
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

    # Voeg een virtuele "hele document" sectie toe aan recognized_sections voor globale checks.
    # Deze sectie heeft 'document' als identifier en een db_id van None.
    # Let op: 'content' van de document_section is de volledige doc_content.
    document_section = {
        'identifier': 'document',
        'name': 'Hele Document',
        'content': doc_content,
        'found': True, # De virtuele sectie is altijd 'gevonden'
        'db_id': None, # Heeft geen corresponderende DB sectie ID
        'word_count': len(re.findall(r'\b\w+\b', doc_content)), # Nauwkeurige woordtelling
        'confidence': 1.0, # Volledige zekerheid voor de hele document sectie
        'headings': [] # Kan eventueel gevuld worden met document-brede top-level headings
    }
    # Combineer de herkende secties met de virtuele 'hele document' sectie.
    # Dit zorgt ervoor dat criteria die van toepassing zijn op 'document' scope ook worden verwerkt.
    all_sections_for_processing = recognized_sections + [document_section]

    # Eerst, verwerk de sectie-specifieke en algemene document-scope criteria
    for criterion in criteria_list:
        # Sla uitgeschakelde criteria over
        if not get_criterion_value(criterion, 'is_enabled', True):
            continue

        # Bepaal welke secties relevant zijn voor dit specifieke criterium.
        # document_type_id is hier essentieel om de juiste criterium-sectie mappings te vinden.
        # Let op: de 'document_only' scope wordt hier gefilterd en apart behandeld.
        if get_criterion_value(criterion, 'application_scope') == 'document_only':
            feedback_item = check_document_wide_criterion(criterion, doc_content, all_sections_for_processing)
            if feedback_item:
                # Frequentiebeperking voor document-wide checks
                current_count = occurrences_count.get((get_criterion_value(criterion, 'id'), 'document'), 0)
                max_mentions = get_criterion_value(criterion, 'max_mentions_per', 0)

                if feedback_item['status'] == 'ok' or max_mentions == 0 or current_count < max_mentions:
                    feedback_items.append(feedback_item)
                    occurrences_count[(get_criterion_value(criterion, 'id'), 'document')] = current_count + 1
            continue # Ga naar het volgende criterium, dit is afgehandeld

        # Voor alle andere scopes (all, specific_sections, exclude_sections)
        # De 'document' virtuele sectie is al afgehandeld voor 'document_only' criteria
        # en wordt hier expliciet uitgesloten om dubbele checks te voorkomen.
        applicable_sections = get_applicable_sections(criterion, [s for s in all_sections_for_processing if s['identifier'] != 'document'], document_type_id, db_connection)

        # Itereer over elke toepasselijke sectie om het criterium te controleren
        for section in applicable_sections:
            feedback_item = None

            # Roep de juiste check-functie aan.
            # Prioriteit 1: check_type registry (direct en expliciet geconfigureerd).
            # Prioriteit 2: oude routing op basis van rule_type (backward-compatible fallback).
            check_type = get_criterion_value(criterion, 'check_type', 'none') or 'none'
            if check_type != 'none' and check_type in CHECK_REGISTRY:
                check_fn = CHECK_REGISTRY[check_type]
                # compound_question en andere structurele checks verwachten geen extra args
                feedback_item = check_fn(criterion, section, db_connection)
            elif get_criterion_value(criterion, 'rule_type') == 'tekstueel':
                feedback_item = check_textual_criterion(criterion, section, db_connection)
            elif get_criterion_value(criterion, 'rule_type') == 'structureel':
                feedback_item = check_structural_criterion(criterion, section, db_connection)
            elif get_criterion_value(criterion, 'rule_type') == 'inhoudelijk':
                feedback_item = check_content_criterion(criterion, section, all_sections_for_processing, db_connection)
            else:
                print(f"    WAARSCHUWING: onbekend rule_type '{criterion['rule_type']}' "
                      f"voor criterium [{criterion['id']}] {criterion['name']!r}")
            # Nieuwe check-typen: voeg toe aan CHECK_REGISTRY bovenaan dit bestand

            # Een check-functie mag een lijst van items teruggeven (bijv. meerdere foute deelvragen).
            # Normaliseer altijd naar een lijst voor uniforme verwerking.
            if isinstance(feedback_item, list):
                candidates = feedback_item
            elif feedback_item is not None:
                candidates = [feedback_item]
            else:
                candidates = []

            for feedback_item in candidates:

                # --- show_suggestion: suggestie wissen als uitgeschakeld voor dit criterium ---
                try:
                    crit_params = json.loads(criterion.get('parameters') or '{}')
                    if not crit_params.get('show_suggestion', True):
                        feedback_item['suggestion'] = ''
                except (json.JSONDecodeError, TypeError, AttributeError):
                    pass

                # --- Automatisch offending_snippet toevoegen als dat ontbreekt ---
                if feedback_item.get('status') not in ('ok', None):
                    if not feedback_item.get('offending_snippet'):
                        sec_content = get_section_content(section, db_connection)
                        if sec_content:
                            sents = re.split(r'(?<=[.!?])\s+', sec_content.strip())
                            for s in sents:
                                if len(s.strip()) >= 10:
                                    feedback_item['offending_snippet'] = s.strip()[:150]
                                    break

                # --- Frequentiebeperkingslogica ---
                scope_key = ''
                frequency_unit = get_criterion_value(criterion, 'frequency_unit')

                if frequency_unit == 'document':
                    scope_key = 'document'
                elif frequency_unit == 'section':
                    scope_key = section.get('identifier', 'document_fallback_section')
                elif frequency_unit == 'paragraph':
                    scope_key = f"paragraph_in_{section.get('identifier', 'document_fallback_paragraph')}"
                else:
                    scope_key = 'document_fallback_unknown_unit'

                current_count = occurrences_count.get((get_criterion_value(criterion, 'id'), scope_key), 0)
                max_mentions = get_criterion_value(criterion, 'max_mentions_per', 0)

                if feedback_item['status'] == 'ok':
                    feedback_items.append(feedback_item)
                    occurrences_count[(get_criterion_value(criterion, 'id'), scope_key)] = current_count + 1
                elif max_mentions == 0 or current_count < max_mentions:
                    feedback_items.append(feedback_item)
                    occurrences_count[(get_criterion_value(criterion, 'id'), scope_key)] = current_count + 1
                # else: limiet bereikt, item overgeslagen
            # --- Einde candidates loop / Frequentiebeperkingslogica ---

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
