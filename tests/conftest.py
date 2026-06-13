"""
Gedeelde pytest fixtures voor DocuCheck tests.

Aanpak:
- Elke test krijgt een verse in-memory SQLite DB (geïsoleerd, snel).
- Flask test-client met session-based login helper.
- Geen echte Anthropic API-calls: LLM-functies worden gemockt.
"""
import os
import sys
import sqlite3
import tempfile
import pytest

# Zorg dat src/ op het pad staat
SRC = os.path.join(os.path.dirname(__file__), '..', 'src')
sys.path.insert(0, SRC)


# ---------------------------------------------------------------------------
# Minimaal DB-schema (kopie van de tabellen die tests nodig hebben)
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'user'
);

CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    organization_id INTEGER
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    upload_date TEXT,
    analysis_status TEXT DEFAULT 'pending',
    document_type_id INTEGER,
    user_id INTEGER,
    organization_id INTEGER
);

CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    identifier TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS criteria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    check_type TEXT DEFAULT 'none',
    application_scope TEXT DEFAULT 'specific_sections',
    is_enabled INTEGER DEFAULT 1,
    parameters TEXT,
    error_message TEXT,
    fixed_feedback_text TEXT,
    severity TEXT DEFAULT 'warning',
    color TEXT DEFAULT '#FFD700',
    rule_type TEXT DEFAULT 'tekstueel',
    frequency_unit TEXT,
    expected_value_min INTEGER,
    expected_value_max INTEGER,
    model_name TEXT DEFAULT 'claude-haiku-4-5',
    prompt_template TEXT,
    threshold INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS document_type_criteria_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_type_id INTEGER NOT NULL,
    criteria_id INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS criteria_section_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    criteria_id INTEGER NOT NULL,
    section_id INTEGER NOT NULL,
    is_excluded INTEGER DEFAULT 0,
    weight REAL DEFAULT 1.0
);

CREATE TABLE IF NOT EXISTS feedback_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    criteria_id INTEGER,
    section_id INTEGER,
    status TEXT,
    message TEXT,
    suggestion TEXT,
    location TEXT,
    confidence REAL,
    color TEXT,
    offending_snippet TEXT
);

CREATE TABLE IF NOT EXISTS recognized_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    section_id INTEGER NOT NULL,
    start_char INTEGER,
    end_char INTEGER,
    content TEXT
);
"""


@pytest.fixture
def db_path(tmp_path):
    """Tijdelijk SQLite-bestand met het volledige schema."""
    path = str(tmp_path / 'test.db')
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    # Voeg een testgebruiker toe (wachtwoord: 'test')
    from werkzeug.security import generate_password_hash
    conn.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?,?,?)",
        ('testuser', generate_password_hash('test'), 'admin')
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def flask_app(db_path, monkeypatch):
    """Flask test-app met geïsoleerde test-DB."""
    # Omgevingsvariabelen zetten vóór import zodat de app de test-DB gebruikt
    monkeypatch.setenv('WERKZEUG_RUN_MAIN', 'false')  # Sla stuck-reset over

    import importlib
    import main as main_module

    # Wijs de test-DB toe
    main_module.app.config['DATABASE'] = db_path
    main_module.app.config['TESTING'] = True
    main_module.app.config['WTF_CSRF_ENABLED'] = False
    main_module.app.config['SECRET_KEY'] = 'test-secret'

    return main_module.app


@pytest.fixture
def client(flask_app):
    """Flask test-client."""
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def logged_in_client(client):
    """Test-client die al ingelogd is als testuser."""
    client.post('/login', data={'username': 'testuser', 'password': 'test'},
                follow_redirects=True)
    return client


# ---------------------------------------------------------------------------
# Helper: maak een minimaal criterion-dict
# ---------------------------------------------------------------------------
def make_criterion(check_type='none', application_scope='specific_sections', **kwargs):
    base = {
        'id': 1,
        'name': 'Test criterium',
        'check_type': check_type,
        'application_scope': application_scope,
        'is_enabled': 1,
        'parameters': '{}',
        'error_message': None,
        'fixed_feedback_text': None,
        'severity': 'warning',
        'color': '#FFD700',
        'rule_type': 'tekstueel',
        'frequency_unit': None,
        'expected_value_min': None,
        'expected_value_max': None,
        'model_name': 'claude-haiku-4-5',
        'prompt_template': 'Beoordeel: {section_content}',
        'threshold': 0,
        'section_mappings': [],
    }
    base.update(kwargs)
    return base


def make_section(name='Inleiding', identifier='inleiding', content='Dit is een testsectie.'):
    return {
        'name': name,
        'identifier': identifier,
        'content': content,
        'db_id': 1,
        'found': True,
    }
