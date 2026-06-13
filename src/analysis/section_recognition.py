import re
import json # Nodig om alternative_names te parsen

# Nederlandse stopwoorden die uitgesloten worden bij fuzzy matching
_NL_STOPWORDS = {
    'de', 'het', 'een', 'en', 'in', 'op', 'te', 'van', 'voor', 'met', 'zijn', 'er',
    'dat', 'die', 'dit', 'aan', 'door', 'over', 'bij', 'als', 'om', 'maar', 'ook',
    'tot', 'uit', 'naar', 'we', 'je', 'ze', 'hij', 'zij', 'ik', 'dan', 'nog', 'wel',
    'niet', 'geen', 'kan', 'wordt', 'werd', 'heeft', 'had', 'was', 'ben', 'der', 'des',
}

def _meaningful_words(text: str) -> set:
    """Haal betekenisvolle woorden op (min. 3 tekens, geen stopwoorden)."""
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    return {w for w in words if w not in _NL_STOPWORDS}

def _words_overlap(set_a: set, set_b: set) -> int:
    """Tel overlappende woorden, inclusief woordvarianten via prefix-matching (≥5 tekens).
    Behandelt Nederlandse woordbuiging zoals 'juridisch'/'juridische'."""
    exact = set_a & set_b
    # Voeg prefix-matches toe voor woorden die nog niet exact matchen
    unmatched_a = set_a - exact
    unmatched_b = set_b - exact
    prefix_matches = 0
    for wa in unmatched_a:
        if len(wa) < 5:
            continue
        for wb in unmatched_b:
            if len(wb) < 5:
                continue
            prefix_len = min(len(wa), len(wb))
            if wa[:prefix_len] == wb[:prefix_len] or wb.startswith(wa[:6]) or wa.startswith(wb[:6]):
                prefix_matches += 1
                break
    return len(exact) + prefix_matches

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
    formatting_warnings = []   # Misformateerde headings (bodytekst met heading-stijl)

    # Maak een dictionary van expected_sections_metadata voor snelle lookup op identifier.
    # Zorg ook dat alternative_names altijd een Python-lijst is (de DB slaat het op als JSON-string).
    expected_sections_dict = {}
    for s in expected_sections_metadata:
        s_dict = dict(s)
        alt = s_dict.get('alternative_names', None)
        if isinstance(alt, str):
            try:
                s_dict['alternative_names'] = json.loads(alt)
            except (json.JSONDecodeError, ValueError):
                s_dict['alternative_names'] = []
        elif not isinstance(alt, list):
            s_dict['alternative_names'] = []
        expected_sections_dict[s_dict['identifier']] = s_dict

    # Sorteer headings op start_char voor sequentiële verwerking
    # Filter bodytekst met verkeerde heading-stijl eruit (>15 woorden = geen echte heading)
    # zodat ze ook de sectiegrenzen niet verstoren
    real_headings = []
    for h in sorted(all_headings, key=lambda x: x['start_char']):
        h_cleaned = re.sub(r'^\s*\d+(\.\d+)*\.?\s*', '', h['text'].lower()).strip()
        h_cleaned = re.sub(r'^(hoofdstuk|bijlage|appendix|sectie)\s*[\d.]*\s*', '', h_cleaned, flags=re.IGNORECASE).strip()
        if len(h_cleaned.split()) > 15:
            print(f"  [PRE-FILTER] Heading genegeerd (bodytekst met verkeerde opmaak, {len(h_cleaned.split())} woorden): '{h['text'][:60]}...'")
        else:
            real_headings.append(h)
    sorted_headings = real_headings

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
        cleaned_heading_text = re.sub(r'^\s*\d+(\.\d+)*\.?\s*', '', heading_text_lower).strip()
        
        # Stap 2: Verwijder algemene hoofdstuk/bijlage-prefixen ALLEEN als er daarna nog tekst volgt
        # Dit voorkomt dat "Hoofdstuk 4" een lege string wordt.
        chapter_prefix_regex = r'^(?:hoofdstuk|bijlage)\s+\d+\s*[:\.]?\s*'
        match_prefix = re.match(chapter_prefix_regex, cleaned_heading_text, re.IGNORECASE)
        remaining_content = ''  # default; wordt ingevuld als er een hoofdstuk-prefix is

        if match_prefix:
            # Als er na de prefix nog inhoud is (group(1) is alles na de match), gebruik dan die inhoud
            remaining_content = cleaned_heading_text[match_prefix.end():].strip()
            if remaining_content:
                cleaned_heading_text = remaining_content
            # Anders, als er geen inhoud na de prefix is (bijv. "Hoofdstuk 4"),
            # dan blijft 'cleaned_heading_text' ongewijzigd van voor deze stap (bijv. "hoofdstuk 4").
            # Dit is de gewenste situatie om te matchen met 'Hoofdstuk Algemeen'.
        
        print(f"  Gereinigde koptekst: '{cleaned_heading_text}'")

        # Detecteer samengestelde nummering (bv. "3.1.", "2.4.1.") — dit is een sub-heading
        # die NIET via alias/fuzzy mag matchen op een top-level sectie
        _has_compound_number = bool(re.match(r'^\s*\d+\.\d+', heading['text']))

        # LENGTEFILTER: teksten langer dan 15 woorden zijn geen echte headings
        # maar bodytekst die per ongeluk een heading-stijl heeft gekregen in Word.
        if len(cleaned_heading_text.split()) > 15:
            preview = heading.get('text', cleaned_heading_text)[:80]
            print(f"  --> GENEGEERD: tekst heeft {len(cleaned_heading_text.split())} woorden (>15), waarschijnlijk bodytekst met verkeerde opmaak.")
            formatting_warnings.append({
                'type': 'misformatted_heading',
                'text_preview': preview,
            })
            continue

        # VERBETERDE MATCHING LOGICA:
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
                        # Sla lege of alleen-witruimte aliassen over om vals-positieve matches te voorkomen
                        if not alias.strip():
                            continue
                        alias_lower = alias.lower()
                        # Check 1: exacte woordgrens-match (bijv. 'methode' in 'methode juridisch')
                        exact = re.search(r'\b' + re.escape(alias_lower) + r'\b', cleaned_heading_text)
                        # Check 2: prefix-match voor meervouds-/verbuigingsvormen
                        # bijv. alias='onderzoeksmethode' matcht 'onderzoeksmethoden'
                        # Alleen richting: heading-woord begint met de alias (NIET omgekeerd)
                        # — zo voorkomt 'onderzoeksvragen'.startswith('onderzoek') valse matches
                        # Minimale aliaslengte van 7 tekens om korte aliassen uit te sluiten
                        prefix = False
                        if not exact and len(alias_lower) >= 7:
                            heading_words = cleaned_heading_text.split()
                            prefix = any(
                                word.startswith(alias_lower)
                                for word in heading_words
                                if len(word) >= 7
                            )
                        if exact or prefix:
                            # Niveau-compatibiliteitscheck: een sub-heading met samengestelde
                            # nummering (bv. "3.1. Inleiding") mag NIET via alias matchen
                            # op een top-level sectie (verwacht niveau 1).
                            _expected_lvl = es_data.get('level', 0)
                            if (_has_compound_number and _expected_lvl > 0
                                    and heading_level_parsed > _expected_lvl):
                                print(f"  --> Alias match GENEGEERD: sub-heading niveau {heading_level_parsed} "
                                      f"is incompatibel met sectie '{es_data['name']}' op niveau {_expected_lvl}.")
                                continue
                            matched_identifier = es_id
                            match_type = 'alias' if exact else 'alias (prefix-match)'
                            print(f"  --> MATCH ({match_type}) op '{es_data['name']}' via alias '{alias}'.")
                            break
                if matched_identifier:
                    break # Als een match gevonden is, stop met zoeken voor deze heading
        
        # NIEUW: Prioriteit 3: Voor Heading niveau 1, probeer algemene hoofdstuk matching
        if not matched_identifier and heading_level_parsed == 1:
            # Voor niveau 1 headings, probeer te matchen met "Hoofdstuk Algemeen" of andere algemene secties
            for es_id, es_data in expected_sections_dict.items():
                if es_data['identifier'] == 'hoofdstuk_algemeen' or 'hoofdstuk' in es_data['alternative_names']:
                    # Als het een niveau 1 heading is en we hebben geen specifieke match, 
                    # koppel het aan de algemene hoofdstuk sectie
                    matched_identifier = es_id
                    print(f"  --> MATCH (niveau 1 hoofdstuk) op '{es_data['name']}' voor algemene hoofdstukkoppen.")
                    break
        
        # Prioriteit 4: Fuzzy matching op basis van woord-overlap (verbeterd)
        # Eisen: koptekst ≥ 5 tekens, minstens 60% overlap van betekenisvolle woorden.
        # Kies de beste match (hoogste overlap ratio) om vals-positieven te vermijden.
        if not matched_identifier and len(cleaned_heading_text) >= 5:
            heading_words = _meaningful_words(cleaned_heading_text)
            if heading_words:
                best_ratio = 0.0
                best_id = None
                best_name = None
                for es_id, es_data in expected_sections_dict.items():
                    expected_words = _meaningful_words(es_data['name'])
                    if not expected_words:
                        continue
                    overlap_count = _words_overlap(heading_words, expected_words)
                    smaller_set = min(len(heading_words), len(expected_words))
                    if smaller_set > 0:
                        ratio = overlap_count / smaller_set
                        if ratio >= 0.6 and ratio > best_ratio:
                            best_ratio = ratio
                            best_id = es_id
                            best_name = es_data['name']
                if best_id:
                    # Niveau-compatibiliteitscheck ook voor fuzzy matches
                    _best_expected_lvl = expected_sections_dict[best_id].get('level', 0)
                    if (_has_compound_number and _best_expected_lvl > 0
                            and heading_level_parsed > _best_expected_lvl):
                        print(f"  --> Fuzzy match GENEGEERD: sub-heading niveau {heading_level_parsed} "
                              f"is incompatibel met sectie '{best_name}' op niveau {_best_expected_lvl}.")
                    else:
                        matched_identifier = best_id
                        print(f"  --> FUZZY MATCH (woord-overlap {best_ratio:.0%}) op '{best_name}'.")
        
        if matched_identifier:
            start_char = heading['start_char']

            # Bepaal het einde van de sectie.
            # Regel: een sectie eindigt bij de volgende koptekst die:
            #   (a) een HOGER niveau heeft (lager getal, bv. H1 na H2), OF
            #   (b) hetzelfde niveau heeft ÉN een numeriek/hoofdstuk-prefix heeft
            #       (bv. "1.4 Doelstelling" of "Hoofdstuk 2 ...").
            # Onnummerde koppen van hetzelfde niveau (bv. "Hoofdvraag", "Output")
            # worden OVERGESLAGEN — zij zijn sub-koppen binnen de huidige sectie.
            end_char = len(doc_content)

            def _heading_has_structure(h_text: str) -> bool:
                """True als deze koptekst een genummerd of hoofdstuk-prefix heeft."""
                return bool(
                    re.match(r'^\s*\d+[\.\s]', h_text) or
                    re.match(r'^(Hoofdstuk|Bijlage|Appendix)\s+\d+', h_text, re.IGNORECASE)
                )

            for j in range(i + 1, len(sorted_headings)):
                next_heading = sorted_headings[j]
                if next_heading['level'] < heading_level_parsed:
                    # Hoger niveau (bijv. H1 na H2) — altijd sectie-einde
                    end_char = next_heading['start_char']
                    break
                elif next_heading['level'] == heading_level_parsed:
                    # Zelfde niveau — alleen einde als de koptekst gestructureerd is
                    if _heading_has_structure(next_heading['text']):
                        end_char = next_heading['start_char']
                        break
                    # Onnummerd zelfde-niveau kopje → doorzoeken (sub-kop van huidige sectie)

            # Bepaal of deze match via een hoofdstuktitel tot stand is gekomen
            # (bv. "Hoofdstuk 1 Inleiding" → gereduceerd tot "inleiding").
            # Zulke matches zijn PROVISIONEEL: een specifiekere sub-koptekst
            # (bv. "1.1 Inleiding") mag ze later overschrijven.
            _is_provisional = bool(match_prefix and remaining_content)

            if matched_identifier not in found_sections_boundaries:
                found_sections_boundaries[matched_identifier] = {
                    'start_char': start_char,
                    'end_char': end_char,
                    'heading_level': heading_level_parsed,
                    'primary_heading_text': heading['text'],
                    'provisional': _is_provisional,
                }
                prov_label = ' [PROVISIONEEL]' if _is_provisional else ''
                print(f"  Sectie '{expected_sections_dict[matched_identifier]['name']}' gedefinieerd van char {start_char} tot {end_char} (geparsed level: {heading_level_parsed}){prov_label}.")
            elif (found_sections_boundaries[matched_identifier].get('provisional')
                  and not _is_provisional
                  and start_char < found_sections_boundaries[matched_identifier]['end_char']):
                # Overschrijf een provisorische hoofdstuktitel-match met een specifiekere koptekst
                # die BINNEN de char-range van de provisorische match valt (zelfde hoofdstuk).
                # Kopteksten buiten die range (bijv. "2.1 Inleiding" na "Hoofdstuk 1 Inleiding")
                # worden NIET als override beschouwd.
                found_sections_boundaries[matched_identifier] = {
                    'start_char': start_char,
                    'end_char': end_char,
                    'heading_level': heading_level_parsed,
                    'primary_heading_text': heading['text'],
                    'provisional': False,
                }
                print(f"  Sectie '{expected_sections_dict[matched_identifier]['name']}' provisorische match overschreven door specifiekere koptekst '{heading['text']}'.")
            else:
                print(f"  Sectie '{expected_sections_dict[matched_identifier]['name']}' al eerder gevonden; huidige koptekst wordt genegeerd.")
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
            # Sla de originele heading-tekst op zodat inline_word_comments.py
            # de juiste paragraaf kan vinden, ook als sectienaam ≠ heading-tekst
            # (bijv. alias/fuzzy-match: 'Doelstelling' → '1.4 Doel van het onderzoek')
            section_info['heading_text'] = boundary_data['primary_heading_text']

            # Voeg karakterposities toe voor Word comments functionaliteit
            section_info['start_char'] = boundary_data['start_char']
            section_info['end_char'] = boundary_data['end_char']

            # Vul de subkopjes binnen deze sectie (kopjes met een hoger niveau dan de sectie's hoofd-heading)
            for heading in sorted_headings:
                if (boundary_data['start_char'] <= heading['start_char'] < boundary_data['end_char'] and
                    heading['level'] > boundary_data['heading_level']): # Check op daadwerkelijk hoger geparsed niveau
                    section_info['headings'].append(heading)
        
        recognized_sections_list.append(section_info)
    
    # Sorteer de uiteindelijke lijst op order_index en dan op level voor een logische weergave in de UI
    recognized_sections_list.sort(key=lambda x: (x.get('order_index', 999), x.get('level', 999)))

    return recognized_sections_list, formatting_warnings
