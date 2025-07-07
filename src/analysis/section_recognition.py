import re
import json # Nodig om alternative_names te parsen

def recognize_and_enrich_sections(
    doc_content: str,
    paragraphs: list[str],
    all_headings: list[dict], # Nu inclusief start_char en end_char
    expected_sections_metadata: list[dict] # Gedefinieerde secties uit de DB, nu met meer velden
) -> list[dict]:
    """
    Herkent secties in de documentinhoud op basis van kopjes en gedefinieerde metadata,
    en verrijkt deze met hun specifieke content, subkopjes, etc.

    Args:
        doc_content: De volledige tekstuele inhoud van het document.
        paragraphs: Een lijst van afzonderlijke paragrafen uit het document.
        all_headings: Een lijst van alle herkende kopjes met hun metadata
                      (text, level, start_char, end_char).
        expected_sections_metadata: Een lijst van sectie-definities uit de database
                                    (bijv. {'id': 1, 'name': 'Inleiding', 'identifier': 'inleiding',
                                           'is_required': 0, 'parent_id': None, 'alternative_names': '["introductie"]',
                                           'order_index': 10, 'level': 1}).

    Returns:
        Lijst van herkende en verrijkte sectie dictionaries.
        Elke sectie-dict bevat:
        - 'identifier': Unieke identifier van de sectie (uit DB)
        - 'name': Naam van de sectie (uit DB)
        - 'content': De tekstuele inhoud van die specifieke sectie
        - 'found': True/False of de sectie daadwerkelijk is herkend in het document
        - 'db_id': Het ID van de sectie in de database
        - 'word_count': Aantal woorden in de sectie
        - 'confidence': Hoe zeker we zijn van de herkenning
        - 'headings': Lijst van kopjes die binnen deze sectie vallen
        - 'is_required': Of de sectie verplicht is (uit DB)
        - 'level': Het verwachte niveau van de sectie (uit DB)
        - 'order_index': De verwachte volgorde (uit DB)
        - 'parent_id': Het ID van de parent sectie (uit DB)
    """
    recognized_sections_list = []
    
    # Maak een dictionary van expected_sections_metadata voor snelle lookup op identifier
    expected_sections_dict = {s['identifier']: dict(s) for s in expected_sections_metadata}

    # Sorteer headings op start_char voor sequentiële verwerking
    sorted_headings = sorted(all_headings, key=lambda x: x['start_char'])

    # Map om de gevonden secties op hun identifier bij te houden, inclusief hun grenzen
    found_sections_boundaries = {} # {identifier: {'start_char': X, 'end_char': Y, 'heading_level': Z, 'primary_heading_text': 'XYZ'}}

    print("\n--- Sectie Herkenning Debugging ---")
    for i, heading in enumerate(sorted_headings):
        matched_identifier = None
        heading_text_lower = heading['text'].lower()
        heading_level_parsed = heading['level'] # Het niveau zoals geparsed uit Word/TXT
        
        if not heading_text_lower.strip(): # Sla lege kopteksten over
            print(f"\nSla lege koptekst over (Parsed Level {heading_level_parsed}).")
            continue

        print(f"\nVerwerken kopje (Parsed Level {heading_level_parsed}): '{heading['text']}'")
        
        # NIEUW: Eerste opschoonstap: Skip of clean specifieke niet-sectie prefixes zoals "Tabel X" of "Vraagschema X"
        if re.match(r'^(tabel|vraagschema)\s+\d+(\.\d+)*[\s\W]*', heading_text_lower):
            print(f"  Skipping non-section heading based on prefix: '{heading['text']}'")
            continue # Sla deze heading over, want het is waarschijnlijk geen documentsectie

        # Verbeterde opschoonlogica voor kopteksten
        # Stap 1: Verwijder voorloopnummering (e.g., "1.", "1.1.", "1.2.3 ")
        cleaned_heading_text = re.sub(r'^\s*\d+(\.\d+)*\s*', '', heading_text_lower).strip()
        
        # Stap 2: Verwijder algemene hoofdstuk/bijlage-prefixen ALLEEN als er daarna nog tekst volgt
        # Dit voorkomt dat "Hoofdstuk 4" een lege string wordt.
        chapter_prefix_regex = r'^(?:hoofdstuk|bijlage)\s+\d+\s*[:\.]?\s*'
        match_prefix = re.match(chapter_prefix_regex, cleaned_heading_text, re.IGNORECASE)
        
        if match_prefix:
            # Als er na de prefix nog inhoud is (group(1) is alles na de match), gebruik dan die inhoud
            remaining_content = cleaned_heading_text[match_prefix.end():].strip()
            if remaining_content:
                cleaned_heading_text = remaining_content
            # Anders, als er geen inhoud na de prefix is (bijv. "Hoofdstuk 4"),
            # dan blijft 'cleaned_heading_text' ongewijzigd van voor deze stap (bijv. "hoofdstuk 4").
            # Dit is de gewenste situatie om te matchen met 'Hoofdstuk Algemeen'.
        
        print(f"  Gereinigde koptekst: '{cleaned_heading_text}'")

        # Prioriteit 1: Exacte match van de gereinigde koptekst met identifier of naam
        for es_id, es_data in expected_sections_dict.items():
            expected_name_lower = es_data['name'].lower()
            expected_identifier_lower = es_data['identifier'].lower()

            if expected_identifier_lower == cleaned_heading_text or \
               expected_name_lower == cleaned_heading_text:
                matched_identifier = es_id
                print(f"  --> PERFECTE MATCH (naam/identifier) op '{es_data['name']}' via gereinigde tekst/identifier.")
                break
        
        if matched_identifier:
            pass # Gevonden, ga door met boundary bepaling
        else:
            # Prioriteit 2: Match met aliassen (als heel woord) in de gereinigde koptekst
            for es_id, es_data in expected_sections_dict.items():
                if es_data['alternative_names']:
                    for alias in es_data['alternative_names']:
                        # AANGEPAST: re.search ipv re.fullmatch om deelmatches toe te staan
                        # En zorg ervoor dat de alias als heel woord wordt gematcht
                        if re.search(r'\b' + re.escape(alias.lower()) + r'\b', cleaned_heading_text):
                            matched_identifier = es_id
                            print(f"  --> MATCH (alias) op '{es_data['name']}' via alias '{alias}'.")
                            break
                if matched_identifier:
                    break # Als een match gevonden is, stop met zoeken voor deze heading
        
        if matched_identifier:
            start_char = heading['start_char']
            
            # Bepaal het einde van de sectie: tot de start van de volgende heading van gelijk of hoger niveau
            end_char = len(doc_content) # Standaard: einde van het document
            
            for j in range(i + 1, len(sorted_headings)):
                next_heading = sorted_headings[j]
                # Een sectie eindigt wanneer een kop van hetzelfde of een hoger niveau begint.
                # Bijvoorbeeld, H1 eindigt bij de volgende H1. H2 eindigt bij de volgende H2 of een H1.
                if next_heading['level'] <= heading_level_parsed:
                    end_char = next_heading['start_char']
                    break
            
            found_sections_boundaries[matched_identifier] = {
                'start_char': start_char,
                'end_char': end_char,
                'heading_level': heading_level_parsed, # Gebruik het geparsede niveau hier
                'primary_heading_text': heading['text'] # Hoofd-heading van deze sectie
            }
            print(f"  Sectie '{expected_sections_dict[matched_identifier]['name']}' gedefinieerd van char {start_char} tot {end_char} (geparsed level: {heading_level_parsed}).")
        else:
            print(f"  GEEN SECTIE GEVONDEN voor kopje: '{heading['text']}' (geparsed level: {heading_level_parsed})")

    print("\n--- Einde Sectie Herkenning Debugging ---")

    # Vul de recognized_sections_list op basis van de verwachte secties en de gevonden grenzen
    for expected_section_id, expected_section_data in expected_sections_dict.items():
        section_info = {
            'identifier': expected_section_data['identifier'],
            'name': expected_section_data['name'],
            'db_id': expected_section_data['id'],
            'is_required': expected_section_data.get('is_required', False),
            'found': False, # Standaard op False, wordt True als herkend
            'content': '',
            'word_count': 0,
            'confidence': 0.0,
            'headings': [], # Subkopjes binnen deze sectie
            'level': expected_section_data.get('level', 0), # Gebruik het niveau uit de DB
            'order_index': expected_section_data.get('order_index', 0), # Gebruik de volgorde uit de DB
            'parent_id': expected_section_data.get('parent_id', None) # Gebruik parent_id uit de DB
        }

        if expected_section_id in found_sections_boundaries:
            boundary_data = found_sections_boundaries[expected_section_id]
            section_content_raw = doc_content[boundary_data['start_char']:boundary_data['end_char']].strip()
            
            # Verwijder de hoofd-heading tekst van de sectie content zelf, indien aanwezig
            if section_content_raw.startswith(boundary_data['primary_heading_text']):
                section_content = section_content_raw[len(boundary_data['primary_heading_text']):].strip()
            else:
                section_content = section_content_raw

            section_info['content'] = section_content
            section_info['found'] = True
            section_info['confidence'] = 0.95 # Hoge zekerheid als met heading gevonden
            section_info['word_count'] = len(re.findall(r'\b\w+\b', section_content))
            # Het 'level' van de gevonden sectie kan afwijken van het verwachte level uit de DB
            # We zetten hier het 'gevonden_level' in voor debugging/weergave
            section_info['found_level'] = boundary_data['heading_level'] 

            # Vul de subkopjes binnen deze sectie (kopjes met een hoger niveau dan de sectie's hoofd-heading)
            for heading in sorted_headings:
                if (boundary_data['start_char'] <= heading['start_char'] < boundary_data['end_char'] and
                    heading['level'] > boundary_data['heading_level']): # Check op daadwerkelijk hoger geparsed niveau
                    section_info['headings'].append(heading)
        
        recognized_sections_list.append(section_info)
    
    # Sorteer de uiteindelijke lijst op order_index en dan op level voor een logische weergave in de UI
    recognized_sections_list.sort(key=lambda x: (x.get('order_index', 999), x.get('level', 999)))

    return recognized_sections_list
