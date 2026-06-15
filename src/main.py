# src/main.py
"""Flask app factory — registreert alle routes via add_url_rule() zodat
url_for()-aanroepen in templates ongewijzigd blijven."""

import os
import sys
import logging
import secrets
from datetime import datetime

# Laad .env bestand als het bestaat (lokale ontwikkeling)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── sys.path zodat alle src/-modules vindbaar zijn ──────────────────────────
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# ── Logging: console + bestand ───────────────────────────────────────────────
_INSTANCE = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'instance')
_LOG_FILE = os.path.join(_INSTANCE, 'app.log')
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_LOG_FILE, encoding='utf-8', delay=True),
    ]
)
logging.getLogger('analysis.inline_word_comments').setLevel(logging.DEBUG)

# Onderdruk extreem verbose debug-output van HTTP-bibliotheken
for _noisy in ('httpcore', 'httpx', 'anthropic._base_client', 'anthropic',
                'urllib3', 'hpack', 'h2'):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

_app_logger = logging.getLogger('docucheck')

class _PrintToLog:
    """Vangt sys.stdout op en stuurt elke regel ook naar de logger."""
    def __init__(self, original):
        self._original = original
    def write(self, msg):
        self._original.write(msg)
        stripped = msg.rstrip('\n')
        if stripped:
            _app_logger.info(stripped)
    def flush(self):
        self._original.flush()

import sys as _sys
_sys.stdout = _PrintToLog(_sys.stdout)

# ── Flask ────────────────────────────────────────────────────────────────────
from flask import Flask

from database_optimizations import initialize_sqlite_optimizer, optimize_database_for_multiple_users
from database import get_db, close_db

# Paden — INSTANCE_PATH kan via env var worden overschreven (bijv. Railway volume: /data)
BASE_DIR      = os.path.abspath(os.path.dirname(__file__))
INSTANCE_PATH = os.environ.get('INSTANCE_PATH', os.path.join(BASE_DIR, '..', 'instance'))
UPLOAD_FOLDER = os.path.join(INSTANCE_PATH, 'uploads')
DATABASE      = os.path.join(INSTANCE_PATH, 'documents.db')

os.makedirs(INSTANCE_PATH, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__, instance_relative_config=True, template_folder='templates')
app.config.from_mapping(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'feedback-tool-secret-key-2024'),
    DATABASE=DATABASE,
    UPLOAD_FOLDER=UPLOAD_FOLDER,
)

# DB-teardown registreren
app.teardown_appcontext(close_db)

# DB-optimalisaties initialiseren
print("[INIT] Initialiseren van database optimalisaties...")
initialize_sqlite_optimizer(DATABASE)
optimize_database_for_multiple_users()

# ── Stuck-analyse reset bij opstarten ────────────────────────────────────────
# Documenten die bij een vorige run op 'analyzing' bleven staan (bijv. door
# een herstart midden in de analyse) worden teruggedraaid naar 'failed'.
# De gebruiker kan ze daarna met één klik heranalyseren.
import sqlite3 as _sqlite3
def _reset_stuck_analyses():
    try:
        _db = _sqlite3.connect(DATABASE)
        result = _db.execute(
            "UPDATE documents SET analysis_status='failed' "
            "WHERE analysis_status='analyzing'"
        )
        if result.rowcount:
            print(f"[INIT] {result.rowcount} vastgelopen analyse(s) teruggezet naar 'failed'.")
        _db.commit()
        _db.close()
    except Exception as _e:
        print(f"[INIT] Waarschuwing: stuck-reset mislukt: {_e}")

# Alleen uitvoeren in de werkelijke worker-process (niet in de reloader-parent)
if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
    _reset_stuck_analyses()

# ── Context processor ─────────────────────────────────────────────────────────
@app.context_processor
def inject_global_data():
    return {'now': datetime.now()}

