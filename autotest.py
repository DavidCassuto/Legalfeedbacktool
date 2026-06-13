"""
DocuCheck AutoTest - Automatisch testscript voor de feedback-loop

Gebruik:
    python autotest.py                          -- test met standaard testdocument
    python autotest.py --doc "pad/naar/doc.docx" -- test met specifiek document
    python autotest.py --url http://127.0.0.1:5000 -- ander serveradres

Wat het doet:
    1. Logt in op de Flask-server
    2. Uploadt het testdocument
    3. Wacht op de analyseresultaten
    4. Toont een overzichtsrapport: secties, feedback-stats, alle bevindingen
    5. Signaleert fouten (500-errors, mislukte analyse, etc.)
"""

import argparse
import re
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("FOUT: 'requests' pakket niet gevonden. Installeer via: pip install requests")
    sys.exit(1)

# --- Standaard instellingen ---
DEFAULT_URL      = "http://127.0.0.1:5000"
DEFAULT_DOC      = Path(__file__).parent / "instance" / "uploads" / "Test_PvA_Esmee_improved_met_fouten2.docx"
DEFAULT_USER     = "admin"
DEFAULT_PASS     = "admin123"
DOC_TYPE_ZOEKTERM = "plan"   # selecteer document_type waarvan de naam dit bevat (hoofdletterongevoelig)


# ---------------------------------------------------------------------------
# HTML hulpfuncties (geen BeautifulSoup vereist)
# ---------------------------------------------------------------------------

def _strip_tags(html: str) -> str:
    """Verwijder alle HTML-tags en normaliseer witruimte."""
    tekst = re.sub(r'<[^>]+>', ' ', html)
    tekst = re.sub(r'&nbsp;', ' ', tekst)
    tekst = re.sub(r'&amp;', '&', tekst)
    tekst = re.sub(r'&lt;', '<', tekst)
    tekst = re.sub(r'&gt;', '>', tekst)
    tekst = re.sub(r'&#39;', "'", tekst)
    tekst = re.sub(r'&quot;', '"', tekst)
    tekst = re.sub(r'&#\d+;', '', tekst)   # verwijder resterende numerieke entities
    tekst = re.sub(r'\s+', ' ', tekst).strip()
    return tekst


def _find_flash_messages(html: str) -> list[tuple[str, str]]:
    """Haal flash-berichten op uit de HTML. Geeft lijst van (categorie, tekst)."""
    berichten = []
    for match in re.finditer(r'class="alert alert-(\w+)"[^>]*>(.*?)</div>', html, re.DOTALL):
        cat  = match.group(1)
        tekst = _strip_tags(match.group(2))
        berichten.append((cat, tekst))
    return berichten


def _find_analysis_status(html: str) -> str:
    """Geeft 'completed', 'failed', of 'unknown'."""
    if 'Geanalyseerd' in html or 'analysis_status == \'completed\'' in html or 'completed' in html:
        # Kijk naar de badge-tekst in de Document Informatie sectie
        # De flash "Analyse succesvol voltooid" is een betere indicator
        if 'Analyse succesvol voltooid' in html or 'succesvol' in html:
            return 'completed'
    if 'Fout' in html and ('analysis_status' in html or 'badge-warning' in html):
        return 'failed'
    # Fallback: als er secties en feedback zijn, is de analyse geslaagd
    if 'Gevonden Secties' in html and 'Feedback' in html:
        return 'completed'
    return 'unknown'


def _find_sections(html: str) -> list[dict]:
    """Haal sectiestabel op. Geeft lijst van dict met naam en gevonden/ontbreekt."""
    secties = []
    # Zoek de rijen in de sectiestabel
    tabel_match = re.search(
        r'Gevonden Secties.*?<tbody>(.*?)</tbody>', html, re.DOTALL
    )
    if not tabel_match:
        return secties

    rijen_html = tabel_match.group(1)
    for rij in re.finditer(r'<tr>(.*?)</tr>', rijen_html, re.DOTALL):
        cellen = re.findall(r'<td[^>]*>(.*?)</td>', rij.group(1), re.DOTALL)
        if not cellen:
            continue
        naam    = _strip_tags(cellen[0])
        gevonden = 'Gevonden' in cellen[1] if len(cellen) > 1 else False
        woorden  = _strip_tags(cellen[2]) if len(cellen) > 2 else '?'
        secties.append({'naam': naam, 'gevonden': gevonden, 'woorden': woorden})
    return secties


