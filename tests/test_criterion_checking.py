"""
Unit-tests voor src/analysis/criterion_checking.py

Dekt drie categorieën:
1. Snelle check-functies (keyword, word_count) — geen LLM, geen DB
2. REGRESSIETEST: document_only + llm_review gaat naar llm_tasks (niet dode functie)
3. REGRESSIETEST: specific_sections zonder mappings levert lege lijst op
"""
import json
import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from analysis.criterion_checking import (
    check_keyword_forbidden,
    check_keyword_required,
    check_word_count,
    get_applicable_sections,
)
from conftest import make_criterion, make_section


# ---------------------------------------------------------------------------
# check_keyword_forbidden
# ---------------------------------------------------------------------------
class TestKeywordForbidden:

    def test_verboden_woord_gevonden(self):
        """Als een verboden woord aanwezig is, moet status != 'ok' zijn."""
        criterion = make_criterion(
            check_type='keyword_forbidden',
            parameters=json.dumps({'keywords': ['ik', 'mij']}),
        )
        section = make_section(content='Ik heb dit zelf onderzocht.')
        result = check_keyword_forbidden(criterion, section)
        assert result is not None
        assert result['status'] != 'ok'
        assert result['offending_snippet'] is not None

    def test_geen_verboden_woord(self):
        """Zonder verboden woorden moet status 'ok' zijn."""
        criterion = make_criterion(
            check_type='keyword_forbidden',
            parameters=json.dumps({'keywords': ['ik', 'mij']}),
        )
        section = make_section(content='De student heeft dit onderzocht.')
        result = check_keyword_forbidden(criterion, section)
        assert result is not None
        assert result['status'] == 'ok'
        assert result['offending_snippet'] is None

    def test_geen_keywords_geconfigureerd(self):
        """Zonder geconfigureerde keywords moet de functie None teruggeven."""
        criterion = make_criterion(parameters='{}')
        section = make_section(content='Willekeurige tekst.')
        result = check_keyword_forbidden(criterion, section)
        assert result is None

    def test_woord_grens_check(self):
        """Verboden woord 'ik' mag niet matchen als deel van 'praktijk'."""
        criterion = make_criterion(
            parameters=json.dumps({'keywords': ['ik']}),
        )
        section = make_section(content='Dit is praktijk-gericht onderzoek.')
        result = check_keyword_forbidden(criterion, section)
        # 'ik' zit in 'praktijk' maar \b grens beschermt daartegen
        assert result['status'] == 'ok'

    def test_snippet_max_200_tekens(self):
        """Offending snippet mag niet langer zijn dan 200 tekens."""
        lange_zin = 'ik ' + 'x' * 300
        criterion = make_criterion(parameters=json.dumps({'keywords': ['ik']}))
        section = make_section(content=lange_zin)
        result = check_keyword_forbidden(criterion, section)
        assert result['offending_snippet'] is not None
        assert len(result['offending_snippet']) <= 200


# ---------------------------------------------------------------------------
# check_keyword_required
# ---------------------------------------------------------------------------
class TestKeywordRequired:

    def test_verplicht_woord_aanwezig(self):
        # Beide keywords moeten aanwezig zijn voor status='ok'
        criterion = make_criterion(parameters=json.dumps({'keywords': ['output', 'outcome']}))
        section = make_section(content='De output en outcome van het onderzoek zijn beschreven.')
        result = check_keyword_required(criterion, section)
        assert result['status'] == 'ok'

    def test_verplicht_woord_ontbreekt(self):
        criterion = make_criterion(parameters=json.dumps({'keywords': ['outcome']}))
        section = make_section(content='Er is geen relevante inhoud.')
        result = check_keyword_required(criterion, section)
        assert result['status'] != 'ok'

    def test_lege_inhoud(self):
        criterion = make_criterion(parameters=json.dumps({'keywords': ['output']}))
        section = make_section(content='')
        result = check_keyword_required(criterion, section)
        assert result['status'] != 'ok'


# ---------------------------------------------------------------------------
# check_word_count
# ---------------------------------------------------------------------------
class TestWordCount:

    def _criterion(self, min_w=None, max_w=None):
        return make_criterion(
            check_type='word_count',
            expected_value_min=min_w,
            expected_value_max=max_w,
        )

    def test_te_weinig_woorden(self):
        criterion = self._criterion(min_w=100)
        section = make_section(content='Kort stuk.')  # 2 woorden
        result = check_word_count(criterion, section)
        assert result is not None
        assert result['status'] != 'ok'

    def test_te_veel_woorden(self):
        criterion = self._criterion(max_w=5)
        section = make_section(content='Dit is een veel te lange sectie met veel te veel woorden.')
        result = check_word_count(criterion, section)
        assert result is not None
        assert result['status'] != 'ok'

    def test_binnen_grenzen(self):
        criterion = self._criterion(min_w=3, max_w=20)
        section = make_section(content='Dit is precies goed.')  # 4 woorden
        result = check_word_count(criterion, section)
        assert result is not None
        assert result['status'] == 'ok'

    def test_geen_grenzen_geconfigureerd(self):
        """Zonder min/max moet de functie None teruggeven."""
        criterion = self._criterion()
        section = make_section(content='Willekeurige tekst.')
        result = check_word_count(criterion, section)
        assert result is None


