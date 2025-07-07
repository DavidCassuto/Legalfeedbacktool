import re
from docx import Document # pip install python-docx

def parse_document(file_path: str) -> tuple[str, list[str], list[dict]]:
    """
    Parses een document (TXT of DOCX) en extraheert de volledige tekst,
    paragrafen en kopjes met hun niveaus en karakterposities.

    Args:
        file_path: Het pad naar het document.

    Returns:
        Een tuple met:
        - full_text (str): De volledige tekst van het document.
        - paragraphs (list[str]): Een lijst van afzonderlijke paragrafen.
        - all_headings (list[dict]): Een lijst van herkende kopjes met text, level, start_char, end_char.
    """
    full_text = ""
    paragraphs = []
    all_headings = []
    current_char_offset = 0

    if file_path.endswith('.txt'):
        with open(file_path, 'r', encoding='utf-8') as f:
            full_text = f.read()
            
            # Robuuste paragraafsplitsing voor TXT (op 1 of meer lege regels)
            raw_paragraphs = re.split(r'\n\s*\n+', full_text)
            paragraphs = [p.strip() for p in raw_paragraphs if p.strip()]

            # Kopjesherkenning voor TXT (heuristisch, kan verbeterd worden)
            # Simpele aanpak: regels die beginnen met nummering (1., 1.1.) of hoofdletterige, korte zinnen
            lines = full_text.split('\n')
            for line_idx, line in enumerate(lines):
                line_stripped = line.strip()
                if not line_stripped: # Sla lege regels over
                    continue

                # Heuristische heading detectie voor TXT:
                # 1. Start met nummering (bv. 1., 1.1. etc.)
                # 2. Helemaal in hoofdletters en relatief kort
                # 3. Specifieke sleutelwoorden (Hoofdstuk, Bijlage)
                
                is_heading = False
                level = 0
                if re.match(r'^\d+(\.\d+)*\s+[A-Z].*', line_stripped): # Nummering gevolgd door hoofdletter
                    is_heading = True
                    level = len(re.match(r'^(\d+)(\.\d+)*', line_stripped).group(0).split('.'))
                elif (line_stripped.isupper() and len(line_stripped) < 80 and len(line_stripped.split()) > 1): # Korte, hoofdletterige zin
                    is_heading = True
                    level = 1
                elif re.match(r'^(hoofdstuk|bijlage|bibliografie)', line_stripped, re.IGNORECASE):
                    is_heading = True
                    level = 1 # Standaard level voor deze types

                if is_heading:
                    start_char = full_text.find(line, current_char_offset) # Zoek vanaf huidige offset
                    end_char = start_char + len(line)
                    all_headings.append({
                        'text': line_stripped,
                        'level': level if level > 0 else 1, # Zorg dat level minstens 1 is
                        'start_char': start_char,
                        'end_char': end_char
                    })
                    current_char_offset = end_char # Update offset

    elif file_path.endswith('.docx'):
        doc = Document(file_path)
        
        # Reset current_char_offset voor docx, want full_text wordt hier opgebouwd
        current_char_offset = 0 
        
        for para in doc.paragraphs:
            para_text = para.text # Ruwe tekst van de paragraaf
            paragraphs.append(para_text.strip())
            full_text += para_text + '\n' # Voeg een newline toe na elke paragraaf voor consistentie

            # Docx headings hebben een ingebouwde stijl-informatie
            if para.style and para.style.name.startswith('Heading'):
                try:
                    level = int(para.style.name.replace('Heading ', ''))
                except ValueError:
                    level = 1 # Fallback als de stijl niet 'Heading X' is, maar wel een Heading
                
                # Zoek de exacte start/end chars van de heading in de full_text
                # Gebruik de current_char_offset om dubbele matches te voorkomen en sneller te zoeken
                start_char_candidate = full_text.find(para_text, current_char_offset)
                if start_char_candidate != -1: # Zorg dat de tekst gevonden is
                    start_char = start_char_candidate
                    end_char = start_char + len(para_text)
                    all_headings.append({
                        'text': para_text.strip(),
                        'level': level,
                        'start_char': start_char,
                        'end_char': end_char
                    })
                    # Update current_char_offset om te voorkomen dat dezelfde tekst opnieuw wordt gevonden
                    current_char_offset = end_char 
                else:
                    # Als de heading text om een of andere reden niet direct gevonden wordt
                    # (bijv. door whitespace verschillen), schat de positie dan.
                    print(f"Waarschuwing: Kon heading '{para_text[:30]}' niet exact vinden in full_text. Schat positie.")
                    all_headings.append({
                        'text': para_text.strip(),
                        'level': level,
                        'start_char': current_char_offset, # Neem huidige offset als start
                        'end_char': current_char_offset + len(para_text)
                    })
                    current_char_offset += len(para_text) + 1 # Update met lengte van para + newline

            # Als het geen heading is, update alleen de current_char_offset voor de volgende iteratie
            else:
                current_char_offset += len(para_text) + 1 # +1 voor de toegevoegde newline

    else:
        print(f"Fout: Ongeldig bestandstype '{file_path}'. Alleen .txt en .docx worden ondersteund.")
        return "", [], []

    return full_text, [p for p in paragraphs if p], all_headings # Filter lege paragrafen

