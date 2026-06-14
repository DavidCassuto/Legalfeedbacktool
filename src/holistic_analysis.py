# src/holistic_analysis.py
"""
PROTOTYPE — Holistische, LLM-first analyse (juni 2026).

Doel: een school levert (1) een student-.docx en (2) de rubric als platte tekst.
Eén LLM-call leest het hele document + de rubric, beoordeelt elk rubric-onderdeel,
en geeft per bevinding een VERBATIM citaat uit het document. Dat citaat wordt door
de bestaande comment-engine (analysis.inline_word_comments) als Word-comment op de
juiste plek geplaatst.

Geen secties/criteria/mappings nodig. Dit staat volledig los van de bestaande
pipeline (analysis_runner / criterion_checking) zodat de productieversie ongemoeid blijft.
"""

import os
import re
import json
import logging
from datetime import date

from config import Config
from analysis import document_parsing
from analysis.inline_word_comments import add_inline_comments

logger = logging.getLogger('docucheck.holistic')

# Standaardmodel voor de holistische beoordeling. Sonnet 4.6 = goede afweging
# tussen oordeelskwaliteit en kosten op een document van deze omvang.
DEFAULT_MODEL = 'claude-sonnet-4-6'

# Formatieve severity-labels (van het LLM) -> interne status voor de comment-engine.
# De engine filtert op status in ('violation','warning','info','error'); we mappen
# de feedback-vriendelijke labels daarop, maar tonen het Nederlandse label in de UI.
_SEVERITY_MAP = {
    'belangrijk':    'violation',
    'aandachtspunt': 'warning',
    'tip':           'info',
    # tolerant voor oude/Engelse waarden:
    'violation':     'violation',
    'warning':       'warning',
    'info':          'info',
}
_STATUS_COLOR = {
    'violation': '#E63946',   # rood
    'warning':   '#F9C74F',   # geel
    'info':      '#4D908E',   # teal
}

_NL_TAALGEBRUIK = (
    "Schrijf helder, modern Nederlands. Vermijd archaisch of overdreven formeel "
    "taalgebruik. Wees concreet, constructief en to-the-point."
)


def _build_system_prompt(product_type: str, feedback_profile: str = '') -> str:
    d = date.today()
    maanden = ['januari', 'februari', 'maart', 'april', 'mei', 'juni',
               'juli', 'augustus', 'september', 'oktober', 'november', 'december']
    vandaag = f"{d.day} {maanden[d.month - 1]} {d.year}"
    base = (
        "Je bent een ervaren Nederlandse afstudeerbegeleider die FORMATIEVE feedback geeft "
        f"op studentwerk (producttype: {product_type}). "
        "Je doel is de student helpen het werk te verbeteren — NIET beoordelen of becijferen. "
        "Geef GEEN cijfer, score, eindoordeel of 'voldoende/onvoldoende'. "
        "Geef concrete, constructieve, opbouwende feedback: benoem wat sterk is en, vooral, "
        "wat de student concreet kan verbeteren en hoe. De rubriek is de structuur en de norm; "
        "jouw taak is de student daar met feedback naartoe te helpen.\n\n"
        f"VANDAAG IS HET: {vandaag}. Beoordeel data en jaartallen ten opzichte van deze datum; "
        "een jaartal in 2025 of 2026 is dus niet per definitie toekomstig.\n\n"
    )
    if feedback_profile and feedback_profile.strip():
        base += (
            "FEEDBACK-AANPAK VAN DE OPLEIDING — volg deze richtlijnen, toon en aandachtspunten "
            "nauwgezet; ze weerspiegelen hoe deze opleiding haar studenten begeleidt:\n"
            f"{feedback_profile.strip()}\n\n"
        )
    return base + _NL_TAALGEBRUIK


