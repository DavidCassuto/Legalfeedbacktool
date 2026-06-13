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

# Kleur per severity (UI + Word-comment-context)
_SEVERITY_COLOR = {
    'violation': '#E63946',   # rood
    'warning':   '#F9C74F',   # geel
    'info':      '#4D908E',   # teal
}

_NL_TAALGEBRUIK = (
    "Schrijf helder, modern Nederlands. Vermijd archaisch of overdreven formeel "
    "taalgebruik. Wees concreet, constructief en to-the-point."
)


def _build_system_prompt(product_type: str) -> str:
    d = date.today()
    maanden = ['januari', 'februari', 'maart', 'april', 'mei', 'juni',
               'juli', 'augustus', 'september', 'oktober', 'november', 'december']
    vandaag = f"{d.day} {maanden[d.month - 1]} {d.year}"
    return (
        "Je bent een ervaren, kritische maar eerlijke Nederlandse afstudeerbegeleider "
        "die een studentdocument beoordeelt aan de hand van een door de opleiding "
        f"aangeleverde beoordelingsrubric (producttype: {product_type}).\n\n"
        f"VANDAAG IS HET: {vandaag}. Beoordeel data en jaartallen ten opzichte van deze datum; "
        "een jaartal in 2025 of 2026 is dus niet per definitie toekomstig.\n\n"
        + _NL_TAALGEBRUIK
    )


def _build_user_prompt(rubric_text: str, document_text: str) -> str:
    """Bouwt de instructie + JSON-schema. Document komt als laatste (groot blok)."""
    return f"""Hieronder staan eerst de BEOORDELINGSRUBRIC en daarna het volledige STUDENTDOCUMENT.

Beoordeel het document onderdeel voor onderdeel volgens de rubric. Bepaal per
rubric-onderdeel een oordeel en, waar relevant, concrete bevindingen die je aan een
EXACTE passage in het document kunt koppelen.

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
  "rubric_items": [
    {{
      "naam": "<naam van het rubric-onderdeel, bv. Methode>",
      "score": "<jouw oordeel/score in de termen van de rubric, bv. 'Voldoende (6)'>",
      "oordeel": "<beknopte onderbouwing van de score, 2-5 zinnen>",
      "findings": [
        {{
          "quote": "<verbatim passage uit het document>",
          "severity": "<violation | warning | info>",
          "comment": "<jouw concrete opmerking bij deze passage>",
          "suggestie": "<optioneel: concreet verbeteradvies, of leeg>"
        }}
      ]
    }}
  ],
  "eindbeeld": "<korte slotalinea: algeheel beeld + belangrijkste verbeterpunten>"
}}

severity-richtlijn: "violation" = duidelijke tekortkoming/fout; "warning" = aandachtspunt;
"info" = neutrale observatie of suggestie.

=== BEOORDELINGSRUBRIC ===
{rubric_text}

=== STUDENTDOCUMENT ===
{document_text}
"""


def _call_llm(system_prompt: str, user_prompt: str, model: str, max_tokens: int = 8000) -> dict:
    """Eén Anthropic-call. Retourneert {'text', 'input_tokens', 'output_tokens'}."""
    import anthropic
    if not Config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY niet ingesteld (.env).")
    client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{'role': 'user', 'content': user_prompt}],
    )
    return {
        'text':          resp.content[0].text,
        'input_tokens':  resp.usage.input_tokens,
        'output_tokens': resp.usage.output_tokens,
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
    full_text, paragraphs, _headings = document_parsing.parse_document(docx_path)
    if not full_text.strip():
        raise RuntimeError("Kon geen tekst uit het document halen (leeg of onleesbaar).")

    # 2. LLM-call
    system_prompt = _build_system_prompt(product_type)
    user_prompt = _build_user_prompt(rubric_text, full_text)
    llm = _call_llm(system_prompt, user_prompt, model)
    logger.info("LLM klaar | in=%d out=%d tokens", llm['input_tokens'], llm['output_tokens'])

    data = _parse_json(llm['text'])
    rubric_items = data.get('rubric_items', []) or []
    eindbeeld = data.get('eindbeeld', '') or ''

    # 3. Bevindingen omzetten naar feedback-items voor de comment-engine
    norm_paras = [_normalize(p) for p in paragraphs]
    feedback_items: list[dict] = []
    unplaced: list[dict] = []
    placed_count = 0

    for item in rubric_items:
        naam = (item.get('naam') or 'Onderdeel').strip()
        for f in item.get('findings', []) or []:
            quote = (f.get('quote') or '').strip()
            severity = (f.get('severity') or 'info').strip().lower()
            if severity not in _SEVERITY_COLOR:
                severity = 'info'
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
                'status':            severity,
                'message':           comment,
                'suggestion':        suggestie,
                'offending_snippet': quote,
                'confidence':        1.0,
                'color':             _SEVERITY_COLOR[severity],
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
        'feedback_items': feedback_items,
        'placed_count':   placed_count,
        'unplaced':       unplaced,
        'output_path':    output_path,
        'usage':          {'input_tokens': llm['input_tokens'],
                           'output_tokens': llm['output_tokens']},
        'model':          model,
    }