def _find_feedback_stats(html: str) -> dict:
    """Haal de samenvattingsgetallen op (overtredingen, waarschuwingen, info, correct)."""
    labels = ['Overtredingen', 'Waarschuwingen', 'Informatie', 'Correct']
    stats  = {l.lower(): 0 for l in labels}

    for label in labels:
        # Zoek de div met dit label en haal het getal erboven op
        patroon = r'font-size:\s*24px[^>]*>(\d+)</div>\s*<div[^>]*>' + label
        m = re.search(patroon, html)
        if m:
            stats[label.lower()] = int(m.group(1))
    return stats


def _find_feedback_items(html: str) -> list[dict]:
    """
    Haal alle individuele feedbackitems op.
    Geeft lijst van dict: {sectie, criteria_naam, status, message, suggestion}
    """
    items = []

    # Verwerk sectiefeedback
    sectie_blokken = re.finditer(
        r'<h4[^>]*>(.*?)</h4>(.*?)(?=<h4|</div>\s*</div>\s*<div class="card"|$)',
        html, re.DOTALL
    )
    for blok in sectie_blokken:
        sectie_naam = _strip_tags(blok.group(1)).strip()
        blok_html   = blok.group(2)

        for item_html in re.finditer(
            r'border-left:\s*4px solid[^>]+>(.*?)(?=border-left:\s*4px solid|</div>\s*</div>\s*<(?:h4|div class))',
            blok_html, re.DOTALL
        ):
            item = _parse_feedback_item(item_html.group(1), sectie_naam)
            if item:
                items.append(item)

    return items


def _parse_feedback_item(html: str, sectie: str) -> dict | None:
    """Verwerk een enkel feedbackitem-blok."""
    # Criteria naam (in <strong>)
    naam_match = re.search(r'<strong[^>]*>(.*?)</strong>', html, re.DOTALL)
    if not naam_match:
        return None
    naam = _strip_tags(naam_match.group(1))

    # Status (badge)
    status = 'onbekend'
    if 'Overtreding' in html:
        status = 'overtreding'
    elif 'Waarschuwing' in html:
        status = 'waarschuwing'
    elif '>OK<' in html:
        status = 'ok'
    else:
        badge_match = re.search(r'color: white;">(.*?)</span>', html)
        if badge_match:
            status = _strip_tags(badge_match.group(1)).lower()

    # Berichten (alle <p> tags)
    paragrafen = [_strip_tags(p) for p in re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)]
    bericht    = paragrafen[0] if paragrafen else ''
    suggestie  = ''
    for p in paragrafen[1:]:
        if p.startswith('Suggestie:'):
            suggestie = p.replace('Suggestie:', '').strip()
            break

    return {
        'sectie': sectie,
        'naam': naam,
        'status': status,
        'bericht': bericht,
        'suggestie': suggestie,
    }


def _find_doc_type_id(html: str, zoekterm: str) -> str | None:
    """Zoek document type ID op basis van zoekterm in de naam."""
    for match in re.finditer(
        r'<option\s+value="(\d+)"[^>]*>(.*?)</option>', html, re.DOTALL
    ):
        optie_tekst = _strip_tags(match.group(2))
        if zoekterm.lower() in optie_tekst.lower():
            return match.group(1)
    return None


def _find_document_id_from_redirect(response) -> int | None:
    """Haal document-ID op uit de uiteindelijke URL na redirects."""
    url = response.url
    m = re.search(r'/analysis/(\d+)', url)
    if m:
        return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Hoofd testlogica
# ---------------------------------------------------------------------------

