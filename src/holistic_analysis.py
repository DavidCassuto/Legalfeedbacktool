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
from analysis.inline_word_comments import add_inline_comments, add_highlights, _is_toc_line

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

# ── Standaard feedback-configuratie (kant-en-klaar; school overschrijft naar wens) ──
# Categorie 1 (inhoud per onderdeel) komt uit de Excel-rubriek + deze extra criteria.
DEFAULT_INHOUD_CRITERIA = (
    "Beoordeel elk onderdeel in samenhang met het HELE document; de deelvragen, methode e.d. "
    "staan mogelijk in een ander hoofdstuk en mag je daarbij betrekken.\n"
    "- Zijn de deelvragen onderling én ten opzichte van de hoofdvraag voldoende onderscheidend "
    "(geen overlap; elke deelvraag is een eigen bouwsteen voor de hoofdvraag)?\n"
    "- Beantwoordt het hoofdstuk 'Juridisch onderzoek' de bijbehorende juridische deelvraag/deelvragen?\n"
    "- Beantwoordt het hoofdstuk 'Praktijkonderzoek' de bijbehorende praktijk-deelvraag/deelvragen?\n"
    "- Is er een evaluerende deelvraag? Wordt de praktijk goed getoetst aan het recht? "
    "(Of, als een juridische situatie/ontwikkeling/wijziging wordt getoetst aan niet-juridische "
    "criteria zoals doelmatigheid en efficiëntie: zijn er goede, MEETBARE criteria geformuleerd "
    "en wordt het recht goed aan die criteria getoetst?)\n"
    "- Signaleer onderdelen of hele resultatenhoofdstukken die NIET bijdragen aan de beantwoording "
    "van de deelvragen, en leg uit waarom ze niet relevant zijn."
)
DEFAULT_TAAL_INSTRUCTIES = (
    "Let op spelling-, grammatica-, interpunctie- en duidelijke stijlfouten: d/t-fouten, "
    "werkwoordsvervoeging, congruentie (onderwerp-werkwoord), verkeerd of ontbrekend "
    "leesteken, hoofdletter-/kleinlettergebruik, en evidente typefouten."
)
DEFAULT_STIJL_INSTRUCTIES = (
    "Beoordeel de juridische schrijfkwaliteit: te lange of te complexe zinnen "
    "(tangconstructies), vaag of wollig taalgebruik, te lange of ongestructureerde "
    "alinea's, passief waar actief beter is, inconsistent of onprecies juridisch "
    "begrippengebruik, en gebrekkige opbouw of samenhang tussen alinea's."
)
DEFAULT_TOON = (
    "Schrijf bemoedigend, respectvol en concreet, en spreek de student direct aan. "
    "Leg uit WAAROM iets beter kan, zodat de student het leert — schrijf de tekst niet "
    "voor de student, maar wijs de weg naar een betere formulering. Gebruik begrijpelijke "
    "taal voor de doelgroep; vermijd jargon in de feedback zelf."
)
DEFAULT_AI_INSTRUCTIES = (
    "Signaleer schrijfstijl-patronen die de tekst zwak of onpersoonlijk maken en vaak op "
    "AI-gegenereerde tekst wijzen. Beoordeel UITSLUITEND de stijl, niet de inhoud:\n"
    "- Generieke openingszinnen zonder concrete inhoud ('In het huidige tijdperk...', 'Het is van cruciaal belang...').\n"
    "- Symmetrische alineastructuur: elke alinea even lang, zelfde opbouw, geen variatie in toon.\n"
    "- Hyperbolisch/wervend taalgebruik zonder onderbouwing ('cruciaal', 'essentieel', 'fundamenteel', 'baanbrekend').\n"
    "- Ontbreken van academische voorzichtigheid: stellingen als absolute waarheid zonder 'lijkt', 'suggereert', 'mogelijk'.\n"
    "- Tautologieën en redundante formuleringen.\n"
    "- Overmatig formele verbindingswoorden ('tevens', 'voorts', 'derhalve', 'teneinde').\n"
    "- Te gepolijst: geen enkele oneffenheid of persoonlijk perspectief.\n"
    "- Verwijzingen naar bronnen die niet concreet worden aangehaald of toegepast.\n"
    "NIET vlaggen: inhoudelijke tekortkomingen, grammatica/spelling, of stijlkeuzes die niet op AI wijzen."
)
DEFAULT_MAX_PER_CATEGORIE = 15