def _build_user_prompt(rubric_text: str, document_text: str,
                       detect_product_type: bool = False) -> tuple[str, str]:
    """
    Bouwt de prompt in TWEE delen:
      - cacheable_prefix : instructies + JSON-schema + de RUBRIC. Dit deel is
        identiek voor elke student met dezelfde rubric, dus het wordt door
        Anthropic prompt-caching hergebruikt (goedkoper bij meerdere runs).
      - document_block   : het studentdocument zelf (verschilt per student).
    De volgorde is bewust: het stabiele deel staat vooraan, het variabele achteraan.
    """
    if detect_product_type:
        detect_instr = (
            "Hieronder staan MEERDERE rubrieken (één per beroepsproduct: PvA, Analyse, "
            "Advies, Ontwerp, Fabricaat, Eindgesprek). Bepaal EERST, op basis van de "
            "inhoud en vorm van het document, welk beroepsproduct hier wordt beoordeeld, "
            "en beoordeel het document UITSLUITEND volgens de bijbehorende rubric. "
            "Vermeld het gekozen beroepsproduct in het veld \"product_type\".\n\n"
        )
        pt_field = '  "product_type": "<het door jou bepaalde beroepsproduct>",\n'
    else:
        detect_instr = ""
        pt_field = ""

    cacheable_prefix = f"""{detect_instr}Hieronder staan eerst de BEOORDELINGSRUBRIC en daarna het volledige STUDENTDOCUMENT.

Geef per rubric-onderdeel FORMATIEVE feedback: benoem kort wat sterk is en — vooral —
wat de student concreet kan verbeteren en hoe. Koppel bevindingen aan een EXACTE passage
in het document. Geef GEEN cijfer, score of eindoordeel.

Het document bevat het onderzoeksrapport en, mogelijk verderop of tussen de bijlagen,
het BEROEPSPRODUCT (bijv. een adviesnota, advies, ontwerp, implementatieplan of analyse).
Geef feedback op het rapport én op het beroepsproduct (dat hoort bij de Deel B-onderdelen
van de rubric). De overige bijlagen (interviews, bronnen, ruwe data) zijn steunmateriaal —
geef daar GEEN feedback op.

ZEER BELANGRIJK voor elke bevinding:
- "quote" MOET een letterlijk (verbatim) overgenomen stuk tekst uit het document zijn,
  exact zoals het er staat (zelfde woorden, leestekens, hoofdletters). Kopieer het,
  verzin of parafraseer het NIET. Houd het kort: bij voorkeur een enkele zin of
  deelzin (max ~25 woorden), zodat de passage eenduidig terug te vinden is.
- Kies de quote zo dat hij precies de plek aanwijst waar je opmerking over gaat.
- Geef alleen bevindingen die er echt toe doen. Niet elk onderdeel hoeft bevindingen
  te hebben; een sterk onderdeel mag een leeg "findings"-lijstje hebben.

Geef je antwoord UITSLUITEND als geldige JSON, zonder extra tekst eromheen, in dit schema:

{{
{pt_field}  "rubric_items": [
    {{
      "naam": "<naam van het rubric-onderdeel, bv. Methode>",
      "feedback": "<formatieve samenvatting: wat is sterk en wat kan beter — GEEN cijfer>",
      "findings": [
        {{
          "quote": "<verbatim passage uit het document>",
          "severity": "<belangrijk | aandachtspunt | tip>",
          "comment": "<concrete, opbouwende feedback bij deze passage>",
          "suggestie": "<concreet verbeteradvies, of leeg>"
        }}
      ]
    }}
  ],
  "eindbeeld": "<formatieve slotalinea: de belangrijkste punten om aan te werken>"
}}

severity: "belangrijk" = hier is echt aandacht nodig; "aandachtspunt" = kan beter;
"tip" = kleine suggestie.

=== BEOORDELINGSRUBRIC ===
{rubric_text}

=== STUDENTDOCUMENT ===
"""
    return cacheable_prefix, document_text


# Prijzen in USD per 1.000.000 tokens (input, output) — bron: claude-api skill, mei 2026.
PRICING = {
    'claude-sonnet-4-6': (3.0, 15.0),
    'claude-haiku-4-5':  (1.0, 5.0),
    'claude-opus-4-8':   (5.0, 25.0),
}
# Ruwe schatting: ~3.7 tekens per token voor Nederlands proza.
CHARS_PER_TOKEN = 3.7
# Typische omvang van het JSON-antwoord (rubric-oordeel + bevindingen).
EST_OUTPUT_TOKENS = 4000