def run_test(base_url: str, doc_path: Path, username: str, wachtwoord: str) -> int:
    """
    Voert de volledige test uit.
    Geeft 0 terug bij succes, 1 bij fouten.
    """
    sessie = requests.Session()
    sessie.headers['User-Agent'] = 'DocuCheck-AutoTest/1.0'
    fouten = 0

    print("=" * 60)
    print("DocuCheck AutoTest")
    print(f"Server : {base_url}")
    print(f"Document: {doc_path.name}")
    print("=" * 60)

    # ---- Stap 1: Inloggen ----
    print("\n[1] Inloggen...")
    login_resp = sessie.post(
        f"{base_url}/login",
        data={'username': username, 'password': wachtwoord},
        allow_redirects=True,
        timeout=10
    )
    if login_resp.status_code >= 400:
        print(f"  FOUT: HTTP {login_resp.status_code} bij inloggen")
        return 1

    flashes = _find_flash_messages(login_resp.text)
    for cat, msg in flashes:
        if cat == 'danger':
            print(f"  FOUT: {msg}")
            return 1

    # Check of we ingelogd zijn (redirect weg van login-pagina)
    if '/login' in login_resp.url:
        print("  FOUT: Inloggen mislukt (nog op login-pagina)")
        return 1
    print("  OK - Ingelogd als", username)

    # ---- Stap 2: Upload-pagina ophalen voor document-type ID ----
    print("\n[2] Document-type ophalen...")
    upload_get = sessie.get(f"{base_url}/upload", timeout=10)
    doc_type_id = _find_doc_type_id(upload_get.text, DOC_TYPE_ZOEKTERM)
    if not doc_type_id:
        print(f"  WAARSCHUWING: Geen document-type gevonden met '{DOC_TYPE_ZOEKTERM}' in de naam")
        print("  Probeer het eerste type...")
        # Gebruik het eerste beschikbare type
        first_match = re.search(r'<option\s+value="(\d+)"', upload_get.text)
        if first_match:
            doc_type_id = first_match.group(1)
        else:
            print("  FOUT: Helemaal geen document-typen gevonden op /upload")
            return 1
    print(f"  OK - Document-type ID: {doc_type_id}")

    # ---- Stap 3: Document uploaden ----
    print(f"\n[3] Document uploaden: {doc_path.name}...")
    if not doc_path.exists():
        print(f"  FOUT: Testdocument niet gevonden: {doc_path}")
        return 1

    with open(doc_path, 'rb') as f:
        upload_resp = sessie.post(
            f"{base_url}/upload",
            data={'document_type_id': doc_type_id},
            files={'file': (doc_path.name, f, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')},
            allow_redirects=True,
            timeout=120   # analyse kan even duren (AI-calls)
        )

    if upload_resp.status_code >= 400:
        print(f"  FOUT: HTTP {upload_resp.status_code} na upload")
        fouten += 1

    # Flash-berichten na upload controleren
    flashes_upload = _find_flash_messages(upload_resp.text)
    for cat, msg in flashes_upload:
        prefix = "  FOUT" if cat == 'danger' else "  INFO"
        print(f"{prefix}: {msg}")
        if cat == 'danger':
            fouten += 1

    # Document-ID ophalen
    doc_id = _find_document_id_from_redirect(upload_resp)
    if doc_id:
        print(f"  OK - Document-ID: {doc_id} | URL: {upload_resp.url}")
    else:
        print("  WAARSCHUWING: Kon document-ID niet bepalen uit redirect-URL")

    # ---- Stap 4: Analyseresultaten verwerken ----
    html = upload_resp.text
    print("\n[4] Analyseresultaten verwerken...")

    status = _find_analysis_status(html)
    status_label = {
        'completed': 'Geanalyseerd',
        'failed':    'MISLUKT',
        'unknown':   'Onbekend'
    }.get(status, status)
    print(f"  Analysestatus: {status_label}")
    if status == 'failed':
        fouten += 1

    # ---- Secties ----
    secties = _find_sections(html)
    if secties:
        gevonden   = [s for s in secties if s['gevonden']]
        ontbrekend = [s for s in secties if not s['gevonden']]
        print(f"\n  Secties: {len(gevonden)} gevonden, {len(ontbrekend)} ontbrekend")
        for s in gevonden:
            print(f"    [+] {s['naam']}  ({s['woorden']} woorden)")
        for s in ontbrekend:
            print(f"    [-] {s['naam']}  (ONTBREEKT)")
    else:
        print("  (Geen sectiedata gevonden in HTML)")

    # ---- Feedbackstatistieken ----
    stats = _find_feedback_stats(html)
    print(f"\n  Feedbacksamenvatting:")
    print(f"    Overtredingen : {stats.get('overtredingen', '?')}")
    print(f"    Waarschuwingen: {stats.get('waarschuwingen', '?')}")
    print(f"    Informatie    : {stats.get('informatie', '?')}")
    print(f"    Correct       : {stats.get('correct', '?')}")

    # ---- Individuele feedbackitems ----
    items = _find_feedback_items(html)
    if items:
        print(f"\n  Feedbackitems ({len(items)} totaal):")
        status_volgorde = ['overtreding', 'waarschuwing', 'ok', 'onbekend']
        items.sort(key=lambda x: status_volgorde.index(x['status']) if x['status'] in status_volgorde else 99)
        huidig_sectie = None
        for item in items:
            if item['sectie'] != huidig_sectie:
                huidig_sectie = item['sectie']
                print(f"\n    -- {huidig_sectie} --")
            icoon = {'overtreding': '[!]', 'waarschuwing': '[?]', 'ok': '[v]'}.get(item['status'], '[ ]')
            print(f"    {icoon} {item['naam']}: {item['bericht'][:100]}")
            if item['suggestie']:
                print(f"        Suggestie: {item['suggestie'][:90]}")
    else:
        print("\n  (Geen feedbackitems geparsed - mogelijk leeg of HTML-structuur gewijzigd)")

    # ---- Controleer op Python-tracebacks in de HTML ----
    if 'Traceback (most recent call last)' in html or 'Internal Server Error' in html:
        print("\n  FOUT: Python traceback/serverfout aangetroffen in de response!")
        fouten += 1
        tb_match = re.search(r'(Traceback.*?)(?:</|$)', html[:5000], re.DOTALL)
        if tb_match:
            print("  " + _strip_tags(tb_match.group(1))[:300])

    # ---- Word export controleren ----
    if doc_id:
        fouten += _check_word_export(sessie, base_url, doc_id)

    # ---- Eindresultaat ----
    print("\n" + "=" * 60)
    if fouten == 0:
        print("RESULTAAT: GESLAAGD - geen fouten gedetecteerd")
    else:
        print(f"RESULTAAT: {fouten} FOUT(EN) GEDETECTEERD")
    print("=" * 60)

    return 0 if fouten == 0 else 1


# ---------------------------------------------------------------------------
# Word export verificatie
# ---------------------------------------------------------------------------

def _check_word_export(sessie, base_url: str, doc_id: int) -> int:
    """
    Download de Word export en controleer of comments op de juiste paragraaf staan
    (niet op headings, tenzij er geen andere optie is).
    Geeft het aantal fouten terug.
    """
    import tempfile
    import zipfile
    import xml.etree.ElementTree as ET

    print("\n[5] Word export controleren...")

    export_resp = sessie.get(
        f"{base_url}/documents/{doc_id}/export",
        timeout=30,
        allow_redirects=True,
    )
    if export_resp.status_code >= 400:
        print(f"  FOUT: HTTP {export_resp.status_code} bij export")
        return 1
    if 'application/vnd.openxmlformats' not in export_resp.headers.get('Content-Type', ''):
        # Waarschijnlijk een redirect naar foutpagina
        print("  WAARSCHUWING: Export leverde geen docx bestand op (mogelijk geen analyseerdata)")
        return 0

    # Sla tijdelijk op
    with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp:
        tmp.write(export_resp.content)
        tmp_path = tmp.name

    try:
        fouten = 0
        W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

        with zipfile.ZipFile(tmp_path, 'r') as z:
            # Lees document.xml voor paragraaf-structuur
            doc_xml   = ET.fromstring(z.read('word/document.xml'))
            # Lees comments.xml voor comment teksten
            try:
                comm_xml  = ET.fromstring(z.read('word/comments.xml'))
            except KeyError:
                print("  INFO: Geen comments.xml in export (geen afwijkingen?)")
                return 0

        # Bouw mapping: comment_id → tekst (eerste 80 chars)
        comment_texts: dict[str, str] = {}
        for comm in comm_xml.findall(f'{{{W}}}comment'):
            cid = comm.get(f'{{{W}}}id', '')
            tekst_delen = []
            for p in comm.findall(f'.//{{{W}}}p'):
                for r in p.findall(f'.//{{{W}}}r'):
                    t = r.find(f'{{{W}}}t')
                    if t is not None and t.text:
                        tekst_delen.append(t.text)
            comment_texts[cid] = ' '.join(tekst_delen)[:80]

        # Loop door alle paragrafen in document.xml en vind commentRangeStart-markers
        body = doc_xml.find(f'.//{{{W}}}body')
        if body is None:
            print("  FOUT: Geen w:body gevonden in export")
            return 1

        body_paras = body.findall(f'{{{W}}}p')

        # Bouw set van heading paragraaf-indices (via w:pPr/w:pStyle)
        heading_indices: set[int] = set()
        para_texts: list[str] = []
        for i, p in enumerate(body_paras):
            pPr    = p.find(f'{{{W}}}pPr')
            pStyle = pPr.find(f'{{{W}}}pStyle') if pPr is not None else None
            style  = pStyle.get(f'{{{W}}}val', '') if pStyle is not None else ''
            runs   = p.findall(f'.//{{{W}}}r')
            tekst  = ''.join(
                (r.find(f'{{{W}}}t').text or '')
                for r in runs
                if r.find(f'{{{W}}}t') is not None
            ).strip()
            para_texts.append(tekst)
            # Heading als stijl begint met 'Heading' of bevat alleen heading-achtig tekst
            if style.startswith('Heading') or style.startswith('Kop'):
                heading_indices.add(i)

        # Vind commentRangeStart per paragraaf-index
        comments_op_para: dict[int, list[str]] = {}
        for i, p in enumerate(body_paras):
            for crs in p.findall(f'{{{W}}}commentRangeStart'):
                cid = crs.get(f'{{{W}}}id', '')
                comments_op_para.setdefault(i, []).append(cid)

        print(f"  Totaal: {len(comment_texts)} comment(s) in export")

        fout_count = 0
        for para_idx, comment_ids in sorted(comments_op_para.items()):
            is_heading = para_idx in heading_indices
            para_tekst = para_texts[para_idx][:60] if para_idx < len(para_texts) else '?'
            for cid in comment_ids:
                comm_preview = comment_texts.get(cid, '(onbekend)')
                if is_heading:
                    print(f"  [!] Comment op HEADING (para {para_idx}): '{para_tekst}'")
                    print(f"       Comment: {comm_preview}")
                    fout_count += 1
                else:
                    print(f"  [v] Comment op alinea (para {para_idx}): '{para_tekst[:50]}'")

        if fout_count == 0:
            print(f"  OK - Alle {len(comments_op_para)} comment(s) staan op inhoudsalinea's")
        else:
            print(f"  FOUT: {fout_count} comment(s) staan op headings i.p.v. alinea's")
            fouten += fout_count

        return fouten

    except Exception as e:
        print(f"  FOUT bij Word export controle: {e}")
        import traceback as tb
        tb.print_exc()
        return 1
    finally:
        import os as _os
        try:
            _os.unlink(tmp_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='DocuCheck AutoTest')
    parser.add_argument('--url',  default=DEFAULT_URL,  help='Server URL')
    parser.add_argument('--doc',  default=str(DEFAULT_DOC), help='Pad naar testdocument')
    parser.add_argument('--user', default=DEFAULT_USER, help='Gebruikersnaam')
    parser.add_argument('--pass', dest='wachtwoord', default=DEFAULT_PASS, help='Wachtwoord')
    args = parser.parse_args()

    exit_code = run_test(
        base_url  = args.url.rstrip('/'),
        doc_path  = Path(args.doc),
        username  = args.user,
        wachtwoord = args.wachtwoord,
    )
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
