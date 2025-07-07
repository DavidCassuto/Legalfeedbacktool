import json
import re
import sqlite3

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
    return defaults.get(criterion.get('rule_type', 'tekstueel'), [])

def get_applicable_sections(criterion: dict, all_recognized_sections: list, document_type_id: int, db_connection: sqlite3.Connection):
    """
    Bepaalt op welke secties een criterium van toepassing is, gebaseerd op de 'application_scope'
    en eventuele `section_mappings` die al in het criterium object aanwezig zijn.
    """
    applicable_sections = []

    # Haal mappings op uit het criterium object. db_utils.get_criteria_for_document_type
    # zou deze al moeten hebben toegevoegd.
    mappings = criterion.get('section_mappings', [])

    # Maak een dictionary van all_recognized_sections voor snelle lookup op identifier
    # Gebruik .get('found', False) om alleen gevonden secties mee te nemen
    sections_dict = {s['identifier']: s for s in all_recognized_sections if s.get('found', False)}

    if criterion['application_scope'] == 'all':
        # Criterium geldt voor alle herkende secties (behalve de virtuele 'document' sectie).
        applicable_sections = [s for s in all_recognized_sections if s.get('found', False) and s['identifier'] != 'document']

    elif criterion['application_scope'] == 'specific_sections':
        if mappings:
            mapped_identifiers = {m['section_identifier'] for m in mappings if not m['is_excluded']}
            for identifier in mapped_identifiers:
                if identifier in sections_dict:
                    applicable_sections.append(sections_dict[identifier])
        else:
            # Fallback: gebruik standaard secties voor criterium type (via identifier)
            default_identifiers = get_default_sections_for_criterion(criterion)
            for identifier in default_identifiers:
                if identifier in sections_dict:
                    applicable_sections.append(sections_dict[identifier])

    elif criterion['application_scope'] == 'exclude_sections':
        # Criterium geldt voor alle secties behalve uitgesloten.
        excluded_identifiers = {m['section_identifier'] for m in mappings if m['is_excluded']}
        applicable_sections = [s for s in all_recognized_sections if s['identifier'] not in excluded_identifiers and s.get('found', False) and s['identifier'] != 'document']
    
    # Filter uitgesloten secties als mappings aanwezig zijn (redundante check, maar veilig)
    if mappings:
        excluded_by_mapping = {m['section_identifier'] for m in mappings if m['is_excluded']}
        applicable_sections = [s for s in applicable_sections if s['identifier'] not in excluded_by_mapping]

    return applicable_sections

# --- Check Functies voor Specifieke Criteria ---

