"""
test_run.py  -  DocuCheck snelle analysetest (CLI)

Gebruik:
    python src/test_run.py                  # meest recente document
    python src/test_run.py 17               # document op ID
    python src/test_run.py --short          # geen OK-items tonen
    python src/test_run.py 17 --short

Toont: gevonden secties, welke criteria draaiden, wat de uitkomst was,
en welke criteria NIET draaiden omdat hun sectie niet herkend werd.
"""

import sys
import os
import json
import sqlite3
import time

# Pad instellen zodat imports werken (zelfde als main.py)
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, THIS_DIR)

import db_utils
from analysis import document_parsing, section_recognition, criterion_checking

# ------------------------------------------------------------------ config
DB_PATH = os.path.join(THIS_DIR, '..', 'instance', 'documents.db')

# ANSI kleuren (werken in Windows Terminal / PowerShell 7+)
RED    = '\033[91m'
YELLOW = '\033[93m'
GREEN  = '\033[92m'
BLUE   = '\033[94m'
GRAY   = '\033[90m'
BOLD   = '\033[1m'
RESET  = '\033[0m'

SEP = '-' * 72


def color_status(status):
    if status in ('violation', 'error'):
        return f'{RED}{status}{RESET}'
    if status == 'warning':
        return f'{YELLOW}{status}{RESET}'
    if status == 'ok':
        return f'{GREEN}{status}{RESET}'
    if status == 'info':
        return f'{BLUE}{status}{RESET}'
    return status


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]
    show_ok = '--short' not in flags

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Bepaal document
    if args:
        doc_id = int(args[0])
        doc = conn.execute('SELECT * FROM documents WHERE id=?', (doc_id,)).fetchone()
    else:
        doc = conn.execute('SELECT * FROM documents ORDER BY id DESC LIMIT 1').fetchone()

    if not doc:
        print('Geen document gevonden.')
        sys.exit(1)

    doc_id = doc['id']
    print(f'\n{BOLD}=== DocuCheck Testrun ==={RESET}')
    print(f'Document : {doc["original_filename"]} (ID {doc_id})')
    print(f'Type-ID  : {doc["document_type_id"]}')
    print(f'Status   : {doc["analysis_status"]}')
    print(f'Bestand  : {doc["file_path"]}')

    if not os.path.exists(doc['file_path']):
        print(f'{RED}BESTAND NIET GEVONDEN: {doc["file_path"]}{RESET}')
        sys.exit(1)

    doc_type = conn.execute('SELECT * FROM document_types WHERE id=?', (doc['document_type_id'],)).fetchone()
    print(f'Doctype  : {doc_type["name"] if doc_type else "?"}\n')

    # ---- 1. Parsen
    print(f'{BOLD}1. Document parsen...{RESET}')
    t0 = time.time()
    full_text, paragraphs, headings = document_parsing.parse_document(doc['file_path'])
    print(f'   {len(paragraphs)} paragrafen, {len(headings)} headings  ({time.time()-t0:.1f}s)')

    # ---- 2. Secties verwacht
    expected_sections_metadata = conn.execute(
        '''SELECT DISTINCT s.id, s.name, s.level, s.identifier, s.is_required,
                  s.parent_id, s.alternative_names, s.order_index
           FROM sections s
           LEFT JOIN document_type_sections dts ON s.id = dts.section_id
           WHERE s.document_type_id = :dt_id
              OR dts.document_type_id = :dt_id
              OR (s.document_type_id IS NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM document_type_sections dts2
                      WHERE dts2.section_id = s.id
                  ))
           ORDER BY CASE WHEN s.document_type_id IS NULL THEN 0 ELSE 1 END, s.order_index''',
        {'dt_id': doc['document_type_id']}
    ).fetchall()

    # ---- 3. Sectieherkenning
    print(f'\n{BOLD}2. Sectieherkenning...{RESET}')
    t0 = time.time()
    recognized_sects, formatting_warnings = section_recognition.recognize_and_enrich_sections(
        full_text, paragraphs, headings, expected_sections_metadata
    )
    print(f'   Klaar in {time.time()-t0:.1f}s')

    if formatting_warnings:
        for fw in formatting_warnings:
            print(f'   {YELLOW}[OPMAAKWAARSCHUWING]{RESET} {fw.get("text_preview","")[:80]}')

    print(f'\n{BOLD}--- GEVONDEN SECTIES ---{RESET}')
    not_found = []
    for s in recognized_sects:
        found = s.get('found', False)
        wc = s.get('word_count', 0)
        name = s.get('name', '?')
        sid = s.get('db_id', '?')
        conf = s.get('confidence', 0) or 0
        if found:
            print(f'   {GREEN}[OK]{RESET}  [{sid:>4}] {name:<35} {wc:>5} woorden  conf={conf:.0%}')
        else:
            print(f'   {RED}[--]{RESET}  [{sid:>4}] {name:<35} NIET GEVONDEN')
            not_found.append(sid)

    # ---- 4. Criteria
    print(f'\n{BOLD}3. Criteria ophalen...{RESET}')
    criteria_list = db_utils.get_criteria_for_document_type(conn, doc['document_type_id'])
    print(f'   {len(criteria_list)} criteria voor dit documenttype')

    # ---- 5. Criteria die NIET zullen draaien (sectie niet gevonden)
    skipped_criteria = []
    for crit in criteria_list:
        scope = crit.get('application_scope', '')
        if scope in ('all', 'document_only'):
            continue
        cid = crit.get('id')
        mappings = conn.execute(
            'SELECT section_id, is_excluded FROM criteria_section_mappings WHERE criteria_id=?', (cid,)
        ).fetchall()
        if scope == 'specific_sections':
            # Draait alleen als minstens één gekoppelde sectie is gevonden
            runs_on = [m['section_id'] for m in mappings
                       if not m['is_excluded'] and m['section_id'] not in not_found]
            if not runs_on:
                skipped_criteria.append(crit)
        elif scope == 'exclude_sections':
            # Draait op alle gevonden secties die NIET uitgesloten zijn
            excluded = {m['section_id'] for m in mappings if m['is_excluded']}
            runs_on = [s for s in recognized_sects
                       if s.get('found') and s.get('db_id') not in excluded]
            if not runs_on:
                skipped_criteria.append(crit)

    if skipped_criteria:
        print(f'\n{BOLD}{YELLOW}--- CRITERIA DIE NIET DRAAIEN (sectie niet gevonden) ---{RESET}')
        for c in skipped_criteria:
            cid = c.get('id','?')
            name = c.get('name','?')
            scope = c.get('application_scope','?')
            mps = conn.execute(
                '''SELECT s.name FROM criteria_section_mappings csm
                   JOIN sections s ON s.id=csm.section_id
                   WHERE csm.criteria_id=? AND csm.is_excluded=0''', (cid,)
            ).fetchall()
            sec_names = ', '.join(m['name'] for m in mps)
            print(f'   {YELLOW}[SKIP]{RESET} [{cid:>3}] {name:<45}  --> secties: {sec_names}')

    # ---- 6. Feedback genereren
    print(f'\n{BOLD}4. Feedback genereren...{RESET}')
    t0 = time.time()
    feedback = criterion_checking.generate_feedback(
        full_text,
        recognized_sects,
        criteria_list,
        conn,
        doc_id,
        doc['document_type_id']
    )
    elapsed = time.time() - t0
    print(f'   {len(feedback)} feedback-items in {elapsed:.1f}s')

    # ---- 7. Resultaten tonen
    print(f'\n{BOLD}--- FEEDBACK RESULTATEN ---{RESET}')
    items_shown = 0
    for item in feedback:
        status = item.get('status', '?')
        if not show_ok and status == 'ok':
            continue
        cid   = item.get('criteria_id', '?')
        cname = item.get('criteria_name', '?')
        sname = item.get('section_name', '?')
        msg   = item.get('message', '')
        sugg  = item.get('suggestion', '')
        snip  = item.get('offending_snippet', '')

        print(f'\n  {color_status(status)}  [{cid}] {BOLD}{cname}{RESET}')
        print(f'  Sectie : {sname}')
        print(f'  Melding: {msg[:200]}')
        if sugg:
            print(f'  Suggestie: {GRAY}{sugg[:150]}{RESET}')
        if snip:
            print(f'  Snippet: {GRAY}"{snip[:100]}"{RESET}')
        items_shown += 1

    if not show_ok:
        total_ok = sum(1 for f in feedback if f.get('status') == 'ok')
        if total_ok:
            print(f'\n  {GRAY}({total_ok} OK-items weggelaten, gebruik zonder --short om ze te zien){RESET}')

    # ---- 8. Samenvatting
    from collections import Counter
    counts = Counter(f.get('status','?') for f in feedback)
    print(f'\n{SEP}')
    print(f'{BOLD}SAMENVATTING{RESET}')
    print(f'  Violations : {RED}{counts.get("violation",0)}{RESET}')
    print(f'  Warnings   : {YELLOW}{counts.get("warning",0)}{RESET}')
    print(f'  Info       : {BLUE}{counts.get("info",0)}{RESET}')
    print(f'  OK         : {GREEN}{counts.get("ok",0)}{RESET}')
    print(f'  Criteria overgeslagen: {len(skipped_criteria)}')
    print(SEP + '\n')

    conn.close()


if __name__ == '__main__':
    main()