def _call_llm(system_prompt: str, cacheable_prefix: str, document_block: str,
              model: str, max_tokens: int = 8000) -> dict:
    """
    Eén Anthropic-call met prompt-caching op het systeemprompt + rubric-deel.
    Bij meerdere runs met dezelfde rubric (bv. een klas studenten) worden die
    tokens uit de cache gelezen (~10% van de inputprijs) i.p.v. opnieuw betaald.
    """
    import anthropic
    if not Config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY niet ingesteld (.env).")
    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[{'type': 'text', 'text': system_prompt,
                 'cache_control': {'type': 'ephemeral'}}],
        messages=[{
            'role': 'user',
            'content': [
                # Stabiel deel (instructies + rubric) -> gecached
                {'type': 'text', 'text': cacheable_prefix,
                 'cache_control': {'type': 'ephemeral'}},
                # Variabel deel (het document) -> niet gecached
                {'type': 'text', 'text': document_block},
            ],
        }],
    )
    u = resp.usage
    return {
        'text':          resp.content[0].text,
        'input_tokens':  u.input_tokens,
        'output_tokens': u.output_tokens,
        'cache_read':    getattr(u, 'cache_read_input_tokens', 0) or 0,
        'cache_created': getattr(u, 'cache_creation_input_tokens', 0) or 0,
    }


def estimate_run(rubric_text: str, docx_path: str, product_type: str = '',
                 model: str = None, detect_product_type: bool = False,
                 include_annexes: bool = False, feedback_profile: str = '') -> dict:
    """
    Schat tokengebruik en kosten VOORAF in, zonder de API aan te roepen
    (heuristisch op basis van tekenaantal). Wordt getoond vóór bevestiging.
    """
    model = model or DEFAULT_MODEL
    pt_for_bp = 'automatisch te bepalen' if detect_product_type else (product_type or '')
    full_text, _paras, headings = document_parsing.parse_document(docx_path)
    if include_annexes:
        analyze_text = full_text
        annex_info = {'stripped': False, 'annex_heading': None, 'beroepsproduct': None,
                      'chars_total': len(full_text), 'chars_analyzed': len(full_text)}
    else:
        analyze_text, annex_info = _strip_annexes(full_text, headings, docx_path, pt_for_bp)

    system_prompt = _build_system_prompt(
        'automatisch te bepalen' if detect_product_type else (product_type or 'Onbekend'),
        feedback_profile)
    prefix, doc_block = _build_user_prompt(rubric_text, analyze_text, detect_product_type)

    input_chars = len(system_prompt) + len(prefix) + len(doc_block)
    input_tokens = int(input_chars / CHARS_PER_TOKEN)
    out_tokens = EST_OUTPUT_TOKENS
    p_in, p_out = PRICING.get(model, PRICING[DEFAULT_MODEL])
    cost_usd = input_tokens / 1_000_000 * p_in + out_tokens / 1_000_000 * p_out

    return {
        'model':            model,
        'input_tokens':     input_tokens,
        'est_output_tokens': out_tokens,
        'cost_usd':         round(cost_usd, 3),
        'annex_info':       annex_info,
        'rubric_chars':     len(rubric_text),
    }


def _parse_json(text: str) -> dict:
    """Haal het JSON-object uit de LLM-respons (tolerant voor markdown-fences)."""
    cleaned = text.strip()
    # Strip ```json ... ``` fences indien aanwezig
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Val terug op het grootste {...}-blok
        start = cleaned.find('{')
        end = cleaned.rfind('}')
        if start != -1 and end != -1 and end > start:
            return json.loads(cleaned[start:end + 1])
        raise


# Kopteksten die het begin van de bijlagen/annexen markeren. De analyse stopt hier
# standaard: bijlagen horen niet bij de inhoudelijke beoordeling en kosten veel tokens.
_ANNEX_RE = re.compile(
    r'^\s*(?:bijlage[n]?|annex(?:en|es)?|appendix|appendices)\b',
    re.IGNORECASE,
)


def _find_annex_start(full_text: str, headings: list[dict]) -> tuple[int | None, str | None]:
    """
    Zoek de positie (char-offset) waar de bijlagen beginnen, op basis van een
    koptekst als 'Bijlagen' / 'Bijlage 1' / 'Annex' / 'Appendix'.

    Gebruikt ALLEEN echte Word-kopstijlen (headings) — inhoudsopgave-regels staan
    daar niet tussen, dus een 'Bijlagen'-vermelding in de inhoudsopgave triggert
    de afkap niet. Voetnoten/eindnoten staan na de body en blijven buiten beschouwing.
    """
    fn_marker = full_text.find('[VOETNOTEN/EINDNOTEN]')
    body_end = fn_marker if fn_marker != -1 else len(full_text)

    candidates = []
    for h in headings:
        sc = h.get('start_char', -1)
        if sc < 0 or sc >= body_end:
            continue
        txt = (h.get('text') or '').strip()
        # Verwijder eventuele voorloopnummering ("7 Bijlagen", "7. Bijlagen")
        cleaned = re.sub(r'^\s*\d+(\.\d+)*\.?\s*', '', txt)
        if _ANNEX_RE.match(cleaned) or _ANNEX_RE.match(txt):
            candidates.append((sc, txt))
    if not candidates:
        return None, None
    candidates.sort()
    return candidates[0]


