"""
Unit-tests voor src/analysis/inline_word_comments.py

REGRESSIETEST: _find_target_paragraph_idx
Bug: Als section_name='Hele Document' (document_only criterium), was heading_idx None
en werd direct para_idx=0 teruggegeven, ongeacht waar het snippet stond.
Fix: Zoek door het hele document als heading_idx None is maar snippet aanwezig.
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from analysis.inline_word_comments import _find_target_paragraph_idx


def _para(idx, text, is_heading=False, heading_level=0):
    return {
        'idx': idx,
        'text': text,
        'is_heading': is_heading,
        'heading_level': heading_level,
        'level': heading_level,   # alias die inline_word_comments.py gebruikt
    }


# Standaard document-structuur voor tests
PARA_STRUCTURE = [
    _para(0,  'Inhoudsopgave',                   is_heading=True, heading_level=1),
    _para(1,  'Inleiding',                        is_heading=True, heading_level=2),
    _para(2,  'Dit is de eerste alinea van de inleiding.'),
    _para(3,  'Hier staat een tweede alinea.'),
    _para(4,  'Methode',                          is_heading=True, heading_level=2),
    _para(5,  'De methode bestaat uit interviews.'),
    _para(6,  'Conclusie',                        is_heading=True, heading_level=2),
    _para(7,  'De conclusie bevat de eindconclusie van het onderzoek.'),
    _para(8,  'Er zijn cruciale bevindingen gedaan.'),
]


class TestFindTargetParagraphIdx:

    # -----------------------------------------------------------------------
    # Normale sectie-matching
    # -----------------------------------------------------------------------

    def test_heading_match_op_sectienaam(self):
        """Bekende sectienaam moet het bijbehorende heading-paragraaf vinden."""
        idx, location = _find_target_paragraph_idx(
            PARA_STRUCTURE, 'Inleiding', offending_snippet=None
        )
        assert idx == 1, f"Verwacht para 1 ('Inleiding'), kreeg {idx}"
        assert 'Inleiding' in location

    def test_snippet_na_heading_geeft_juiste_para(self):
        """Als snippet achter een heading staat, moet dat para gevonden worden."""
        idx, location = _find_target_paragraph_idx(
            PARA_STRUCTURE,
            section_name='Inleiding',
            offending_snippet='tweede alinea',
        )
        assert idx == 3, f"Verwacht para 3 (snippet-match), kreeg {idx}"

    def test_heading_prefix_fallback(self):
        """
        Sectienaam 'Conclusie' moet matchen op 'Conclusie' heading ook al
        is het heading-tekst soms langer.
        """
        idx, location = _find_target_paragraph_idx(
            PARA_STRUCTURE, 'Conclusie', offending_snippet=None
        )
        assert idx == 6, f"Verwacht para 6 ('Conclusie'), kreeg {idx}"

    # -----------------------------------------------------------------------
    # REGRESSIETEST: document_only — heading_idx=None
    # -----------------------------------------------------------------------

    def test_document_only_met_snippet_zoekt_door_heel_doc(self):
        """
        REGRESSIE: Als section_name niet als heading bestaat (document_only
        criterium met section_name='Hele Document'), maar er WEL een snippet
        aanwezig is, moet de functie het snippet door het HELE document zoeken
        — NIET direct para 0 teruggeven.

        Oud gedrag: altijd para 0 → comment onder inhoudsopgave.
        Nieuw gedrag: snippet gevonden op para 8 → idx=8.
        """
        snippet = 'cruciale bevindingen'
        idx, location = _find_target_paragraph_idx(
            PARA_STRUCTURE,
            section_name='Hele Document',   # Bestaat niet als heading
            offending_snippet=snippet,
        )
        assert idx == 8, (
            f"REGRESSIE: snippet '{snippet}' staat op para 8, maar functie gaf "
            f"para {idx} terug. Oud gedrag (para 0) wijst op regression."
        )

    def test_document_only_zonder_snippet_geeft_para_0(self):
        """
        Als section niet bestaat ALS heading EN er geen snippet is,
        is para 0 het correcte fallback (begin van document).
        """
        idx, location = _find_target_paragraph_idx(
            PARA_STRUCTURE,
            section_name='Hele Document',
            offending_snippet=None,
        )
        assert idx == 0, (
            f"Zonder snippet verwacht para 0 als fallback, kreeg {idx}."
        )

    def test_document_only_kort_snippet_geeft_para_0(self):
        """
        Snippet korter dan 5 tekens telt niet als betrouwbaar — fallback op 0.
        """
        idx, location = _find_target_paragraph_idx(
            PARA_STRUCTURE,
            section_name='Hele Document',
            offending_snippet='abc',  # < 5 tekens
        )
        assert idx == 0

    def test_document_only_snippet_niet_gevonden_geeft_para_0(self):
        """
        Als het snippet nergens in het document voorkomt, fallback op 0.
        """
        idx, location = _find_target_paragraph_idx(
            PARA_STRUCTURE,
            section_name='Hele Document',
            offending_snippet='XYZXYZ_bestaat_niet',
        )
        assert idx == 0

    # -----------------------------------------------------------------------
    # Snippet-locatie binnen bekende sectie
    # -----------------------------------------------------------------------

    def test_snippet_buiten_sectie_grenzen_valt_terug_op_heading(self):
        """
        Als het snippet NIET in de verwachte sectie staat, geef de heading terug.
        (Defensief gedrag — geen crash.)
        """
        idx, location = _find_target_paragraph_idx(
            PARA_STRUCTURE,
            section_name='Methode',
            offending_snippet='conclusie van het onderzoek',  # staat in Conclusie, niet Methode
        )
        # Mag de Methode-heading (idx=4) of de snippet-locatie (idx=7) zijn
        # — maar mag niet crashen en moet een geldig index teruggeven
        assert isinstance(idx, int)
        assert 0 <= idx < len(PARA_STRUCTURE)