def check_word_count(criterion: dict, section: dict):
    """Controleert woordtelling van een sectie."""
    content = section.get('content', '')
    word_count = len(re.findall(r'\b\w+\b', content)) # Robuustere telling

    # Haal het verwachte minimum en maximum aantal woorden uit de criterium metadata
    expected_min_words = criterion.get('expected_value_min')
    expected_max_words = criterion.get('expected_value_max')

    feedback = None

    if expected_min_words is not None and word_count < expected_min_words:
        feedback = {
            'criteria_id': criterion['id'],
            'criteria_name': criterion['name'],
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': criterion.get('severity', 'warning'),
            'message': criterion.get('error_message', f"Sectie '{section['name']}' heeft {word_count} woorden, minimaal {expected_min_words} vereist."),
            'suggestion': f"Breid de {section['name']} sectie uit. Huidig: {word_count} woorden, Vereist: {expected_min_words} woorden.",
            'location': f"Sectie: {section['name']}",
            'confidence': 0.8,
            'color': criterion.get('color', '#FFD700')
        }
    elif expected_max_words is not None and word_count > expected_max_words:
        feedback = {
            'criteria_id': criterion['id'],
            'criteria_name': criterion['name'],
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': criterion.get('severity', 'warning'),
            'message': criterion.get('error_message', f"Sectie '{section['name']}' heeft {word_count} woorden, maximaal {expected_max_words} toegestaan."),
            'suggestion': f"Verkort de {section['name']} sectie. Huidig: {word_count} woorden, Maximaal: {expected_max_words} woorden.",
            'location': f"Sectie: {section['name']}",
            'confidence': 0.8,
            'color': criterion.get('color', '#FFD700')
        }
    elif expected_min_words is not None or expected_max_words is not None:
        feedback = {
            'criteria_id': criterion['id'],
            'criteria_name': criterion['name'],
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


def check_smart_formulation(criterion: dict, section: dict):
    """Controleert of tekst SMART geformuleerd is."""
    content = section.get('content', '').lower()

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

    if len(missing_aspects) > 2:
        return {
            'criteria_id': criterion['id'],
            'criteria_name': criterion['name'],
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': criterion.get('severity', 'violation'),
            'message': criterion.get('error_message', f"De {section['name'].lower()} mist belangrijke SMART aspecten: {', '.join(missing_aspects)}"),
            'suggestion': f"Zorg dat de {section['name'].lower()} Specifiek, Meetbaar, Acceptabel, Realistisch en Tijdgebonden is. Ontbrekende: {', '.join(missing_aspects)}.",
            'location': f"Sectie: {section['name']}",
            'confidence': 0.9,
            'color': criterion.get('color', '#FF0000') # Standaardkleur indien afwezig
        }
    elif len(missing_aspects) > 0:
        return {
            'criteria_id': criterion['id'],
            'criteria_name': criterion['name'],
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': criterion.get('severity', 'warning'),
            'message': criterion.get('error_message', f"De {section['name'].lower()} zou kunnen verbeteren op: {', '.join(missing_aspects)}"),
            'suggestion': f"Overweeg om de {section['name'].lower()} completer te maken met betrekking tot: {', '.join(missing_aspects)}.",
            'location': f"Sectie: {section['name']}",
            'confidence': 0.6,
            'color': criterion.get('color', '#FFD700')
        }
    else:
        return {
            'criteria_id': criterion['id'],
            'criteria_name': criterion['name'],
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': 'ok',
            'message': f"De {section['name'].lower()} lijkt SMART geformuleerd te zijn.",
            'suggestion': "",
            'location': f"Sectie: {section['name']}",
            'confidence': 1.0,
            'color': '#84A98C' # Groen voor OK
        }

def check_textual_criterion(criterion: dict, section: dict):
    """Controleert tekstuele criteria (woordgebruik, zinsbouw, etc.)"""
    feedback = None

    raw_content = section.get('content', '')
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
    if 'persoonlijk taalgebruik' in criterion['name'].lower() or \
       (criterion.get('rule_type') == 'tekstueel' and 'persoonlijk' in criterion.get('description', '').lower()):
        personal_pronouns = ['ik', 'mij', 'mijn', 'wij', 'ons', 'onze'] # Kan eventueel uit criterium parameters komen
        
        found_personal_pronouns = [p for p in personal_pronouns if re.search(r'\b' + re.escape(p) + r'\b', content)] # Gebruik regex voor hele woorden
        if found_personal_pronouns:
            feedback = {
                'criteria_id': criterion['id'],
                'criteria_name': criterion['name'],
                'section_id': section.get('db_id'),
                'section_name': section['name'],
                'status': criterion.get('severity', 'warning'),
                'message': criterion.get('error_message', f"Persoonlijk taalgebruik gevonden in '{section['name']}': {', '.join(found_personal_pronouns)}."),
                'suggestion': criterion.get('fixed_feedback_text', "Hanteer een zakelijke schrijfstijl zonder persoonlijke voornaamwoorden."),
                'location': f"Sectie: {section['name']}",
                'confidence': 0.7,
                'color': criterion.get('color', '#FFD700')
            }
        else:
            feedback = {
                'criteria_id': criterion['id'],
                'criteria_name': criterion['name'],
                'section_id': section.get('db_id'),
                'section_name': section['name'],
                'status': 'ok',
                'message': f"Geen persoonlijk taalgebruik gevonden in '{section['name']}'.",
                'suggestion': "",
                'location': f"Sectie: {section['name']}",
                'confidence': 1.0,
                'color': '#84A98C'
            }
    
    # Voeg hier meer 'elif' blokken toe voor andere specifieke tekstuele criteria
    # die je kunt identificeren op basis van 'criterion['name']' of een ander veld.

    return feedback

def check_structural_criterion(criterion: dict, section: dict):
    """
    Controleert structurele criteria (lengte, opbouw, volgorde, kopjes, paragrafen)
    die op EEN specifieke sectie van toepassing zijn.
    """
    criterion_name = criterion['name'].lower()
    
    # Woordtelling criteria (kan ook structureel zijn, als de structuur door lengte wordt beïnvloed)
    if 'woorden' in criterion_name or 'word' in criterion_name or 'lengte' in criterion_name:
        return check_word_count(criterion, section)

    # Paragraaf criteria
    if 'paragraaf' in criterion_name or 'alinea' in criterion_name or 'paragrafen' in criterion_name:
        return check_paragraph_structure(criterion, section)

    # Kopjes/structuur criteria binnen een sectie
    if 'kopje' in criterion_name or 'structuur' in criterion_name or 'headings' in criterion_name:
        return check_heading_structure(criterion, section)
    
    # Criteria voor sectie aanwezigheid (is_required in sections tabel)
    if criterion.get('rule_type') == 'structureel' and 'aanwezigheid' in criterion_name:
        # Dit is een check of de sectie zelf gevonden is.
        if section['identifier'] != 'document' and not section.get('found', False) and section.get('is_required', False): # 'is_required' komt uit de sectie definitie
            return {
                'criteria_id': criterion['id'],
                'criteria_name': criterion['name'],
                'section_id': section.get('db_id'),
                'section_name': section['name'],
                'status': criterion.get('severity', 'violation'),
                'message': criterion.get('error_message', f"De verplichte sectie '{section['name']}' is niet gevonden in het document."),
                'suggestion': criterion.get('fixed_feedback_text', f"Zorg ervoor dat de sectie '{section['name']}' duidelijk aanwezig is in het document."),
                'location': 'Document',
                'confidence': 1.0,
                'color': criterion.get('color', '#FF0000')
            }
        elif section['identifier'] != 'document' and section.get('found', False) and section.get('is_required', False):
            return {
                'criteria_id': criterion['id'],
                'criteria_name': criterion['name'],
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

def check_paragraph_structure(criterion: dict, section: dict):
    """Controleert paragraaf structuur van een sectie."""
    content = section.get('content', '')
    # Gebruik een robuustere methode om paragrafen te splitsen
    paragraphs = re.split(r'\n\s*\n+', content) # Split op 2+ nieuwe regels met optionele spaties ertussen
    paragraphs = [p.strip() for p in paragraphs if p.strip()] # Verwijder lege paragrafen
    paragraph_count = len(paragraphs)

    # Haal min/max paragrafen op uit criterium parameters
    expected_min_paragraphs = criterion.get('expected_value_min')
    expected_max_paragraphs = criterion.get('expected_value_max')

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
            'criteria_id': criterion['id'],
            'criteria_name': criterion['name'],
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': criterion.get('severity', 'violation'),
            'message': criterion.get('error_message', f"Sectie '{section['name']}' heeft {paragraph_count} paragrafen, minimaal {expected_min_paragraphs} vereist."),
            'suggestion': criterion.get('fixed_feedback_text', f"Voeg meer paragrafen toe aan de '{section['name']}' sectie voor betere structuur. Huidig: {paragraph_count}, Vereist: {expected_min_paragraphs}."),
            'confidence': 0.9,
            'color': criterion.get('color', '#FF0000')
        }
    elif expected_max_paragraphs is not None and paragraph_count > expected_max_paragraphs:
        feedback = {
            'criteria_id': criterion['id'],
            'criteria_name': criterion['name'],
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': criterion.get('severity', 'violation'),
            'message': criterion.get('error_message', f"Sectie '{section['name']}' heeft {paragraph_count} paragrafen, maximaal {expected_max_paragraphs} toegestaan."),
            'suggestion': criterion.get('fixed_feedback_text', f"Verkort het aantal paragrafen in de '{section['name']}' sectie. Huidig: {paragraph_count}, Maximaal: {expected_max_paragraphs}."),
            'confidence': 0.9,
            'color': criterion.get('color', '#FF0000')
        }
    elif expected_min_paragraphs is not None or expected_max_paragraphs is not None:
        feedback = {
            'criteria_id': criterion['id'],
            'criteria_name': criterion['name'],
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


def check_heading_structure(criterion: dict, section: dict):
    """Controleert kopjes structuur van een sectie."""
    # Veronderstelt dat de `section` dict een lijst van `headings` bevat,
    # die de daadwerkelijke kopjes uit de geparste content zijn.
    headings = section.get('headings', [])

    feedback = None

    # Als het criterium specificeert dat er minimaal N kopjes moeten zijn
    expected_min_headings = criterion.get('expected_value_min')
    if isinstance(expected_min_headings, (int, float)):
        expected_min_headings = int(expected_min_headings)
    else:
        expected_min_headings = None

    if expected_min_headings is not None and len(headings) < expected_min_headings:
        feedback = {
            'criteria_id': criterion['id'],
            'criteria_name': criterion['name'],
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': criterion.get('severity', 'warning'),
            'message': criterion.get('error_message', f"Sectie '{section['name']}' heeft {len(headings)} subkopjes, minimaal {expected_min_headings} vereist."),
            'suggestion': criterion.get('fixed_feedback_text', "Overweeg subkopjes toe te voegen voor een betere structuur en leesbaarheid."),
            'location': f"Sectie: {section['name']}",
            'confidence': 0.7,
            'color': criterion.get('color', '#FFD700')
        }
    elif expected_min_headings is not None: # Als er een minimum is ingesteld en het is OK
        feedback = {
            'criteria_id': criterion['id'],
            'criteria_name': criterion['name'],
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': 'ok',
            'message': f"De sectie '{section['name']}' heeft voldoende subkopjes ({len(headings)}).",
            'suggestion': "",
            'location': f"Sectie: {section['name']}",
            'confidence': 1.0,
            'color': '#84A98C'
        }
    elif not headings and ('structuur' in criterion.get('name', '').lower() or 'kopje' in criterion.get('name', '').lower()):
        # Generieke check als er geen specifieke min/max is, maar naam impliceert structuur
        feedback = {
            'criteria_id': criterion['id'],
            'criteria_name': criterion['name'],
            'section_id': section.get('db_id'),
            'section_name': section['name'],
            'status': criterion.get('severity', 'warning'),
            'message': criterion.get('error_message', f"Sectie '{section['name']}' heeft geen subkopjes, wat de leesbaarheid kan verminderen."),
            'suggestion': criterion.get('fixed_feedback_text', "Overweeg subkopjes toe te voegen voor een betere structuur en leesbaarheid."),
            'location': f"Sectie: {section['name']}",
            'confidence': 0.7,
            'color': criterion.get('color', '#FFD700')
        }
    return feedback

def check_content_criterion(criterion: dict, section: dict, all_recognized_sections: list):
    """
    Controleert inhoudelijke criteria (bijv. volledigheid, relevantie, etc.).
    Kan de `all_recognized_sections` lijst gebruiken voor context over andere secties.
    """
    content = section.get('content', '').lower()
    criterion_name = criterion.get('name', '').lower()

    # Voorbeeld: "Hoofdvraag aansluiting"
    if 'hoofdvraag aansluiting' in criterion_name and section.get('identifier') == 'onderzoeksvragen':
        # Haal de probleemstelling op (virtueel, dit zou in een echte implementatie van 'all_recognized_sections' komen)
        problem_statement_section = next((s for s in all_recognized_sections if s.get('identifier') == 'probleemstelling'), None)
        problem_statement_content = problem_statement_section.get('content', '').lower() if problem_statement_section else ''

        # Simpele dummy logica: check of hoofdvraag gerelateerde termen in beide secties voorkomen
        if not ("hoofdvraag" in content and "probleemstelling" in problem_statement_content):
            return {
                'criteria_id': criterion['id'],
                'criteria_name': criterion['name'],
                'section_id': section.get('db_id'),
                'section_name': section['name'],
                'status': criterion.get('severity', 'violation'),
                'message': criterion.get('error_message', f"De sectie 'Onderzoeksvragen' lijkt niet duidelijk aan te sluiten op de probleemstelling of mist een expliciete hoofdvraag."),
                'suggestion': criterion.get('fixed_feedback_text', "Zorg voor een duidelijke hoofdvraag die direct voortvloeit uit de probleemstelling en controleer de consistentie."),
                'location': f"Sectie: {section['name']}",
                'confidence': 0.6,
                'color': criterion.get('color', '#FF0000')
            }
        else:
            return {
                'criteria_id': criterion['id'],
                'criteria_name': criterion['name'],
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
    criterion_name = criterion['name'].lower()

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
                    'criteria_id': criterion['id'],
                    'criteria_name': criterion['name'],
                    'section_id': None, # Geldt voor hele document
                    'section_name': 'Hele Document',
                    'status': criterion.get('severity', 'violation'),
                    'message': criterion.get('error_message', f"De sectie 'Methode' lijkt vóór de sectie 'Inleiding' te staan, wat afwijkt van de verwachte volgorde."),
                    'suggestion': criterion.get('fixed_feedback_text', "Controleer de volgorde van de secties. Zorg dat de Inleiding voor de Methode-sectie komt."),
                    'location': 'Document Structuur',
                    'confidence': 0.9,
                    'color': criterion.get('color', '#FF0000')
                }
            else:
                feedback = {
                    'criteria_id': criterion['id'],
                    'criteria_name': criterion['name'],
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
                'criteria_id': criterion['id'],
                'criteria_name': criterion['name'],
                'section_id': None,
                'section_name': 'Hele Document',
                'status': 'info',
                'message': f"Sectievolgorde check voor '{criterion['name']}' kon niet volledig worden uitgevoerd; één of meer relevante secties niet gevonden.",
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
        if not criterion.get('is_enabled', True):
            continue
        
        # Bepaal welke secties relevant zijn voor dit specifieke criterium.
        # document_type_id is hier essentieel om de juiste criterium-sectie mappings te vinden.
        # Let op: de 'document_only' scope wordt hier gefilterd en apart behandeld.
        if criterion['application_scope'] == 'document_only':
            feedback_item = check_document_wide_criterion(criterion, doc_content, all_sections_for_processing)
            if feedback_item:
                # Frequentiebeperking voor document-wide checks
                current_count = occurrences_count.get((criterion['id'], 'document'), 0)
                max_mentions = criterion.get('max_mentions_per', 0)

                if feedback_item['status'] == 'ok' or max_mentions == 0 or current_count < max_mentions:
                    feedback_items.append(feedback_item)
                    occurrences_count[(criterion['id'], 'document')] = current_count + 1
            continue # Ga naar het volgende criterium, dit is afgehandeld

        # Voor alle andere scopes (all, specific_sections, exclude_sections)
        # De 'document' virtuele sectie is al afgehandeld voor 'document_only' criteria
        # en wordt hier expliciet uitgesloten om dubbele checks te voorkomen.
        applicable_sections = get_applicable_sections(criterion, [s for s in all_sections_for_processing if s['identifier'] != 'document'], document_type_id, db_connection) 
        
        # Itereer over elke toepasselijke sectie om het criterium te controleren
        for section in applicable_sections:
            feedback_item = None
            
            # Roep de juiste check-functie aan op basis van het rule_type van het criterium
            if criterion['rule_type'] == 'tekstueel':
                feedback_item = check_textual_criterion(criterion, section)
            elif criterion['rule_type'] == 'structureel':
                feedback_item = check_structural_criterion(criterion, section)
            elif criterion['rule_type'] == 'inhoudelijk':
                # Voor inhoudelijke checks, geef ook alle secties mee voor context
                feedback_item = check_content_criterion(criterion, section, all_sections_for_processing)
            # Voeg hier meer rule_types toe

            # --- Start Frequentiebeperkingslogica ---
            if feedback_item: # Alleen doorgaan als er daadwerkelijk een feedback_item is gegenereerd
                
                # Bepaal de 'scope_key' voor het bijhouden van de tellingen.
                # Dit is afhankelijk van de 'frequency_unit' van het criterium.
                scope_key = ''
                frequency_unit = criterion.get('frequency_unit')

                if frequency_unit == 'document': # Als de frequentie op document-niveau is, ondanks sectie-check
                    scope_key = 'document'
                elif frequency_unit == 'section':
                    if section.get('identifier'):
                        scope_key = section['identifier']
                    else:
                        print(f"Waarschuwing: Sectie mist 'identifier' voor criterium '{criterion.get('name', 'Onbekend')}'. Valt terug op document-scope voor frequentiebeperking.")
                        scope_key = 'document_fallback_section'
                elif frequency_unit == 'paragraph':
                    # Voor paragraaf-niveau frequentiebeperking moet de feedback-item al info bevatten over
                    # welke specifieke paragraaf de trigger was. Dit is complexer en vereist
                    # een diepere integratie met de parsing/herkenning van paragrafen.
                    # Voor nu een simplificatie, valt terug op sectie als de kleinste eenheid.
                    if section.get('identifier'):
                        scope_key = f"paragraph_in_{section['identifier']}" # Meer specifieke scope
                    else:
                        print(f"Waarschuwing: Sectie mist 'identifier' voor paragraaf-criterium '{criterion.get('name', 'Onbekend')}'. Valt terug op document-scope voor frequentiebeperking.")
                        scope_key = 'document_fallback_paragraph'
                else:
                    print(f"Waarschuwing: Onbekende of ontbrekende 'frequency_unit' '{frequency_unit}' voor criterium '{criterion.get('name', 'Onbekend')}'. Valt terug op document-scope.")
                    scope_key = 'document_fallback_unknown_unit'

                # Haal de huidige telling op voor dit criterium binnen de gedefinieerde scope
                current_count = occurrences_count.get((criterion['id'], scope_key), 0)

                # Haal het maximale aantal toegestane vermeldingen op (0 betekent onbeperkt)
                max_mentions = criterion.get('max_mentions_per', 0) 

                # Logica voor het al dan niet toevoegen van het feedback item
                if feedback_item['status'] == 'ok':
                    feedback_items.append(feedback_item)
                    occurrences_count[(criterion['id'], scope_key)] = current_count + 1
                else: # Voor 'violation', 'warning', 'info' statussen, controleer de frequentielimiet
                    if max_mentions == 0: # 0 betekent onbeperkt aantal vermeldingen
                        feedback_items.append(feedback_item)
                        occurrences_count[(criterion['id'], scope_key)] = current_count + 1
                    elif current_count < max_mentions:
                        feedback_items.append(feedback_item)
                        occurrences_count[(criterion['id'], scope_key)] = current_count + 1
                    else:
                        # Limiet is bereikt, dit feedback item wordt overgeslagen
                        continue 
            # --- Einde Frequentiebeperkingslogica ---

    return feedback_items