# ── Route-functies importeren ─────────────────────────────────────────────────
from routes.auth import login, logout, index, demo_loader
from routes.documents import (
    upload_document, api_upload_document, list_documents,
    analysis_status_api, document_analysis, export_document, export_select,
    reanalyze_partial, reanalyze_document,
)
from routes.criteria import (
    list_criteria, add_criterion, edit_criterion, delete_criterion,
    map_criteria_to_sections,
    list_criteria_templates, add_criteria_template,
    list_document_type_criteria, add_criteria_to_document_type,
    edit_criteria_instance, delete_criteria_instance,
)
from routes.sections import (
    list_sections, add_section, edit_section, delete_section,
)
from routes.document_types import (
    list_document_types, add_document_type, edit_document_type, delete_document_type,
    list_organization_document_types, add_organization_document_type,
    manage_document_type_sections, add_section_to_document_type,
    remove_section_from_document_type,
)
from routes.organizations import (
    list_organizations, add_organization, edit_organization, delete_organization,
)
from routes.users import list_users, add_user, edit_user, delete_user
from routes.onboarding import (
    onboarding_wizard, onboarding_step1, onboarding_step2,
    onboarding_step3, onboarding_step4, invite_accept, welcome,
)
from routes.misc import performance_stats
from routes.holistic import (
    holistic_form, holistic_run, holistic_analyze, holistic_download,
    holistic_rubrics, holistic_rubric_add, holistic_rubric_edit,
    holistic_rubric_update, holistic_rubric_delete,
)

# ── URL-registraties (endpoint-naam = functienaam → url_for() werkt ongewijzigd) ─
R = app.add_url_rule   # alias voor leesbaarheid

# Authenticatie
R('/login',   'login',   login,   methods=['GET', 'POST'])
R('/logout',  'logout',  logout)
R('/',        'index',   index)
R('/demo_loader', 'demo_loader', demo_loader)

# Documenten
R('/upload',                              'upload_document',    upload_document,    methods=['GET', 'POST'])
R('/api/upload',                          'api_upload_document', api_upload_document, methods=['POST'])
R('/documents',                           'list_documents',     list_documents)
R('/api/analysis/<int:document_id>/status', 'analysis_status_api', analysis_status_api)
R('/analysis/<int:document_id>',          'document_analysis',  document_analysis)
R('/documents/<int:document_id>/export',            'export_document',   export_document)
R('/documents/<int:document_id>/export-select',    'export_select',     export_select,     methods=['GET', 'POST'])
R('/documents/<int:document_id>/reanalyze',        'reanalyze_document', reanalyze_document)
R('/documents/<int:document_id>/reanalyze-partial','reanalyze_partial',  reanalyze_partial, methods=['POST'])

# Criteria
R('/criteria',                          'list_criteria',         list_criteria)
R('/criteria/add',                      'add_criterion',         add_criterion,        methods=['GET', 'POST'])
R('/criteria/edit/<int:id>',            'edit_criterion',        edit_criterion,       methods=['GET', 'POST'])
R('/criteria/delete/<int:id>',          'delete_criterion',      delete_criterion,     methods=['POST'])
R('/criteria/<int:id>/map_sections',    'map_criteria_to_sections', map_criteria_to_sections, methods=['GET', 'POST'])
R('/criteria_templates',                'list_criteria_templates',  list_criteria_templates)
R('/criteria_templates/add',            'add_criteria_template',    add_criteria_template, methods=['GET', 'POST'])

# Criteria instances (gekoppeld aan document type)
R('/document_types/<int:doc_type_id>/criteria',     'list_document_type_criteria',   list_document_type_criteria)
R('/document_types/<int:doc_type_id>/criteria/add', 'add_criteria_to_document_type', add_criteria_to_document_type, methods=['GET', 'POST'])
R('/criteria_instances/<int:instance_id>/edit',     'edit_criteria_instance',         edit_criteria_instance,        methods=['GET', 'POST'])
R('/criteria_instances/<int:instance_id>/delete',   'delete_criteria_instance',       delete_criteria_instance,      methods=['POST'])

# Secties
R('/sections',              'list_sections', list_sections)
R('/sections/add',          'add_section',   add_section,   methods=['GET', 'POST'])
R('/sections/edit/<int:id>', 'edit_section',  edit_section,  methods=['GET', 'POST'])
R('/sections/delete/<int:id>', 'delete_section', delete_section, methods=['POST'])