def _merge_config(cfg: dict | None) -> dict:
    """Vul een (deels lege) feedback-configuratie aan met de standaarden."""
    cfg = dict(cfg or {})
    return {
        'inhoud_criteria':  (cfg.get('inhoud_criteria') or DEFAULT_INHOUD_CRITERIA).strip(),
        'taal_enabled':     cfg.get('taal_enabled', True),
        'taal_instructies': (cfg.get('taal_instructies') or DEFAULT_TAAL_INSTRUCTIES).strip(),
        'stijl_enabled':    cfg.get('stijl_enabled', True),
        'stijl_instructies': (cfg.get('stijl_instructies') or DEFAULT_STIJL_INSTRUCTIES).strip(),
        'ai_enabled':       cfg.get('ai_enabled', True),
        'ai_instructies':   (cfg.get('ai_instructies') or DEFAULT_AI_INSTRUCTIES).strip(),
        'toon':             (cfg.get('toon') or DEFAULT_TOON).strip(),
        'show_suggestions': cfg.get('show_suggestions', True),
        'max_per_categorie': int(cfg.get('max_per_categorie') or DEFAULT_MAX_PER_CATEGORIE),
    }


def _build_system_prompt(product_type: str, toon: str = '') -> str:
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
    base += (
        "Je bent een EDUCATIEVE assistent die de student helpt LEREN schrijven — geen "
        "assistent die het schrijfwerk overneemt. Geef de student inzicht, geen kant-en-klare "
        "herschrijving.\n\n"
    )
    if toon and toon.strip():
        base += ("TOON EN STIJL VAN DE FEEDBACK (volg dit nauwgezet — zo begeleidt deze opleiding):\n"
                 f"{toon.strip()}\n\n")
    return base + _NL_TAALGEBRUIK