def _find_annex_start_bold(docx_path: str, full_text: str,
                           headings: list[dict]) -> tuple[int | None, str | None]:
    """
    Fallback: vind een bijlage-start die GEEN Word-kopstijl heeft maar wel als
    koptekst is bedoeld — vetgedrukt of in HOOFDLETTERS (komt veel voor bij studenten).

    TOC-vermijding: er wordt pas gezocht NA de eerste echte koptekst in het document
    (de inhoudsopgave staat daarvoor), en regels met tabs/punt-leiders worden genegeerd.
    """
    from docx import Document
    try:
        doc = Document(docx_path)
    except Exception:
        return None, None

    # Zoek pas vanaf de eerste echte koptekst — daarvoor zit de inhoudsopgave.
    search_from = min((h['start_char'] for h in headings
                       if h.get('start_char', -1) >= 0), default=0)

    for para in doc.paragraphs:
        raw = (para.text or '').strip()
        if not raw or '\t' in raw or re.search(r'\.{4,}|…', raw):
            continue  # leeg of inhoudsopgave-achtig (punt-leiders / tab + paginanr.)
        if len(raw.split()) > 6:
            continue  # te lang voor een koptekst
        cleaned = re.sub(r'^\s*\d+(\.\d+)*\.?\s*', '', raw)
        if not (_ANNEX_RE.match(cleaned) or _ANNEX_RE.match(raw)):
            continue
        style = (para.style.name if para.style else '') or ''
        emphasized = (
            style.startswith('Heading')
            or raw.isupper()
            or any(r.bold for r in para.runs if (r.text or '').strip())
        )
        if not emphasized:
            continue
        pos = full_text.find(raw, search_from)
        if pos == -1:
            pos = full_text.find(cleaned, search_from)
        if pos != -1:
            return pos, raw
    return None, None


# Het BEROEPSPRODUCT moet wél beoordeeld worden (Deel B), ook al staat het tussen
# of na de bijlagen. We herkennen het op koptekst — generiek + producttype-specifiek.
_BEROEPSPRODUCT_GENERIC = ['beroepsproduct', 'beroepsprodukt', 'het product', 'productnaam']
_BEROEPSPRODUCT_SPECIFIC = {
    'advies':    ['advies', 'adviesnota', 'adviesrapport', 'advisnota', 'adviesbrief', 'adviesdocument'],
    'ontwerp':   ['ontwerp', 'implementatieplan', 'blauwdruk', 'stappenplan', 'ontwerpplan'],
    'analyse':   ['analyse', 'analyserapport', 'analysedocument'],
    'fabricaat': ['fabricaat', 'handleiding', 'testverslag', 'prototype'],
    'pva':       ['plan van aanpak'],
}


def _beroepsproduct_keywords(product_type: str) -> list[str]:
    pt = (product_type or '').lower()
    kws = list(_BEROEPSPRODUCT_GENERIC)
    auto = (not pt) or 'automatisch' in pt or 'onbekend' in pt
    for key, words in _BEROEPSPRODUCT_SPECIFIC.items():
        if auto or key in pt:
            kws += words
    return kws


def _heading_is_beroepsproduct(text: str, kws: list[str]) -> bool:
    cleaned = re.sub(r'^\s*\d+(\.\d+)*\.?\s*', '', (text or '').lower())
    cleaned = re.sub(r'^(?:bijlage|annex|appendix)\s*\w*\s*[:.\-]?\s*', '', cleaned).strip()
    return any(re.search(r'\b' + re.escape(kw) + r'\b', cleaned) for kw in kws)


