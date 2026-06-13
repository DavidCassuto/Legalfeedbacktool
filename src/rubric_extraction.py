# src/rubric_extraction.py
"""
Rubric-extractie uit een Excel-beoordelingsformulier (.xlsx).

De daadwerkelijke rubric-tekst (de criteria/niveaubeschrijvingen) staat in deze
formulieren NIET in cellen maar in DrawingML-tekstvakken (xl/drawings/drawingN.xml).
Per werkblad (= beroepsproduct: PvA, Analyse, Advies, Ontwerp, Fabricaat, Eindgesprek)
hoort één drawing met de volledige rubric.

Deze module koppelt elk werkblad aan zijn drawing en levert leesbare rubric-tekst,
zodat de gebruiker alleen het Excel-bestand hoeft te uploaden (niets plakken).
"""

import re
import zipfile
from html import unescape
from xml.etree import ElementTree as ET

_NS = {
    'wb':  'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'r':   'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'rel': 'http://schemas.openxmlformats.org/package/2006/relationships',
    'a':   'http://schemas.openxmlformats.org/drawingml/2006/main',
}
_DRAWING_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing'


def _drawing_text(xml_bytes: bytes) -> str:
    """Haal leesbare tekst uit een drawingN.xml: regel per a:p-paragraaf,
    lege regel tussen tekstvakken (shapes)."""
    root = ET.fromstring(xml_bytes)
    shapes_out = []
    # Itereer over alle shapes met tekst (xdr:sp); val terug op hele boom als nodig
    for sp in root.iter():
        tag = sp.tag.split('}')[-1]
        if tag != 'txBody':
            continue
        paras = []
        for p in sp.findall('a:p', _NS):
            runs = [t.text or '' for t in p.findall('.//a:t', _NS)]
            line = ''.join(runs).strip()
            if line:
                paras.append(line)
        block = '\n'.join(paras).strip()
        if block:
            shapes_out.append(block)
    return '\n\n'.join(shapes_out).strip()


def extract_rubric_tabs(xlsx_path: str) -> dict[str, str]:
    """
    Returns {werkblad_naam: rubric_tekst} voor elk werkblad dat een rubric-drawing heeft.
    Werkbladen zonder bruikbare rubric-tekst worden overgeslagen.
    """
    with zipfile.ZipFile(xlsx_path) as z:
        names = set(z.namelist())

        # 1. Werkbladen + volgorde uit workbook.xml
        wb = ET.fromstring(z.read('xl/workbook.xml'))
        sheets = []  # (naam, r:id)
        for s in wb.find('wb:sheets', _NS):
            rid = s.get('{%s}id' % _NS['r'])
            sheets.append((s.get('name'), rid))

        # 2. r:id -> worksheets/sheetN.xml
        wb_rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        rid_to_target = {}
        for rel in wb_rels:
            rid_to_target[rel.get('Id')] = rel.get('Target')

        result: dict[str, str] = {}
        for naam, rid in sheets:
            target = rid_to_target.get(rid, '')
            if not target:
                continue
            sheet_path = 'xl/' + target.lstrip('/').replace('xl/', '', 1) \
                if not target.startswith('xl/') else target
            # Normaliseer naar 'xl/worksheets/sheetN.xml'
            sheet_file = 'xl/' + target if not target.startswith('xl/') else target
            sheet_file = sheet_file.replace('xl/xl/', 'xl/')
            base = sheet_file.split('/')[-1]                       # sheetN.xml
            rels_file = f'xl/worksheets/_rels/{base}.rels'
            if rels_file not in names:
                continue

            # 3. drawing-relationship volgen
            sheet_rels = ET.fromstring(z.read(rels_file))
            drawing_target = None
            for rel in sheet_rels:
                if rel.get('Type') == _DRAWING_REL:
                    drawing_target = rel.get('Target')
                    break
            if not drawing_target:
                continue
            drawing_file = 'xl/' + drawing_target.replace('../', '')
            if drawing_file not in names:
                continue

            text = _drawing_text(z.read(drawing_file))
            text = unescape(text)
            # Vervang het veelvoorkomende mojibake-vraagteken door spatie
            text = text.replace('�', ' ').replace('\x00', '')
            text = re.sub(r'[ \t]+', ' ', text)
            if len(text) >= 200:   # zinvolle rubric, geen losse selector-knop
                result[naam] = text.strip()

        return result


def list_product_tabs(xlsx_path: str) -> list[str]:
    """Namen van werkbladen met een bruikbare rubric (voor de keuzelijst)."""
    return list(extract_rubric_tabs(xlsx_path).keys())


def build_rubric_text(xlsx_path: str, product_type: str | None = None) -> tuple[str, list[str]]:
    """
    Bouw de rubric-tekst voor de LLM.

    - product_type opgegeven en gevonden -> alleen die tab.
    - anders (auto-detect) -> alle tabs, gelabeld, zodat de LLM zelf het juiste
      beroepsproduct kan kiezen.

    Returns (rubric_text, beschikbare_tab_namen).
    """
    tabs = extract_rubric_tabs(xlsx_path)
    available = list(tabs.keys())
    if not tabs:
        return '', available

    if product_type:
        pt = product_type.strip().lower()
        for naam, text in tabs.items():
            if pt and pt in naam.strip().lower():
                return f"=== Rubric voor beroepsproduct: {naam} ===\n{text}", available

    # Auto: alle tabs gelabeld
    blocks = [f"=== Rubric voor beroepsproduct: {naam} ===\n{text}"
              for naam, text in tabs.items()]
    return '\n\n'.join(blocks), available