def _build_user_prompt(rubric_text: str, document_text: str,
                       detect_product_type: bool = False,
                       cfg: dict | None = None) -> tuple[str, str]:
    """
    Bouwt de prompt in TWEE delen (stabiel-cachebaar deel + variabel document).
    cfg = feedback-configuratie (taal/stijl aan-uit + instructies, suggesties, cap).
    """
    cfg = _merge_config(cfg)
    if detect_product_type:
        detect_instr = (
            "Hieronder staan MEERDERE rubrieken (één per beroepsproduct: PvA, Analyse, "
            "Advies, Ontwerp, Fabricaat, Eindgesprek). Bepaal EERST, op basis van de "
            "inhoud en vorm van het document, welk beroepsproduct hier wordt beoordeeld, "
            "en geef feedback UITSLUITEND volgens de bijbehorende rubric. "
            "Vermeld het gekozen beroepsproduct in het veld \"product_type\".\n\n"
        )
        pt_field = '  "product_type": "<het door jou bepaalde beroepsproduct>",\n'
    else:
        detect_instr = ""
        pt_field = ""

    sugg_field = ('          "suggestie": "<wijs de weg naar een betere formulering, of leeg>"\n'
                  if cfg['show_suggestions'] else '')
    sugg_rule = ("" if cfg['show_suggestions'] else
                 "Geef GEEN kant-en-klare oplossing of herschrijving in 'suggestie' "
                 "(laat dat veld leeg); benoem alleen wát beter kan, zodat de student het zelf leert.\n")
    cap = cfg['max_per_categorie']

    # Categorie 2 — taalfouten (worden in het document GEMARKEERD, geen comment)
    taal_block = ""
    if cfg['taal_enabled']:
        taal_block = f"""
  "taalfouten": [
    {{ "quote": "<verbatim passage met genoeg context om de plek te vinden>",
       "fout": "<ALLEEN het foutieve woord, of de twee woorden waartussen het misgaat (bv. bij een ontbrekende komma); exact verbatim, binnen de quote>",
       "type": "<spelling|grammatica|interpunctie|stijl>" }}
  ],"""
    # Categorie 3 — juridische schrijfkwaliteit (worden COMMENTS)
    stijl_block = ""
    if cfg['stijl_enabled']:
        stijl_block = f"""
  "schrijfkwaliteit": [
    {{ "quote": "<verbatim passage>", "severity": "<belangrijk|aandachtspunt|tip>",
       "comment": "<feedback op de schrijfkwaliteit>"{(',' + chr(10) + '       "suggestie": "<of leeg>"') if cfg['show_suggestions'] else ''} }}
  ],"""
    # Categorie 5 — AI-stijldetectie (document-breed, worden COMMENTS)
    ai_block = ""
    if cfg['ai_enabled']:
        ai_block = f"""
  "ai_stijl": [
    {{ "quote": "<verbatim passage>", "comment": "<welk AI-stijlpatroon en waarom dit de tekst zwakker maakt>" }}
  ],"""

    cat1_extra = ""
    if cfg.get('inhoud_criteria'):
        cat1_extra = ("\nEXTRA INHOUDELIJKE CRITERIA (bovenop de rubriek, van de opleiding). "
                      "Verwerk deze in het passende onderdeel. Geef voor ELKE deelvraag / ELK "
                      "resultatenhoofdstuk een APARTE bevinding (finding) met als \"quote\" de "
                      "tussenconclusie of deelvraag van dat hoofdstuk, en in \"comment\" een "
                      "expliciet oordeel of (en hoe goed) de deelvraag wordt beantwoord — ook als "
                      "meerdere deelvragen onder hetzelfde rubric-onderdeel vallen. "
                      "PLAATSING: hoort een tekortkoming bij een ander hoofdstuk (bv. een "
                      "ontbrekende methodologie hoort thuis in het methode-hoofdstuk, niet bij een "
                      "tussenconclusie), kies dan een \"quote\" uit DAT hoofdstuk.\n"
                      f"{cfg['inhoud_criteria']}\n")

    cat2_instr = (f"\nCATEGORIE TAALFOUTEN (spelling/grammatica/stijl) — vul \"taalfouten\". "
                  f"Richtlijn van de opleiding: {cfg['taal_instructies']} "
                  f"Zet in \"fout\" UITSLUITEND het foutieve woord (of de twee woorden waartussen "
                  f"het misgaat), niet de hele zin — dat is wat gemarkeerd wordt. "
                  f"Geef maximaal {cap} REPRESENTATIEVE voorbeelden (niet elke instantie); "
                  f"noem terugkerende fouttypes één keer.\n" if cfg['taal_enabled'] else "")
    cat3_instr = (f"\nCATEGORIE JURIDISCHE SCHRIJFKWALITEIT — vul \"schrijfkwaliteit\". "
                  f"Richtlijn van de opleiding: {cfg['stijl_instructies']} "
                  f"Geef maximaal {cap} belangrijkste punten. UITZONDERING: structurele eisen die "
                  f"PER hoofdstuk gelden (bv. een inleidende alinea per hoofdstuk) signaleer je bij "
                  f"ELK hoofdstuk waar ze ontbreken — die vallen buiten deze limiet.\n"
                  if cfg['stijl_enabled'] else "")
    cat5_instr = (f"\nCATEGORIE AI-STIJLDETECTIE — vul \"ai_stijl\". "
                  f"Richtlijn van de opleiding: {cfg['ai_instructies']} "
                  f"Geef maximaal {cap} REPRESENTATIEVE voorbeelden.\n" if cfg['ai_enabled'] else "")

    cacheable_prefix = f"""{detect_instr}Hieronder staan eerst de BEOORDELINGSRUBRIC en daarna het volledige STUDENTDOCUMENT.

Geef FORMATIEVE, opbouwende feedback om de student te helpen LEREN schrijven. Geen cijfer
of beoordeling. Koppel elke bevinding aan een EXACTE passage in het document.

Het document bevat het onderzoeksrapport en, mogelijk verderop of tussen de bijlagen,
het BEROEPSPRODUCT (adviesnota, advies, ontwerp, implementatieplan of analyse). Geef feedback
op het rapport én op het beroepsproduct (Deel B van de rubric). Overige bijlagen (interviews,
bronnen, ruwe data) zijn steunmateriaal — geef daar GEEN feedback op.

Drie soorten feedback:
1. INHOUD per rubric-onderdeel -> "rubric_items" (de inhoudelijke eisen uit de rubric).
{cat1_extra}{cat2_instr}{cat3_instr}{cat5_instr}
ZEER BELANGRIJK voor elke "quote": een letterlijk (verbatim) overgenomen stuk tekst uit het
document, exact zoals het er staat (zelfde woorden, leestekens, hoofdletters). Kopieer het,
verzin of parafraseer NIET. Houd het kort (één zin of deelzin) en kies de quote zó dat hij EXACT
de zin/passage bevat waar je opmerking over gaat (niet de zin ervoor of erna). Citeer NOOIT uit
de inhoudsopgave.
Citeer ALTIJD het concrete tekstfragment zelf, nooit een omschrijving of plaatsaanduiding:
dus niet "in §3.1.3" maar de letterlijk geciteerde wettekst zelf; bij een typefout het exacte
woord (bv. "EDPD"); bij een opmerking over een afkortingenlijst of kop het exacte element zelf,
of — gaat het over een hoofdstuktitel — een zin uit dat hoofdstuk (niet de kop). Meld alleen
problemen die je aan een concreet, vindbaar fragment kunt koppelen. {sugg_rule}
Geef alleen bevindingen die er echt toe doen; een sterk onderdeel mag een leeg lijstje hebben.

Geef je antwoord UITSLUITEND als geldige JSON, zonder extra tekst eromheen, in dit schema:

{{
{pt_field}  "rubric_items": [
    {{
      "naam": "<naam van het rubric-onderdeel, bv. Methode>",
      "feedback": "<formatieve samenvatting: wat is sterk en wat kan beter — GEEN cijfer; beantwoordt het hoofdstuk zijn deelvraag?>",
      "anchor": "<verbatim zin uit dit onderdeel om de samenvatting bij te plaatsen (deelvraag of tussenconclusie), of leeg>",
      "findings": [
        {{
          "quote": "<verbatim passage>",
          "severity": "<belangrijk|aandachtspunt|tip>",
          "comment": "<concrete, opbouwende feedback>"{(',' if sugg_field else '')}
{sugg_field}        }}
      ]
    }}
  ],{taal_block}{stijl_block}{ai_block}
  "eindbeeld": "<formatieve slotalinea: de belangrijkste punten om aan te werken>"
}}

severity: "belangrijk" = hier is echt aandacht nodig; "aandachtspunt" = kan beter; "tip" = kleine suggestie.

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
# Typische omvang van het JSON-antwoord (drie feedback-groepen). Ruwe bovengrens
# voor de kostenschatting; de werkelijke uitvoer is begrensd door max_tokens.
EST_OUTPUT_TOKENS = 6000


def _call_llm(system_prompt: str, cacheable_prefix: str, document_block: str,
              model: str, max_tokens: int = 16000) -> dict:
    """
    Eén Anthropic-call met prompt-caching op het systeemprompt + rubric-deel.
    Streamt het antwoord (ruim output-budget) zodat de JSON niet halverwege afkapt.
    """
    import anthropic
    if not Config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY niet ingesteld (.env).")
    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        system=[{'type': 'text', 'text': system_prompt,
                 'cache_control': {'type': 'ephemeral'}}],
        messages=[{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': cacheable_prefix,
                 'cache_control': {'type': 'ephemeral'}},
                {'type': 'text', 'text': document_block},
            ],
        }],
    )
    with client.messages.stream(**kwargs) as stream:
        msg = stream.get_final_message()
    u = msg.usage
    text = ''.join(b.text for b in msg.content if getattr(b, 'type', None) == 'text')
    return {
        'text':          text,
        'input_tokens':  u.input_tokens,
        'output_tokens': u.output_tokens,
        'cache_read':    getattr(u, 'cache_read_input_tokens', 0) or 0,
        'cache_created': getattr(u, 'cache_creation_input_tokens', 0) or 0,
        'stop_reason':   msg.stop_reason,
    }


def estimate_run(rubric_text: str, docx_path: str, product_type: str = '',
                 model: str = None, detect_product_type: bool = False,
                 include_annexes: bool = False, feedback_config: dict | None = None) -> dict:
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

    cfg = _merge_config(feedback_config)
    system_prompt = _build_system_prompt(
        'automatisch te bepalen' if detect_product_type else (product_type or 'Onbekend'),
        cfg['toon'])
    prefix, doc_block = _build_user_prompt(rubric_text, analyze_text, detect_product_type, cfg)

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


def _repair_truncated_json(s: str) -> str:
    """Repareer afgekapte JSON: knip terug naar het laatste 'veilige' punt
    (na een afgesloten waarde) en sluit open haakjes. Vangnet voor max_tokens-afkap."""
    stack = []
    in_str = False
    esc = False
    last_safe = 0
    safe_stack: list = []   # open haakjes ZOALS op het veilige afkappunt
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in '{[':
            stack.append('}' if ch == '{' else ']')
            if len(stack) == 1:                 # minimaal een leeg root-object sluiten
                last_safe, safe_stack = i + 1, list(stack)
        elif ch in '}]':
            if stack:
                stack.pop()
            last_safe, safe_stack = i + 1, list(stack)   # net na een afgesloten container
        elif ch == ',':
            last_safe, safe_stack = i, list(stack)        # vóór de komma: na een complete waarde
    out = s[:last_safe].rstrip().rstrip(',')
    out += ''.join(reversed(safe_stack))
    return out


def _parse_json(text: str) -> dict:
    """Haal het JSON-object uit de LLM-respons (tolerant voor fences en afkap)."""
    cleaned = text.strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start = cleaned.find('{')
    end = cleaned.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            pass
    # Laatste redmiddel: afgekapte JSON repareren
    frag = cleaned[start:] if start != -1 else cleaned
    return json.loads(_repair_truncated_json(frag))


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
    feedback_config: dict | None = None,
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
    cfg = _merge_config(feedback_config)
    system_prompt = _build_system_prompt(
        'automatisch te bepalen' if detect_product_type else product_type, cfg['toon'])
    cacheable_prefix, document_block = _build_user_prompt(
        rubric_text, analyze_text, detect_product_type, cfg)
    llm = _call_llm(system_prompt, cacheable_prefix, document_block, model)
    logger.info("LLM klaar | in=%d out=%d cache_read=%d cache_created=%d stop=%s",
                llm['input_tokens'], llm['output_tokens'],
                llm.get('cache_read', 0), llm.get('cache_created', 0),
                llm.get('stop_reason'))
    if llm.get('stop_reason') == 'max_tokens':
        logger.warning("Antwoord afgekapt op max_tokens — JSON wordt indien nodig gerepareerd.")

    data = _parse_json(llm['text'])
    rubric_items = data.get('rubric_items', []) or []
    schrijfkwaliteit = data.get('schrijfkwaliteit', []) or []
    ai_stijl = data.get('ai_stijl', []) or []
    taalfouten = data.get('taalfouten', []) or []
    eindbeeld = data.get('eindbeeld', '') or ''
    detected_product_type = (data.get('product_type') or '').strip() or product_type

    show_sugg = cfg['show_suggestions']
    # Inhoudsopgave-regels uitsluiten zodat 'vindbaar' overeenkomt met de echte plaatsing
    norm_paras = [_normalize(p) for p in paragraphs if not _is_toc_line(p)]
    comment_items: list[dict] = []
    unplaced: list[dict] = []

    def _add_comment(naam, f, check_type):
        quote = (f.get('quote') or '').strip()
        comment = (f.get('comment') or '').strip()
        if not comment and not quote:
            return
        sev_label = (f.get('severity') or 'tip').strip().lower()
        status = _SEVERITY_MAP.get(sev_label, 'info')
        suggestie = (f.get('suggestie') or '').strip() if show_sugg else ''
        locatable = _quote_is_locatable(quote, norm_paras)
        fi = {
            'criteria_id': None, 'criteria_name': naam, 'section_name': naam,
            'status': status, 'severity_label': sev_label,
            'message': comment, 'suggestion': suggestie,
            'offending_snippet': quote, 'confidence': 1.0,
            'color': _STATUS_COLOR[status], 'check_type': check_type,
            '_locatable': locatable,
        }
        comment_items.append(fi)
        if not locatable:
            unplaced.append(fi)

    # Categorie 1: inhoud per rubric-onderdeel -> comments
    for item in rubric_items:
        naam = (item.get('naam') or 'Onderdeel').strip()
        for f in item.get('findings', []) or []:
            _add_comment(naam, f, 'holistic')
        # Per-onderdeel samenvatting (incl. deelvraag-oordeel) als comment bij een
        # citaat uit dat onderdeel — zodat het holistische oordeel ook in het doc staat.
        fb = (item.get('feedback') or '').strip()
        anchor = (item.get('anchor') or '').strip()
        if fb and anchor:
            _add_comment(naam, {'quote': anchor, 'comment': fb,
                                'severity': 'tip', 'suggestie': ''}, 'holistic')
    # Categorie 3: juridische schrijfkwaliteit -> comments
    for f in schrijfkwaliteit:
        _add_comment('Schrijfkwaliteit', f, 'holistic')
    # Categorie 5: AI-stijldetectie -> comments
    for f in ai_stijl:
        _add_comment('Schrijfstijl (AI-signaal)', f, 'holistic')

    # Categorie 2: taalfouten -> lichte MARKERING (geen comment).
    # quote = context om de plek te vinden; fout = exact het te markeren stukje.
    taal_items = [{'offending_snippet': (t.get('quote') or '').strip(),
                   'fout': (t.get('fout') or '').strip()}
                  for t in taalfouten if (t.get('quote') or t.get('fout') or '').strip()]

    placed_count = sum(1 for fi in comment_items if fi['_locatable'])

    # 4. Document opbouwen: eerst comments, dan markeringen (twee stappen op één bestand)
    if output_path is None:
        base, ext = os.path.splitext(docx_path)
        output_path = f"{base}_holistisch_gecommentarieerd{ext}"

    comments_tmp = output_path
    if taal_items:
        base, ext = os.path.splitext(output_path)
        comments_tmp = f"{base}__c{ext}"

    # Alleen betrouwbaar plaatsbare comments in het document; de rest blijft zichtbaar
    # in de "niet-geplaatste"-lijst i.p.v. bovenaan (inhoudsopgave) te belanden.
    placeable = [fi for fi in comment_items if fi['_locatable']]
    add_inline_comments(
        original_docx_path=docx_path,
        feedback_items=placeable,
        recognized_sections=[],
        output_path=comments_tmp,
    )

    highlights_placed = 0
    if taal_items:
        _, highlights_placed = add_highlights(
            comments_tmp, taal_items, output_path, color='yellow')
        try:
            if os.path.abspath(comments_tmp) != os.path.abspath(output_path):
                os.remove(comments_tmp)
        except OSError:
            pass

    logger.info("Holistisch klaar | comments=%d (geplaatst %d) | taalmarkeringen=%d",
                len(comment_items), placed_count, highlights_placed)

    return {
        'rubric_items':     rubric_items,
        'schrijfkwaliteit': schrijfkwaliteit,
        'ai_stijl':         ai_stijl,
        'taalfouten':       taalfouten,
        'eindbeeld':        eindbeeld,
        'product_type':     detected_product_type,
        'annex_info':       annex_info,
        'feedback_items':   comment_items,
        'placed_count':     placed_count,
        'highlights_placed': highlights_placed,
        'unplaced':         unplaced,
        'output_path':      output_path,
        'usage':            {'input_tokens': llm['input_tokens'],
                             'output_tokens': llm['output_tokens'],
                             'cache_read': llm.get('cache_read', 0),
                             'cache_created': llm.get('cache_created', 0)},
        'model':            model,
    }