def _find_beroepsproduct_ranges(full_text: str, headings: list[dict],
                                product_type: str, search_from: int) -> list[tuple[int, int, str]]:
    """
    Zoek beroepsproduct-secties op koptekst vanaf `search_from` (de bijlage-grens).
    Returns lijst van (start_char, end_char, heading_text). Meestal precies één.
    """
    kws = _beroepsproduct_keywords(product_type)
    fn_marker = full_text.find('[VOETNOTEN/EINDNOTEN]')
    body_end = fn_marker if fn_marker != -1 else len(full_text)
    hs = sorted((h for h in headings if h.get('start_char', -1) >= 0),
                key=lambda x: x['start_char'])
    ranges = []
    for i, h in enumerate(hs):
        if h['start_char'] < search_from:
            continue
        if not _heading_is_beroepsproduct(h.get('text', ''), kws):
            continue
        lvl = h.get('level', 1)
        end = body_end
        for j in range(i + 1, len(hs)):
            if hs[j]['level'] <= lvl:
                end = min(hs[j]['start_char'], body_end)
                break
        ranges.append((h['start_char'], end, (h.get('text') or '').strip()))
    return ranges


def _strip_annexes(full_text: str, headings: list[dict],
                   docx_path: str | None = None,
                   product_type: str = '') -> tuple[str, dict]:
    """
    Knip de bijlagen weg, maar:
      - behoud het voetnoten/eindnoten-blok (bronvermelding), en
      - vis het BEROEPSPRODUCT eruit en houd dat erbij (Deel B-beoordeling),
        ook al staat het tussen of na de bijlagen.
    Probeert eerst echte kopstijlen, daarna vet/hoofdletter-koppen.
    Returns (te_analyseren_tekst, info-dict).
    """
    start, htxt = _find_annex_start(full_text, headings)
    if start is None and docx_path:
        start, htxt = _find_annex_start_bold(docx_path, full_text, headings)
    if start is None:
        return full_text, {'stripped': False, 'annex_heading': None,
                           'beroepsproduct': None,
                           'chars_total': len(full_text), 'chars_analyzed': len(full_text)}

    fn_marker = full_text.find('[VOETNOTEN/EINDNOTEN]')
    body = full_text[:start].rstrip()

    # Beroepsproduct uit de bijlage-zone halen en toevoegen
    bp_ranges = _find_beroepsproduct_ranges(full_text, headings, product_type, start)
    bp_heading = None
    for (bps, bpe, bptext) in bp_ranges:
        segment = full_text[bps:bpe].strip()
        if segment:
            body += '\n\n[BEROEPSPRODUCT]\n' + segment
            bp_heading = bp_heading or bptext

    # Voetnoten/eindnoten weer aanplakken
    if fn_marker != -1 and fn_marker > start:
        body += '\n\n' + full_text[fn_marker:]

    return body, {'stripped': True, 'annex_heading': htxt,
                  'beroepsproduct': bp_heading,
                  'chars_total': len(full_text), 'chars_analyzed': len(body)}


def _normalize(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '').lower().strip())


def _quote_is_locatable(quote: str, normalized_paragraphs: list[str]) -> bool:
    """
    Spiegelt de matching van inline_word_comments: exacte substring of prefix(60).
    Gebruikt om bevindingen te markeren die NIET geplaatst kunnen worden,
    zodat ze zichtbaar blijven i.p.v. stil te verdwijnen.
    """
    q = _normalize(quote)
    if len(q) < 5:
        return False
    for p in normalized_paragraphs:
        if q in p:
            return True
    prefix = q[:60]
    if len(prefix) >= 15:
        for p in normalized_paragraphs:
            if prefix in p:
                return True
    return False


