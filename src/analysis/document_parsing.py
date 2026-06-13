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

        # Helper: verwerk één paragraaf-object
        def _verwerk_para(para):
            nonlocal full_text, current_char_offset
            para_text = para.text
            paragraphs.append(para_text.strip())

            style_name = para.style.name if para.style else 'Normal'
            is_heading = style_name.startswith('Heading')
            is_empty   = not para_text.strip()

            if is_heading or is_empty:
                full_text += para_text + '\n'
            else:
                full_text += para_text + '\n\n'

            if is_heading:
                try:
                    level = int(para.style.name.replace('Heading ', ''))
                except ValueError:
                    level = 1
                start_char_candidate = full_text.find(para_text, current_char_offset)
                if start_char_candidate != -1:
                    start_char = start_char_candidate
                    end_char   = start_char + len(para_text)
                    all_headings.append({
                        'text': para_text.strip(),
                        'level': level,
                        'start_char': start_char,
                        'end_char': end_char
                    })
                    current_char_offset = end_char
                else:
                    print(f"Waarschuwing: Kon heading '{para_text[:30]}' niet exact vinden in full_text. Schat positie.")
                    all_headings.append({
                        'text': para_text.strip(),
                        'level': level,
                        'start_char': current_char_offset,
                        'end_char': current_char_offset + len(para_text)
                    })
                    current_char_offset += len(para_text) + 1
            else:
                current_char_offset += len(para_text) + 1

        # Helper: verwerk een tabel — voeg cel-tekst toe als leesbare blokken
        def _verwerk_tabel(tabel):
            nonlocal full_text, current_char_offset
            for rij in tabel.rows:
                cel_teksten = [cel.text.strip() for cel in rij.cells]
                # Dedupleer samengevoegde cellen (python-docx herhaalt merged cells)
                uniek = []
                for t in cel_teksten:
                    if not uniek or t != uniek[-1]:
                        uniek.append(t)
                rij_tekst = ' | '.join(t for t in uniek if t)
                if rij_tekst:
                    full_text += rij_tekst + '\n\n'
                    paragraphs.append(rij_tekst)
                    current_char_offset += len(rij_tekst) + 2

        # Itereer body-elementen IN VOLGORDE (paragrafen én tabellen)
        from docx.oxml.ns import qn
        from docx.table import Table as DocxTable
        from docx.text.paragraph import Paragraph as DocxParagraph

        for kind in doc.element.body:
            tag = kind.tag.split('}')[-1] if '}' in kind.tag else kind.tag
            if tag == 'p':
                _verwerk_para(DocxParagraph(kind, doc))
            elif tag == 'tbl':
                _verwerk_tabel(DocxTable(kind, doc))

        # Voetnoten uitlezen via directe ZIP/XML-toegang
        # (python-docx biedt geen footnotes_part attribuut)
        try:
            import zipfile
            from lxml import etree as _etree
            WNS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
            voetnoten = []
            with zipfile.ZipFile(file_path, 'r') as zf:
                for xml_naam in ('word/footnotes.xml', 'word/endnotes.xml'):
                    if xml_naam not in zf.namelist():
                        continue
                    root = _etree.fromstring(zf.read(xml_naam))
                    label = 'Voetnoot' if 'footnote' in xml_naam else 'Eindnoot'
                    teller = 1
                    for node in root.findall(f'{{{WNS}}}footnote') + root.findall(f'{{{WNS}}}endnote'):
                        # Sla separator/continuation-noten over op basis van type, niet id
                        fn_type = node.get(f'{{{WNS}}}type', 'normal')
                        if fn_type != 'normal':
                            continue
                        tekst_delen = [t.text for t in node.findall(f'.//{{{WNS}}}t') if t.text]
                        fn_tekst = ''.join(tekst_delen).strip()
                        if fn_tekst:
                            voetnoten.append(f'[{label} {teller}] {fn_tekst}')
                            teller += 1
            if voetnoten:
                blok = '[VOETNOTEN/EINDNOTEN]\n' + '\n'.join(voetnoten) + '\n[/VOETNOTEN/EINDNOTEN]'
                full_text += '\n\n' + blok + '\n\n'
                paragraphs.append(blok)
                current_char_offset += len(blok) + 4
        except Exception:
            pass  # Geen voetnoten of niet toegankelijk — geen probleem

    else:
        print(f"Fout: Ongeldig bestandstype '{file_path}'. Alleen .txt en .docx worden ondersteund.")
        return "", [], []

    return full_text, [p for p in paragraphs if p], all_headings # Filter lege paragrafen

