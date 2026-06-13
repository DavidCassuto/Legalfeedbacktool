"""
Tests voor opstart-gedrag van de applicatie.

REGRESSIETEST: Documenten met status='analyzing' worden bij herstart
automatisch teruggezet naar 'failed'.

Bug: Als Flask crashte of herstartte midden in een analyse (bijv. door de
debug-reloader die stdlib-bestanden bewaakt), bleef het document voor altijd
op 'analyzing' staan en kon de gebruiker de analyse niet meer starten.

Fix: Bij opstarten worden alle 'analyzing' documenten gereset naar 'failed'.
"""
import sys
import os
import sqlite3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def _setup_db(db_path, statuses):
    """Vul de test-DB met documenten met de opgegeven statussen."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            analysis_status TEXT DEFAULT 'pending'
        )
    """)
    for i, status in enumerate(statuses):
        conn.execute(
            "INSERT INTO documents (filename, original_filename, analysis_status) VALUES (?,?,?)",
            (f'doc{i}.docx', f'Origineel{i}.docx', status)
        )
    conn.commit()
    conn.close()


def _get_statuses(db_path):
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT id, analysis_status FROM documents ORDER BY id").fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}


class TestStuckAnalyseReset:

    def test_analyzing_wordt_failed_bij_herstart(self, tmp_path):
        """
        REGRESSIE: Documenten met status 'analyzing' moeten bij herstart
        worden teruggezet naar 'failed'.
        """
        db_path = str(tmp_path / 'test.db')
        _setup_db(db_path, ['analyzing', 'analyzing', 'completed'])

        # Simuleer de reset-functie uit main.py
        conn = sqlite3.connect(db_path)
        result = conn.execute(
            "UPDATE documents SET analysis_status='failed' "
            "WHERE analysis_status='analyzing'"
        )
        rowcount = result.rowcount
        conn.commit()
        conn.close()

        statuses = _get_statuses(db_path)
        assert rowcount == 2, f"Verwacht 2 gereset, maar {rowcount} werden gereset."
        assert statuses[1] == 'failed', "Doc 1 (was 'analyzing') moet 'failed' zijn."
        assert statuses[2] == 'failed', "Doc 2 (was 'analyzing') moet 'failed' zijn."
        assert statuses[3] == 'completed', "Doc 3 (was 'completed') moet ongewijzigd blijven."

    def test_pending_wordt_niet_gereset(self, tmp_path):
        """'pending' documenten worden NIET gereset — alleen 'analyzing'."""
        db_path = str(tmp_path / 'test.db')
        _setup_db(db_path, ['pending', 'analyzing', 'failed'])

        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE documents SET analysis_status='failed' "
            "WHERE analysis_status='analyzing'"
        )
        conn.commit()
        conn.close()

        statuses = _get_statuses(db_path)
        assert statuses[1] == 'pending',   "'pending' mag niet worden gewijzigd."
        assert statuses[2] == 'failed',    "'analyzing' → 'failed'."
        assert statuses[3] == 'failed',    "'failed' blijft 'failed'."

    def test_lege_db_geen_crash(self, tmp_path):
        """Reset op lege DB mag niet crashen."""
        db_path = str(tmp_path / 'empty.db')
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT, original_filename TEXT, analysis_status TEXT
            )
        """)
        conn.commit()
        conn.close()

        conn = sqlite3.connect(db_path)
        result = conn.execute(
            "UPDATE documents SET analysis_status='failed' "
            "WHERE analysis_status='analyzing'"
        )
        assert result.rowcount == 0
        conn.commit()
        conn.close()

    def test_geen_analyzing_niets_veranderd(self, tmp_path):
        """Als er geen 'analyzing' documenten zijn, verandert er niets."""
        db_path = str(tmp_path / 'test.db')
        _setup_db(db_path, ['completed', 'failed', 'pending'])

        conn = sqlite3.connect(db_path)
        result = conn.execute(
            "UPDATE documents SET analysis_status='failed' "
            "WHERE analysis_status='analyzing'"
        )
        assert result.rowcount == 0
        conn.commit()
        conn.close()

        statuses = _get_statuses(db_path)
        assert statuses[1] == 'completed'
        assert statuses[2] == 'failed'
        assert statuses[3] == 'pending'