def run_holistic_analysis(
    docx_path: str,
    rubric_text: str,
    product_type: str = 'Onbekend',
    model: str = DEFAULT_MODEL,
    output_path: str | None = None,
    detect_product_type: bool = False,
    include_annexes: bool = False,
    feedback_profile: str = '',
) -> dict:
    """
    Voer de holistische analyse uit en plaats Word-comments via de bestaande engine.

    Returns dict met:
      - rubric_items   : lijst van per-onderdeel oordeel/score (+ findings)
      - eindbeeld      : slottekst
      - feedback_items : alle gegenereerde items (incl. placed-vlag)
      - placed_count   : aantal bevindingen waarvan het citaat in het document gevonden is
      - unplaced       : bevindingen waarvan het citaat NIET gevonden is (blijven zichtbaar)
      - output_path    : pad naar het gecommentarieerde .docx
      - usage          : token-gebruik
      - model          : gebruikt model
    """
    logger.info("Holistische analyse start | doc=%s | type=%s | model=%s",
                os.path.basename(docx_path), product_type, model)

    # 1. Document parsen (hergebruik bestaande parser)
    full_text, paragraphs, headings = document_parsing.parse_document(docx_path)
    if not full_text.strip():
        raise RuntimeError("Kon geen tekst uit het document halen (leeg of onleesbaar).")

    # 1b. Bijlagen standaard wegknippen (scheelt veel tokens en is geen beoordelingsstof)
    pt_for_bp = 'automatisch te bepalen' if detect_product_type else product_type
    if include_annexes:
        analyze_text = full_text
        annex_info = {'stripped': False, 'annex_heading': None, 'beroepsproduct': None,
                      'chars_total': len(full_text), 'chars_analyzed': len(full_text)}
    else:
        analyze_text, annex_info = _strip_annexes(full_text, headings, docx_path, pt_for_bp)
        if annex_info['stripped']:
            logger.info("Bijlagen overgeslagen vanaf %r | beroepsproduct=%r (%d -> %d tekens)",
                        annex_info['annex_heading'], annex_info.get('beroepsproduct'),
                        annex_info['chars_total'], annex_info['chars_analyzed'])

    # 2. LLM-call (met prompt-caching op systeemprompt + rubric)
    system_prompt = _build_system_prompt(
        'automatisch te bepalen' if detect_product_type else product_type, feedback_profile)
    cacheable_prefix, document_block = _build_user_prompt(rubric_text, analyze_text, detect_product_type)
    llm = _call_llm(system_prompt, cacheable_prefix, document_block, model)
    logger.info("LLM klaar | in=%d out=%d cache_read=%d cache_created=%d",
                llm['input_tokens'], llm['output_tokens'],
                llm.get('cache_read', 0), llm.get('cache_created', 0))

    data = _parse_json(llm['text'])
    rubric_items = data.get('rubric_items', []) or []
    eindbeeld = data.get('eindbeeld', '') or ''
    # Door de LLM bepaald beroepsproduct (auto-detect) — anders de meegegeven keuze
    detected_product_type = (data.get('product_type') or '').strip() or product_type

    # 3. Bevindingen omzetten naar feedback-items voor de comment-engine
    norm_paras = [_normalize(p) for p in paragraphs]
    feedback_items: list[dict] = []
    unplaced: list[dict] = []
    placed_count = 0

    for item in rubric_items:
        naam = (item.get('naam') or 'Onderdeel').strip()
        for f in item.get('findings', []) or []:
            quote = (f.get('quote') or '').strip()
            sev_label = (f.get('severity') or 'tip').strip().lower()
            status = _SEVERITY_MAP.get(sev_label, 'info')
            comment = (f.get('comment') or '').strip()
            suggestie = (f.get('suggestie') or '').strip()
            if not comment and not quote:
                continue

            locatable = _quote_is_locatable(quote, norm_paras)
            if locatable:
                placed_count += 1

            fi = {
                'criteria_id':       None,
                'criteria_name':     naam,
                # Rubric-naam als ZACHTE plaatsings-hint; de engine valt terug op
                # document-brede zoektocht naar het citaat als de naam geen heading raakt.
                'section_name':      naam,
                'status':            status,
                'severity_label':    sev_label,
                'message':           comment,
                'suggestion':        suggestie,
                'offending_snippet': quote,
                'confidence':        1.0,
                'color':             _STATUS_COLOR[status],
                'check_type':        'holistic',
                '_locatable':        locatable,
            }
            feedback_items.append(fi)
            if not locatable:
                unplaced.append(fi)

    # 4. Word-comments plaatsen via bestaande engine (recognized_sections leeg:
    #    plaatsing leunt volledig op het verbatim citaat + rubric-naam-hint).
    if output_path is None:
        base, ext = os.path.splitext(docx_path)
        output_path = f"{base}_holistisch_gecommentarieerd{ext}"

    add_inline_comments(
        original_docx_path=docx_path,
        feedback_items=feedback_items,
        recognized_sections=[],
        output_path=output_path,
    )

    logger.info("Holistische analyse klaar | items=%d | geplaatst=%d | niet-geplaatst=%d",
                len(feedback_items), placed_count, len(unplaced))

    return {
        'rubric_items':   rubric_items,
        'eindbeeld':      eindbeeld,
        'product_type':   detected_product_type,
        'annex_info':     annex_info,
        'feedback_items': feedback_items,
        'placed_count':   placed_count,
        'unplaced':       unplaced,
        'output_path':    output_path,
        'usage':          {'input_tokens': llm['input_tokens'],
                           'output_tokens': llm['output_tokens'],
                           'cache_read': llm.get('cache_read', 0),
                           'cache_created': llm.get('cache_created', 0)},
        'model':          model,
    }