# ---------------------------------------------------------------------------
# REGRESSIETEST: specific_sections zonder mappings → lege lijst
#
# Bug: criterium met specific_sections maar geen section_mappings liep
# vroeger op alle secties. Verwacht gedrag: lege lijst.
# ---------------------------------------------------------------------------
class TestGetApplicableSections:

    def test_specific_sections_zonder_mappings_geeft_lege_lijst(self):
        """
        REGRESSIE: Een criterium met application_scope='specific_sections'
        maar lege section_mappings mag NIET op alle secties lopen.
        Verwacht: lege lijst.
        """
        criterion = make_criterion(
            application_scope='specific_sections',
            section_mappings=[],  # geen koppelingen
        )
        all_sections = [
            {'identifier': 'inleiding', 'name': 'Inleiding', 'found': True},
            {'identifier': 'methode',   'name': 'Methode',   'found': True},
        ]
        # db_connection en document_type_id zijn niet nodig voor dit pad
        result = get_applicable_sections(criterion, all_sections, 1, None)
        assert result == [], (
            "Criterium met specific_sections maar geen mappings mag NIET "
            "op alle secties lopen (regressie voor bekende bug)."
        )

    def test_specific_sections_met_mappings(self):
        """Met expliciete mapping wordt alleen de gemapte sectie teruggegeven."""
        criterion = make_criterion(
            application_scope='specific_sections',
            section_mappings=[
                {'section_identifier': 'inleiding', 'is_excluded': 0}
            ],
        )
        all_sections = [
            {'identifier': 'inleiding', 'name': 'Inleiding', 'found': True},
            {'identifier': 'methode',   'name': 'Methode',   'found': True},
        ]
        result = get_applicable_sections(criterion, all_sections, 1, None)
        assert len(result) == 1
        assert result[0]['identifier'] == 'inleiding'

    def test_document_only_niet_in_applicable(self):
        """document_only criteria komen nooit via get_applicable_sections."""
        criterion = make_criterion(application_scope='document_only')
        all_sections = [
            {'identifier': 'document', 'name': 'Hele Document', 'found': True},
            {'identifier': 'inleiding', 'name': 'Inleiding', 'found': True},
        ]
        # document_only heeft geen pad in get_applicable_sections → lege lijst
        result = get_applicable_sections(criterion, all_sections, 1, None)
        assert result == []


# ---------------------------------------------------------------------------
# REGRESSIETEST: document_only + llm_review gaat naar llm_tasks
#
# Bug: check_document_wide_criterion() gaf None terug voor llm_review type,
# waardoor document-brede LLM-criteria nooit werden uitgevoerd.
# Fix: document_only + llm_review wordt direct aan llm_tasks toegevoegd.
# ---------------------------------------------------------------------------
class TestDocumentOnlyLlmRouting:

    def test_document_only_llm_review_roept_niet_check_document_wide_aan(self):
        """
        REGRESSIE: check_document_wide_criterion() gaf None terug voor llm_review,
        waardoor document-brede LLM-criteria nooit werden uitgevoerd.

        Fix: document_only + llm_review gaat DIRECT naar de LLM-executor,
        check_document_wide_criterion() wordt NIET aangeroepen.

        Verificatie: patch check_document_wide_criterion en check_llm_review,
        verifieer welke wordt aangeroepen.
        """
        import analysis.criterion_checking as cc

        llm_criterion = make_criterion(
            id=99,
            name='AI-stijlcheck',
            check_type='llm_review',
            application_scope='document_only',
            prompt_template='Beoordeel het document: {section_content}',
            model_name='claude-haiku-4-5',
        )

        llm_called_with = []
        wide_called_with = []

        def fake_llm_review(crit, sec, db_conn):
            llm_called_with.append(crit.get('id'))
            return {
                'criteria_id': crit.get('id'),
                'criteria_name': crit.get('name'),
                'status': 'ok', 'message': 'mock', 'suggestion': '',
                'location': 'Hele Document', 'confidence': 1.0,
                'color': '#84A98C', 'offending_snippet': None,
                'section_id': None, 'section_name': 'Hele Document',
            }

        def fake_wide(crit, doc_content, sections):
            wide_called_with.append(crit.get('id'))
            return None

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = []
        mock_db.execute.return_value.fetchone.return_value = None

        with patch.object(cc, 'check_llm_review', side_effect=fake_llm_review), \
             patch.object(cc, 'check_document_wide_criterion', side_effect=fake_wide):

            # Vervang ThreadPoolExecutor door synchrone uitvoering zodat de
            # test niet hangt: submit() roept de functie direct aan.
            class SyncExecutor:
                def __enter__(self): return self
                def __exit__(self, *a): pass
                def submit(self, fn, *args, **kwargs):
                    f = MagicMock()
                    f.result.return_value = fn(*args, **kwargs)
                    return f

            with patch.object(cc, 'ThreadPoolExecutor', return_value=SyncExecutor()), \
                 patch.object(cc, 'as_completed', side_effect=lambda fs: iter(fs)):
                try:
                    cc.generate_feedback(
                        doc_content='Testdocument inhoud.',
                        recognized_sections=[],
                        criteria_list=[llm_criterion],
                        db_connection=mock_db,
                        document_id=1,
                        document_type_id=1,
                    )
                except Exception:
                    pass

        assert 99 in llm_called_with, (
            "REGRESSIE: document_only + llm_review (id=99) moet check_llm_review() "
            "aanroepen, niet check_document_wide_criterion()."
        )
        assert 99 not in wide_called_with, (
            "REGRESSIE: check_document_wide_criterion() mag NIET worden aangeroepen "
            "voor llm_review criteria (retourneert altijd None voor dat type)."
        )