# Document types
R('/document_types',                     'list_document_types',  list_document_types)
R('/document_types/add',                 'add_document_type',    add_document_type,   methods=['GET', 'POST'])
R('/document_types/edit/<int:id>',       'edit_document_type',   edit_document_type,  methods=['GET', 'POST'])
R('/document_types/delete/<int:id>',     'delete_document_type', delete_document_type, methods=['POST'])
R('/document_types/organization/<int:org_id>',      'list_organization_document_types',  list_organization_document_types)
R('/document_types/organization/<int:org_id>/add',  'add_organization_document_type',    add_organization_document_type, methods=['GET', 'POST'])
R('/document_types/<int:doc_type_id>/sections/manage', 'manage_document_type_sections',  manage_document_type_sections)
R('/document_types/<int:doc_type_id>/sections/add',    'add_section_to_document_type',   add_section_to_document_type,  methods=['POST'])
R('/document_types/<int:doc_type_id>/sections/<int:section_id>/remove',
  'remove_section_from_document_type', remove_section_from_document_type, methods=['POST'])

# Organisaties
R('/organizations',              'list_organizations', list_organizations)
R('/organizations/add',          'add_organization',   add_organization,   methods=['GET', 'POST'])
R('/organizations/edit/<int:id>', 'edit_organization',  edit_organization,  methods=['GET', 'POST'])
R('/organizations/delete/<int:id>', 'delete_organization', delete_organization, methods=['POST'])

# Gebruikers
R('/users',              'list_users', list_users)
R('/users/add',          'add_user',   add_user,   methods=['GET', 'POST'])
R('/users/edit/<int:id>', 'edit_user',  edit_user,  methods=['GET', 'POST'])
R('/users/delete/<int:id>', 'delete_user', delete_user, methods=['POST'])

# Onboarding wizard + uitnodigingen
R('/onboarding',          'onboarding_wizard', onboarding_wizard)
R('/onboarding/step/1',   'onboarding_step1',  onboarding_step1,  methods=['POST'])
R('/onboarding/step/2',   'onboarding_step2',  onboarding_step2,  methods=['POST'])
R('/onboarding/step/3',   'onboarding_step3',  onboarding_step3,  methods=['POST'])
R('/onboarding/step/4',   'onboarding_step4',  onboarding_step4,  methods=['POST'])
R('/invite/<token>',      'invite_accept',     invite_accept,     methods=['GET', 'POST'])
R('/welcome',             'welcome',           welcome)

# Overig
R('/performance', 'performance_stats', performance_stats)

# Holistische analyse (PROTOTYPE — LLM-first, geen secties/criteria nodig)
R('/holistic',                   'holistic_form',     holistic_form)
R('/holistic/run',               'holistic_run',      holistic_run,      methods=['POST'])
R('/holistic/analyze',           'holistic_analyze',  holistic_analyze,  methods=['POST'])
R('/holistic/download/<naam>',   'holistic_download', holistic_download)
R('/holistic/rubrics',                  'holistic_rubrics',       holistic_rubrics)
R('/holistic/rubrics/add',              'holistic_rubric_add',    holistic_rubric_add,    methods=['POST'])
R('/holistic/rubrics/<rubric_id>/edit',   'holistic_rubric_edit',   holistic_rubric_edit)
R('/holistic/rubrics/<rubric_id>/update', 'holistic_rubric_update', holistic_rubric_update, methods=['POST'])
R('/holistic/rubrics/<rubric_id>/delete', 'holistic_rubric_delete', holistic_rubric_delete, methods=['POST'])

# ── Start ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
    port = int(os.environ.get('PORT', 5000))
    app.run(
        debug=debug_mode,
        host='0.0.0.0',
        port=port,
        # Gebruik de 'stat'-reloader in plaats van watchdog.
        # Watchdog triggert op Windows op stdlib-bestanden (asyncio, zoneinfo, ...)
        # wanneer een achtergrond-thread ze importeert — dit veroorzaakt een
        # WinError 10038 socket-fout midden in een lopende analyse.
        # De stat-reloader pollt alleen project-bestanden en kent dit probleem niet.
        reloader_type='stat',
    )
