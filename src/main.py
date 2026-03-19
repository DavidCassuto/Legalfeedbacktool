# C:\ProjectFT\src\main.py

import os
import re
import sqlite3
import json
import time
import logging
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, flash, g, current_app, abort, session
import traceback

# Debug logging voor inline comments module
logging.basicConfig(level=logging.DEBUG)
logging.getLogger('analysis.inline_word_comments').setLevel(logging.DEBUG)

# Importeer functies uit je eigen modules
# AANGEPAST: Importeer db_utils direct vanuit src/
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import db_utils
from analysis import document_parsing
from analysis import section_recognition
from analysis import criterion_checking
from ai_feedback import AIFeedbackGenerator
from word_export import WordFeedbackExporter
from analysis.inline_word_comments import add_inline_comments
from werkzeug.security import generate_password_hash, check_password_hash
from auth import login_required, admin_required, current_user_id, is_admin

# Importeer database optimalisaties
from database_optimizations import (
    initialize_sqlite_optimizer, 
    get_optimized_db, 
    get_section_content_cached,
    save_section_content_optimized,
    batch_save_section_content,
    performance_monitor,
    optimize_database_for_multiple_users
)

# ================================================================
# Flask App Configuratie
# ================================================================
app = Flask(__name__, instance_relative_config=True, template_folder='templates') 

# Definieer de paden
BASE_DIR = os.path.abspath(os.path.dirname(__file__)) # src directory
INSTANCE_PATH = os.path.join(BASE_DIR, '..', 'instance') # parent directory van src, dan 'instance'
UPLOAD_FOLDER = os.path.join(INSTANCE_PATH, 'uploads')
DATABASE = os.path.join(INSTANCE_PATH, 'documents.db') # Dit is de database die Flask gebruikt

# Zorg ervoor dat de 'instance' en 'uploads' mappen bestaan
os.makedirs(INSTANCE_PATH, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config.from_mapping(
    SECRET_KEY='feedback-tool-secret-key-2024',
    DATABASE=DATABASE,
    UPLOAD_FOLDER=UPLOAD_FOLDER
)

# Initialiseer database optimalisaties bij startup
print("[INIT] Initialiseren van database optimalisaties...")
initialize_sqlite_optimizer(DATABASE)
optimize_database_for_multiple_users()

# Functie om database connectie te krijgen (geoptimaliseerd)
def get_db():
    if 'db' not in g:
        start_time = time.time()
        g.db = get_optimized_db()
        duration = time.time() - start_time
        performance_monitor.record_query_time('connection', duration)
        
        # Check of database al bestaat door te kijken of er secties zijn
        cursor = g.db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sections'")
        if cursor.fetchone() is None:
            # Database bestaat nog niet, initialiseer
            print("DEBUG: Database bestaat nog niet, initialiseren...")
            db_utils.initialize_db(g.db)
        else:
            # Database bestaat al, check of er secties zijn
            cursor.execute("SELECT COUNT(*) FROM sections")
            section_count = cursor.fetchone()[0]
            if section_count == 0:
                db_utils.initialize_db(g.db)

        # Altijd migraties uitvoeren (idempotent — veilig bij herhaalde aanroepen)
        db_utils.migrate_db(g.db)

    return g.db

# Functie om database connectie te sluiten
@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()
        print("Databaseverbinding gesloten (via close_db).")

# ================================================================
# Globale Context Processors
# ================================================================
@app.context_processor
def inject_global_data():
    """Injecteert algemene data in alle templates, zoals het huidige jaar."""
    return {'now': datetime.now()}

# ================================================================
# Authenticatie routes (Login / Logout)
# ================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login pagina."""
    if 'user_id' in session:
        return redirect(url_for('upload_document'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        db = get_db()
        user = db.execute(
            'SELECT * FROM users WHERE username = ?', (username,)
        ).fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id']   = user['id']
            session['username']  = user['username']
            session['user_role'] = user['role']
            if user['role'] == 'admin':
                return redirect(url_for('index'))
            else:
                return redirect(url_for('upload_document'))
        else:
            flash('Ongeldige gebruikersnaam of wachtwoord.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    """Uitloggen en sessie wissen."""
    session.clear()
    flash('Je bent uitgelogd.', 'info')
    return redirect(url_for('login'))


@app.route('/demo_loader')
def demo_loader():
    """Demo pagina voor de laadanimatie."""
    return render_template('demo_loader.html')


# ================================================================
# Hoofdroutes (Welkomst, Upload, Documenten Overzicht, Analyse)
# ================================================================

@app.route('/')
@login_required
def index():
    """Welkomstpagina van de applicatie."""
    if not is_admin():
        return redirect(url_for('upload_document'))
    return render_template('index.html')

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_document():
    """Route voor het uploaden van een nieuw document."""
    db = get_db()
    document_types = db.execute('SELECT id, name FROM document_types').fetchall()
    
    # Haal organizations op
    try:
        organizations = db.execute('SELECT id, name FROM organizations').fetchall()
    except sqlite3.OperationalError:
        organizations = [] # Val terug op lege lijst als tabel nog niet bestaat

    form_data = {}

    if request.method == 'POST':
        form_data = request.form # Houd ingediende data bij voor 'selected' state in template

        file = request.files.get('file')
        document_type_id = request.form.get('document_type_id')
        organization_id = request.form.get('organization_id')

        if not file or file.filename == '':
            flash('Geen bestand geselecteerd!', 'danger')
        elif not document_type_id:
            flash('Selecteer een documenttype!', 'danger')
        else:
            try:
                original_filename = file.filename
                if original_filename is None:
                    flash('Ongeldige bestandsnaam!', 'danger')
                    return render_template('upload.html', 
                                           document_types=document_types, 
                                           organizations=organizations,
                                           form_data=form_data)
                
                filename = secure_filename(original_filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)

                # Sla document op in DB
                document_id = db_utils.get_or_create_document(db, original_filename, file_path)

                # Werk document_type_id, organization_id, file_size, analysis_status en uploaded_by bij
                file_size = os.path.getsize(file_path)
                db.execute(
                    'UPDATE documents SET document_type_id = ?, organization_id = ?, file_size = ?, analysis_status = ?, uploaded_by = ? WHERE id = ?',
                    (document_type_id, organization_id, file_size, 'pending', current_user_id(), document_id)
                )
                db.commit()

                flash('Document succesvol geüpload! Starten met analyse...', 'success')
                return redirect(url_for('document_analysis', document_id=document_id))

            except Exception as e:
                flash(f'Fout bij uploaden: {e}', 'danger')
                traceback.print_exc() 

    # Voor GET request of bij fouten in POST, render template opnieuw
    return render_template('upload.html', 
                           document_types=document_types, 
                           organizations=organizations,
                           form_data=form_data)

@app.route('/documents')
@login_required
def list_documents():
    """Overzichtspagina van geüploade documenten.
    Admins zien alle documenten; consumenten zien alleen hun eigen documenten."""
    db = get_db()
    if is_admin():
        documents = db.execute('''
            SELECT d.*, dt.name AS document_type_name, o.name AS organization_name,
                   u.username AS uploader_name
            FROM documents d
            JOIN document_types dt ON d.document_type_id = dt.id
            LEFT JOIN organizations o ON d.organization_id = o.id
            LEFT JOIN users u ON d.uploaded_by = u.id
            ORDER BY d.uploaded_at DESC
        ''').fetchall()
    else:
        documents = db.execute('''
            SELECT d.*, dt.name AS document_type_name, o.name AS organization_name,
                   u.username AS uploader_name
            FROM documents d
            JOIN document_types dt ON d.document_type_id = dt.id
            LEFT JOIN organizations o ON d.organization_id = o.id
            LEFT JOIN users u ON d.uploaded_by = u.id
            WHERE d.uploaded_by = ?
            ORDER BY d.uploaded_at DESC
        ''', (current_user_id(),)).fetchall()
    return render_template('documents.html', documents=documents)

@app.route('/analysis/<int:document_id>')
@login_required
def document_analysis(document_id):
    """Gedetailleerde analyseweergave voor een specifiek document."""
    db = get_db()

    document = db.execute('SELECT * FROM documents WHERE id = ?', (document_id,)).fetchone()
    if document is None:
        flash('Document niet gevonden.', 'danger')
        return redirect(url_for('list_documents'))

    document_type = db.execute('SELECT * FROM document_types WHERE id = ?', (document['document_type_id'],)).fetchone()
    if document_type is None:
        flash('Documenttype niet gevonden voor dit document.', 'danger')
        return redirect(url_for('list_documents'))

    organization = db.execute('SELECT * FROM organizations WHERE id = ?', (document['organization_id'],)).fetchone()

    # Check of het bestand fysiek bestaat
    file_exists = os.path.exists(document['file_path'])
    if not file_exists:
        flash(f"Bestand '{document['original_filename']}' niet gevonden op server. Kan niet analyseren.", 'danger')
        db.execute('UPDATE documents SET analysis_status = ? WHERE id = ?', ('failed', document_id))
        db.commit()
        return redirect(url_for('list_documents'))

    # Start analyse als de status pending is, 'failed' is, of geforceerd opnieuw analyseren
    if document['analysis_status'] in ['pending', 'failed'] or request.args.get('reanalyze'):
        try:
            print(f"Start analyse voor document ID: {document_id}")
            # 1. Document parsen
            full_document_text, document_paragraphs, headings_in_document = document_parsing.parse_document(document['file_path'])
            
            print(f"--- DEBUGGING in extract_document_content ---")
            print(f"Totaal aantal paragrafen: {len(document_paragraphs)}")
            print(f"Gevonden headings: {len(headings_in_document)}")
            
            # 2. Sectieherkenning
            # Haal secties op die relevant zijn voor dit documenttype:
            #   1) Direct gekoppeld via sections.document_type_id = X
            #   2) Gekoppeld via de koppeltabel document_type_sections
            #   3) Universele secties (document_type_id IS NULL en niet in de koppeltabel)
            expected_sections_metadata = db.execute(
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
                   ORDER BY
                       CASE WHEN s.document_type_id IS NULL THEN 0 ELSE 1 END,
                       s.order_index''',
                {'dt_id': document_type['id']}
            ).fetchall()

            recognized_sects_raw = section_recognition.recognize_and_enrich_sections(
                full_document_text,
                document_paragraphs,
                headings_in_document,
                expected_sections_metadata
            )

            # Sla sectie-content op in database (geoptimaliseerd)
            save_start = time.time()
            batch_save_section_content(db, recognized_sects_raw)
            save_duration = time.time() - save_start
            performance_monitor.record_query_time('save_section_content', save_duration)
            print(f"[OK] Sectie-content opslag voltooid in {save_duration:.2f} seconden")

            # Combineer sectie-info uit DB met analyse-resultaten
            # Gebruik dezelfde brede query als hierboven zodat de display-lijst klopt
            all_db_sections = db.execute(
                '''SELECT DISTINCT s.id, s.name, s.level, s.identifier
                   FROM sections s
                   LEFT JOIN document_type_sections dts ON s.id = dts.section_id
                   WHERE s.document_type_id = :dt_id
                      OR dts.document_type_id = :dt_id
                      OR (s.document_type_id IS NULL
                          AND NOT EXISTS (
                              SELECT 1 FROM document_type_sections dts2
                              WHERE dts2.section_id = s.id
                          ))
                   ORDER BY
                       CASE WHEN s.document_type_id IS NULL THEN 0 ELSE 1 END,
                       s.order_index''',
                {'dt_id': document_type['id']}
            ).fetchall()

            # Maak een map voor snelle lookup van DB secties op identifier
            db_sections_map = {s['identifier']: dict(s) for s in all_db_sections}

            # Verrijk de herkende secties met 'found', 'word_count', 'confidence'
            display_sections = []
            for db_sec_info in all_db_sections:
                recognized_sec = next((s for s in recognized_sects_raw if s.get('db_id') == db_sec_info['id']), None)
                
                section_data = {
                    'id': db_sec_info['id'], # DB ID van de sectie
                    'name': db_sec_info['name'],
                    'level': db_sec_info['level'],
                    'found': recognized_sec.get('found', False) if recognized_sec else False,
                    'word_count': recognized_sec.get('word_count', 0) if recognized_sec else 0,
                    'confidence': recognized_sec.get('confidence', None) if recognized_sec else None,
                    'content': recognized_sec.get('content', '') if recognized_sec else '', # Sla content op voor latere weergave
                    'identifier': db_sec_info['identifier'], # Nodig voor JS `showSectionContent`
                    # Sla de originele heading-tekst op voor Word comment plaatsing
                    # (secties gematcht via alias/fuzzy hebben een andere naam dan heading-tekst)
                    'heading_text': recognized_sec.get('heading_text', '') if recognized_sec else '',
                }
                display_sections.append(section_data)

            # 3. Criteria ophalen en feedback genereren
            # Haal alle ingeschakelde criteria op voor dit documenttype, inclusief section_mappings
            criteria_for_analysis = db_utils.get_criteria_for_document_type(db, document_type['id'])
            
            # Voer de feedback generatie uit (simulatie of echte LLM-call)
            generated_feedback_items = criterion_checking.generate_feedback(
                full_document_text,
                recognized_sects_raw, # Geef de ruwe herkende secties mee
                criteria_for_analysis,
                db, # Geef de db-verbinding door voor eventuele extra lookups
                document_id,
                document_type['id']
            )

            # 4. Sla geanalyseerde data op in het document (optioneel, voor caching)
            analysis_summary = {
                'sections': [
                    {
                        'id': s['id'],
                        'name': s['name'],
                        'level': s['level'],
                        'found': s['found'],
                        'word_count': s['word_count'],
                        'confidence': s['confidence'],
                        'content': s['content'] # Sla content ook op in analysis_data voor makkelijk ophalen
                    } for s in display_sections
                ],
                'feedback': generated_feedback_items,
                'analysis_timestamp': datetime.now().isoformat()
            }

            # Update document status en sla analysis data op
            db.execute(
                'UPDATE documents SET analysis_status = ?, analysis_data = ? WHERE id = ?',
                ('completed', json.dumps(analysis_summary), document_id)
            )
            db.commit()

            flash('Analyse succesvol voltooid!', 'success')

        except Exception as e:
            print(f"Fout tijdens analyse: {e}")
            traceback.print_exc()
            flash(f'Fout tijdens analyse: {e}', 'danger')
            db.execute('UPDATE documents SET analysis_status = ? WHERE id = ?', ('failed', document_id))
            db.commit()
            display_sections = []
            generated_feedback_items = []

    else:
        # Geen analyse gedraaid: lees opgeslagen data uit de database
        try:
            if document['analysis_data']:
                analysis_data = json.loads(document['analysis_data'])
                display_sections = analysis_data.get('sections', [])
                generated_feedback_items = analysis_data.get('feedback', [])
            else:
                display_sections = []
                generated_feedback_items = []
        except (json.JSONDecodeError, TypeError):
            display_sections = []
            generated_feedback_items = []

    # Bereken feedback statistieken
    feedback_stats = {
        'violations': len([f for f in generated_feedback_items if f.get('status') in ('violation', 'error')]),
        'warnings':   len([f for f in generated_feedback_items if f.get('status') == 'warning']),
        'info':       len([f for f in generated_feedback_items if f.get('status') == 'info']),
        'passed':     len([f for f in generated_feedback_items if f.get('status') == 'ok']),
    }

    # Bereken alinea's per sectie (voor weergave per alinea in de template)
    def split_into_paragraphs_for_display(content):
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        def is_heading_like(line):
            words = re.findall(r'\b\w+\b', line)
            return len(words) <= 10 and not re.search(r'[.!?]$', line.strip())
        paragraphs = []
        current = []
        for line in content.split('\n'):
            s = line.strip()
            if not s:
                if current:
                    paragraphs.append(' '.join(current))
                    current = []
            elif is_heading_like(s):
                if current:
                    paragraphs.append(' '.join(current))
                    current = []
            else:
                current.append(s)
        if current:
            paragraphs.append(' '.join(current))
        return paragraphs

    for section in display_sections:
        section['paragraphs'] = split_into_paragraphs_for_display(section.get('content', ''))

    # Groepeer feedback per sectie-naam voor overzichtelijke weergave
    feedback_by_section = {}
    non_section_feedback = []
    for fb in generated_feedback_items:
        sname = fb.get('section_name')
        if sname:
            feedback_by_section.setdefault(sname, []).append(fb)
        else:
            non_section_feedback.append(fb)

    return render_template('analysis.html',
                           document=document,
                           document_type=document_type,
                           organization=organization,
                           sections=display_sections,
                           feedback_items=generated_feedback_items,
                           feedback_by_section=feedback_by_section,
                           non_section_feedback=non_section_feedback,
                           feedback_stats=feedback_stats)

@app.route('/documents/<int:document_id>/export')
@login_required
def export_document(document_id):
    """Exporteer feedback naar Word document."""
    db = get_db()
    
    document = db.execute('SELECT * FROM documents WHERE id = ?', (document_id,)).fetchone()
    if document is None:
        flash('Document niet gevonden.', 'danger')
        return redirect(url_for('list_documents'))

    try:
        # Haal analysis data op
        if not document['analysis_data']:
            flash('Geen analyse data beschikbaar voor export.', 'danger')
            return redirect(url_for('document_analysis', document_id=document_id))

        analysis_data  = json.loads(document['analysis_data'])
        feedback_items = analysis_data.get('feedback', [])
        saved_sections = analysis_data.get('sections', [])

        # Controleer of het originele bestand nog bestaat
        if not os.path.exists(document['file_path']):
            flash('Origineel bestand niet gevonden op de server.', 'danger')
            return redirect(url_for('document_analysis', document_id=document_id))

        # Maak export bestandsnaam
        base_name       = os.path.splitext(document['original_filename'])[0]
        export_filename = f"{base_name}_gecommentarieerd.docx"
        export_path     = os.path.join(app.config['UPLOAD_FOLDER'], export_filename)

        # Voeg inline comments toe aan het originele Word document
        add_inline_comments(
            original_docx_path  = document['file_path'],
            feedback_items      = feedback_items,
            recognized_sections = saved_sections,
            output_path         = export_path,
        )

        # Stuur bestand naar gebruiker
        from flask import send_file
        return send_file(export_path, as_attachment=True, download_name=export_filename)

    except Exception as e:
        flash(f'Fout bij export: {e}', 'danger')
        traceback.print_exc()
        return redirect(url_for('document_analysis', document_id=document_id))

@app.route('/documents/<int:document_id>/reanalyze')
@login_required
def reanalyze_document(document_id):
    """Forceer heranalyse van een document."""
    return redirect(url_for('document_analysis', document_id=document_id, reanalyze=True))

# Performance monitoring route
@app.route('/performance')
@admin_required
def performance_stats():
    """Toont performance statistieken."""
    stats = performance_monitor.get_performance_summary()
    return render_template('performance.html', stats=stats)

# ================================================================
# Criteria Management Routes
# ================================================================

@app.route('/criteria')
@admin_required
def list_criteria():
    """Overzichtspagina van alle criteria."""
    db = get_db()
    criteria = db.execute('''
        SELECT c.*, o.name AS organization_name
        FROM criteria c
        LEFT JOIN organizations o ON c.organization_id = o.id
        ORDER BY c.name
    ''').fetchall()
    return render_template('criteria_list.html', criteria=criteria)

@app.route('/criteria/add', methods=('GET', 'POST'))
@admin_required
def add_criterion():
    """Route voor het toevoegen van een nieuw criterium."""
    db = get_db()
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description', '')
        organization_id = request.form.get('organization_id')
        rule_type = request.form.get('rule_type', 'content_check')
        application_scope = request.form.get('application_scope', 'document')
        severity = request.form.get('severity', 'warning')
        # Checkbox stuurt 'on' als aangevinkt, niets als niet → converteer naar int 1/0
        is_enabled = 1 if request.form.get('is_enabled') else 0
        show_suggestion = bool(request.form.get('show_suggestion'))
        color = request.form.get('color', '#3B82F6')
        error_message = request.form.get('error_message', '').strip()
        fixed_feedback_text = request.form.get('fixed_feedback_text', '').strip()
        frequency_unit = request.form.get('frequency_unit', 'document')
        max_mentions_per = int(request.form.get('max_mentions_per') or 0)
        expected_value_min_raw = request.form.get('expected_value_min', '').strip()
        expected_value_max_raw = request.form.get('expected_value_max', '').strip()
        expected_value_min = float(expected_value_min_raw) if expected_value_min_raw else None
        expected_value_max = float(expected_value_max_raw) if expected_value_max_raw else None
        check_type = request.form.get('check_type', 'none')
        # Parameters opbouwen op basis van check_type
        if check_type in ('keyword_forbidden', 'keyword_required'):
            keywords_raw = request.form.get('keywords', '').strip()
            kw_list = [k.strip() for k in keywords_raw.split(',') if k.strip()]
            parameters = json.dumps({'keywords': kw_list, 'show_suggestion': show_suggestion}, ensure_ascii=False) if kw_list else json.dumps({'show_suggestion': show_suggestion})
        elif check_type == 'llm_review':
            parameters = json.dumps({
                'llm_role_prompt':     request.form.get('llm_role_prompt', '').strip(),
                'llm_criteria_prompt': request.form.get('llm_criteria_prompt', '').strip(),
                'llm_check_ai_style':  bool(request.form.get('llm_check_ai_style')),
                'show_suggestion':     show_suggestion,
            }, ensure_ascii=False)
        else:
            parameters = json.dumps({'show_suggestion': show_suggestion})

        if not name:
            flash('Naam is verplicht!', 'danger')
        else:
            try:
                cursor = db.cursor()
                cursor.execute(
                    '''INSERT INTO criteria
                       (name, description, rule_type, application_scope, severity, is_enabled,
                        organization_id, color, error_message, fixed_feedback_text,
                        frequency_unit, max_mentions_per, expected_value_min, expected_value_max,
                        check_type, parameters)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (name, description, rule_type, application_scope, severity, is_enabled,
                     organization_id, color, error_message or None, fixed_feedback_text or None,
                     frequency_unit, max_mentions_per, expected_value_min, expected_value_max,
                     check_type, parameters)
                )
                db.commit()
                flash('Criterium succesvol toegevoegd!', 'success')
                return redirect(url_for('list_criteria'))
            except Exception as e:
                flash(f'Fout bij toevoegen: {e}', 'danger')
                traceback.print_exc()

    organizations = db.execute('SELECT id, name FROM organizations').fetchall()
    
    return render_template('add_criterion.html', 
                           organizations=organizations)

@app.route('/criteria/edit/<int:id>', methods=('GET', 'POST'))
@admin_required
def edit_criterion(id):
    """Route voor het bewerken van een criterium."""
    db = get_db()
    criterion = db.execute('SELECT * FROM criteria WHERE id = ?', (id,)).fetchone()
    
    if criterion is None:
        flash('Criterium niet gevonden.', 'danger')
        return redirect(url_for('list_criteria'))
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description', '')
        organization_id = request.form.get('organization_id')
        rule_type = request.form.get('rule_type', 'mention')
        application_scope = request.form.get('application_scope', 'document_only')
        severity = request.form.get('severity', 'warning')
        # Checkbox stuurt 'on' als aangevinkt, niets als niet → converteer naar int 1/0
        is_enabled = 1 if request.form.get('is_enabled') else 0
        show_suggestion = bool(request.form.get('show_suggestion'))
        color = request.form.get('color', '#3B82F6')
        error_message = request.form.get('error_message', '').strip()
        fixed_feedback_text = request.form.get('fixed_feedback_text', '').strip()
        frequency_unit = request.form.get('frequency_unit', 'document')
        max_mentions_per = int(request.form.get('max_mentions_per') or 0)
        expected_value_min_raw = request.form.get('expected_value_min', '').strip()
        expected_value_max_raw = request.form.get('expected_value_max', '').strip()
        expected_value_min = float(expected_value_min_raw) if expected_value_min_raw else None
        expected_value_max = float(expected_value_max_raw) if expected_value_max_raw else None
        check_type = request.form.get('check_type', 'none')
        # Parameters opbouwen op basis van check_type
        if check_type in ('keyword_forbidden', 'keyword_required'):
            keywords_raw = request.form.get('keywords', '').strip()
            kw_list = [k.strip() for k in keywords_raw.split(',') if k.strip()]
            parameters = json.dumps({'keywords': kw_list, 'show_suggestion': show_suggestion}, ensure_ascii=False) if kw_list else json.dumps({'show_suggestion': show_suggestion})
        elif check_type == 'llm_review':
            parameters = json.dumps({
                'llm_role_prompt':     request.form.get('llm_role_prompt', '').strip(),
                'llm_criteria_prompt': request.form.get('llm_criteria_prompt', '').strip(),
                'llm_check_ai_style':  bool(request.form.get('llm_check_ai_style')),
                'show_suggestion':     show_suggestion,
            }, ensure_ascii=False)
        else:
            parameters = json.dumps({'show_suggestion': show_suggestion})

        if not name:
            flash('Naam is verplicht!', 'danger')
        else:
            try:
                db.execute(
                    '''UPDATE criteria
                       SET name = ?, description = ?, organization_id = ?,
                           rule_type = ?, application_scope = ?, severity = ?, is_enabled = ?,
                           color = ?, error_message = ?, fixed_feedback_text = ?,
                           frequency_unit = ?, max_mentions_per = ?,
                           expected_value_min = ?, expected_value_max = ?,
                           check_type = ?, parameters = ?
                       WHERE id = ?''',
                    (name, description, organization_id, rule_type,
                     application_scope, severity, is_enabled, color,
                     error_message or None, fixed_feedback_text or None,
                     frequency_unit, max_mentions_per,
                     expected_value_min, expected_value_max,
                     check_type, parameters, id)
                )
                db.commit()
                flash('Criterium succesvol bijgewerkt!', 'success')
                return redirect(url_for('list_criteria'))
            except Exception as e:
                flash(f'Fout bij bijwerken: {e}', 'danger')
                traceback.print_exc()

    organizations = db.execute('SELECT id, name FROM organizations').fetchall()

    # Parseer parameters JSON voor pre-filling in het formulier
    criterion_keywords = ''
    llm_role_prompt = ''
    llm_criteria_prompt = ''
    llm_check_ai_style = False
    try:
        criterion_dict = dict(criterion)
        params = json.loads(criterion_dict.get('parameters') or '{}')
        criterion_keywords = ', '.join(params.get('keywords', []))
        llm_role_prompt     = params.get('llm_role_prompt', '')
        llm_criteria_prompt = params.get('llm_criteria_prompt', '')
        llm_check_ai_style  = bool(params.get('llm_check_ai_style', False))
        # show_suggestion: standaard True (bestaande criteria tonen suggestie tenzij expliciet uitgeschakeld)
        show_suggestion     = params.get('show_suggestion', True)
    except (json.JSONDecodeError, TypeError, KeyError, IndexError):
        show_suggestion = True

    return render_template('edit_criterion.html',
                           criterion=criterion,
                           organizations=organizations,
                           criterion_keywords=criterion_keywords,
                           llm_role_prompt=llm_role_prompt,
                           llm_criteria_prompt=llm_criteria_prompt,
                           llm_check_ai_style=llm_check_ai_style,
                           show_suggestion=show_suggestion,
                           current_doc_type_id=None)

@app.route('/criteria/delete/<int:id>', methods=('POST',))
@admin_required
def delete_criterion(id):
    """Route voor het verwijderen van een criterium."""
    db = get_db()
    criterion = db.execute('SELECT * FROM criteria WHERE id = ?', (id,)).fetchone()
    
    if criterion is None:
        flash('Criterium niet gevonden.', 'danger')
    else:
        try:
            db.execute('DELETE FROM criteria WHERE id = ?', (id,))
            db.commit()
            flash('Criterium succesvol verwijderd!', 'success')
        except Exception as e:
            flash(f'Fout bij verwijderen: {e}', 'danger')
            traceback.print_exc()
    
    return redirect(url_for('list_criteria'))

@app.route('/criteria/<int:id>/map_sections', methods=('GET', 'POST'))
@admin_required
def map_criteria_to_sections(id):
    """Route voor het mappen van criteria naar secties."""
    db = get_db()
    criterion = db.execute('SELECT * FROM criteria WHERE id = ?', (id,)).fetchone()
    
    if criterion is None:
        flash('Criterium niet gevonden.', 'danger')
        return redirect(url_for('list_criteria'))
    
    if request.method == 'POST':
        selected_sections = request.form.getlist('selected_sections')
        excluded_sections = request.form.getlist('excluded_sections')
        new_scope = request.form.get('application_scope')

        try:
            # Sla application_scope op als die is gewijzigd
            if new_scope:
                db.execute(
                    'UPDATE criteria SET application_scope = ? WHERE id = ?',
                    (new_scope, id)
                )

            # Verwijder bestaande sectie-mappings
            db.execute('DELETE FROM criteria_section_mappings WHERE criteria_id = ?', (id,))

            # Voeg geselecteerde (inclusie) secties toe
            for section_id in selected_sections:
                db.execute(
                    'INSERT INTO criteria_section_mappings (criteria_id, section_id, is_excluded) VALUES (?, ?, 0)',
                    (id, section_id)
                )

            # Voeg uitgesloten secties toe met is_excluded=1
            for section_id in excluded_sections:
                if section_id not in selected_sections:  # voorkom conflict
                    db.execute(
                        'INSERT INTO criteria_section_mappings (criteria_id, section_id, is_excluded) VALUES (?, ?, 1)',
                        (id, section_id)
                    )

            db.commit()
            flash('Sectie mappings en toepassingsgebied succesvol bijgewerkt!', 'success')
            return redirect(url_for('list_criteria'))
        except Exception as e:
            flash(f'Fout bij mappen: {e}', 'danger')
            traceback.print_exc()
    
    # Haal ALLE secties op (sections tabel heeft geen document_type_id;
    # de koppeling loopt via de junction-tabel document_type_sections)
    all_sections = db.execute('''
        SELECT s.*, p.name AS parent_name
        FROM sections s
        LEFT JOIN sections p ON s.parent_id = p.id
        ORDER BY s.order_index, s.level, s.name
    ''').fetchall()
    
    # Haal huidige mappings op inclusief is_excluded status
    current_mappings = db.execute(
        'SELECT section_id, is_excluded FROM criteria_section_mappings WHERE criteria_id = ?',
        (id,)
    ).fetchall()

    # Maak een dictionary van mapped sections voor de template
    mapped_sections = {}
    for m in current_mappings:
        mapped_sections[m['section_id']] = {'is_excluded': bool(m['is_excluded'])}
    
    return render_template('criteria_section_mapping.html', 
                           criterion=criterion,
                           all_sections=all_sections,
                           mapped_sections=mapped_sections)

# ================================================================
# Secties Management Routes
# ================================================================

@app.route('/sections')
@admin_required
def list_sections():
    """Overzichtspagina van alle secties."""
    db = get_db()
    sections = db.execute('''
        SELECT s.*, p.name AS parent_name
        FROM sections s
        LEFT JOIN sections p ON s.parent_id = p.id
        ORDER BY s.order_index, s.level, s.name
    ''').fetchall()
    return render_template('sections_list.html', sections=sections)

@app.route('/sections/add', methods=('GET', 'POST'))
@admin_required
def add_section():
    """Route voor het toevoegen van een nieuwe sectie."""
    db = get_db()
    
    if request.method == 'POST':
        name = request.form['name']
        identifier = request.form['identifier']
        level = request.form.get('level', 1)
        order_index = request.form.get('order_index', 0)
        document_type_id = request.form.get('document_type_id')
        alt_names_raw = request.form.get('alternative_names', '').strip()
        # Converteer komma-gescheiden invoer naar JSON array
        alt_names_list = [n.strip() for n in alt_names_raw.split(',') if n.strip()]
        alternative_names_json = json.dumps(alt_names_list)

        if not name or not identifier:
            flash('Naam en identifier zijn verplicht!', 'danger')
        else:
            try:
                cursor = db.cursor()
                cursor.execute(
                    'INSERT INTO sections (name, identifier, level, order_index, document_type_id, alternative_names) VALUES (?, ?, ?, ?, ?, ?)',
                    (name, identifier, level, order_index, document_type_id, alternative_names_json)
                )
                db.commit()
                flash('Sectie succesvol toegevoegd!', 'success')
                return redirect(url_for('list_sections'))
            except Exception as e:
                flash(f'Fout bij toevoegen: {e}', 'danger')
                traceback.print_exc()

    document_types = db.execute('SELECT id, name FROM document_types').fetchall()
    form_data = request.form if request.method == 'POST' else {}
    return render_template('add_section.html', document_types=document_types, form_data=form_data)

@app.route('/sections/edit/<int:id>', methods=('GET', 'POST'))
@admin_required
def edit_section(id):
    """Route voor het bewerken van een sectie."""
    db = get_db()
    section = db.execute('SELECT * FROM sections WHERE id = ?', (id,)).fetchone()
    
    if section is None:
        flash('Sectie niet gevonden.', 'danger')
        return redirect(url_for('list_sections'))
    
    if request.method == 'POST':
        name = request.form['name']
        identifier = request.form['identifier']
        level = request.form.get('level', 1)
        order_index = request.form.get('order_index', 0)
        document_type_id = request.form.get('document_type_id')
        alt_names_raw = request.form.get('alternative_names', '').strip()
        # Converteer komma-gescheiden invoer naar JSON array
        alt_names_list = [n.strip() for n in alt_names_raw.split(',') if n.strip()]
        alternative_names_json = json.dumps(alt_names_list)

        if not name or not identifier:
            flash('Naam en identifier zijn verplicht!', 'danger')
        else:
            try:
                db.execute(
                    'UPDATE sections SET name = ?, identifier = ?, level = ?, order_index = ?, document_type_id = ?, alternative_names = ? WHERE id = ?',
                    (name, identifier, level, order_index, document_type_id, alternative_names_json, id)
                )
                db.commit()
                flash('Sectie succesvol bijgewerkt!', 'success')
                return redirect(url_for('list_sections'))
            except Exception as e:
                flash(f'Fout bij bijwerken: {e}', 'danger')
                traceback.print_exc()

    document_types = db.execute('SELECT id, name FROM document_types').fetchall()
    form_data = request.form if request.method == 'POST' else {}
    # Converteer JSON naar komma-gescheiden string voor weergave in het formulier
    try:
        existing_alt = json.loads(section['alternative_names'] or '[]')
        alt_names_display = ', '.join(existing_alt)
    except (json.JSONDecodeError, TypeError):
        alt_names_display = ''
    return render_template('edit_section.html',
                           section=section,
                           document_types=document_types,
                           form_data=form_data,
                           alt_names_display=alt_names_display)

@app.route('/sections/delete/<int:id>', methods=('POST',))
@admin_required
def delete_section(id):
    """Route voor het verwijderen van een sectie."""
    db = get_db()
    section = db.execute('SELECT * FROM sections WHERE id = ?', (id,)).fetchone()
    
    if section is None:
        flash('Sectie niet gevonden.', 'danger')
    else:
        try:
            db.execute('DELETE FROM sections WHERE id = ?', (id,))
            db.commit()
            flash('Sectie succesvol verwijderd!', 'success')
        except Exception as e:
            flash(f'Fout bij verwijderen: {e}', 'danger')
            traceback.print_exc()
    
    return redirect(url_for('list_sections'))

# ================================================================
# Document Types Management Routes
# ================================================================

@app.route('/document_types')
@admin_required
def list_document_types():
    """Overzichtspagina van alle document types."""
    db = get_db()
    document_types = db.execute('SELECT * FROM document_types ORDER BY name').fetchall()
    return render_template('document_types_list.html', document_types=document_types)

@app.route('/document_types/add', methods=('GET', 'POST'))
@admin_required
def add_document_type():
    """Route voor het toevoegen van een nieuw document type."""
    db = get_db()
    
    if request.method == 'POST':
        name = request.form['name']
        identifier = request.form['identifier']
        description = request.form.get('description', '')
        
        if not name or not identifier:
            flash('Naam en identifier zijn verplicht!', 'danger')
        else:
            try:
                cursor = db.cursor()
                cursor.execute(
                    'INSERT INTO document_types (name, identifier, description) VALUES (?, ?, ?)',
                    (name, identifier, description)
                )
                db.commit()
                flash('Document type succesvol toegevoegd!', 'success')
                return redirect(url_for('list_document_types'))
            except Exception as e:
                flash(f'Fout bij toevoegen: {e}', 'danger')
                traceback.print_exc()

    return render_template('add_document_type.html')

@app.route('/document_types/edit/<int:id>', methods=('GET', 'POST'))
@admin_required
def edit_document_type(id):
    """Route voor het bewerken van een document type."""
    db = get_db()
    document_type = db.execute('SELECT * FROM document_types WHERE id = ?', (id,)).fetchone()
    
    if document_type is None:
        flash('Document type niet gevonden.', 'danger')
        return redirect(url_for('list_document_types'))
    
    if request.method == 'POST':
        name = request.form['name']
        identifier = request.form['identifier']
        # description = request.form.get('description', '')  # Verwijderd
        
        if not name or not identifier:
            flash('Naam en identifier zijn verplicht!', 'danger')
        else:
            try:
                db.execute(
                    'UPDATE document_types SET name = ?, identifier = ? WHERE id = ?',
                    (name, identifier, id)
                )
                db.commit()
                flash('Document type succesvol bijgewerkt!', 'success')
                return redirect(url_for('list_document_types'))
            except Exception as e:
                flash(f'Fout bij bijwerken: {e}', 'danger')
                traceback.print_exc()

    return render_template('edit_document_type.html', document_type=document_type)

@app.route('/document_types/delete/<int:id>', methods=('POST',))
@admin_required
def delete_document_type(id):
    """Route voor het verwijderen van een document type."""
    db = get_db()
    document_type = db.execute('SELECT * FROM document_types WHERE id = ?', (id,)).fetchone()
    
    if document_type is None:
        flash('Document type niet gevonden.', 'danger')
    else:
        try:
            db.execute('DELETE FROM document_types WHERE id = ?', (id,))
            db.commit()
            flash('Document type succesvol verwijderd!', 'success')
        except Exception as e:
            flash(f'Fout bij verwijderen: {e}', 'danger')
            traceback.print_exc()
    
    return redirect(url_for('list_document_types'))

# ================================================================
# Organisaties Management Routes
# ================================================================

@app.route('/organizations')
@admin_required
def list_organizations():
    """Overzichtspagina van alle organisaties."""
    db = get_db()
    organizations = db.execute('SELECT * FROM organizations ORDER BY name').fetchall()
    return render_template('organizations_list.html', organizations=organizations)

@app.route('/organizations/add', methods=('GET', 'POST'))
@admin_required
def add_organization():
    """Route voor het toevoegen van een nieuwe organisatie."""
    db = get_db()
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description', '')
        
        if not name:
            flash('Naam is verplicht!', 'danger')
        else:
            try:
                cursor = db.cursor()
                cursor.execute(
                    'INSERT INTO organizations (name, description) VALUES (?, ?)',
                    (name, description)
                )
                db.commit()
                flash('Organisatie succesvol toegevoegd!', 'success')
                return redirect(url_for('list_organizations'))
            except Exception as e:
                flash(f'Fout bij toevoegen: {e}', 'danger')
                traceback.print_exc()

    return render_template('add_organization.html')

@app.route('/organizations/edit/<int:id>', methods=('GET', 'POST'))
@admin_required
def edit_organization(id):
    """Route voor het bewerken van een organisatie."""
    db = get_db()
    organization = db.execute('SELECT * FROM organizations WHERE id = ?', (id,)).fetchone()
    
    if organization is None:
        flash('Organisatie niet gevonden.', 'danger')
        return redirect(url_for('list_organizations'))
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description', '')
        
        if not name:
            flash('Naam is verplicht!', 'danger')
        else:
            try:
                db.execute(
                    'UPDATE organizations SET name = ?, description = ? WHERE id = ?',
                    (name, description, id)
                )
                db.commit()
                flash('Organisatie succesvol bijgewerkt!', 'success')
                return redirect(url_for('list_organizations'))
            except Exception as e:
                flash(f'Fout bij bijwerken: {e}', 'danger')
                traceback.print_exc()

    return render_template('edit_organization.html', organization=organization)

@app.route('/organizations/delete/<int:id>', methods=('POST',))
@admin_required
def delete_organization(id):
    """Route voor het verwijderen van een organisatie."""
    db = get_db()
    organization = db.execute('SELECT * FROM organizations WHERE id = ?', (id,)).fetchone()
    
    if organization is None:
        flash('Organisatie niet gevonden.', 'danger')
    else:
        try:
            db.execute('DELETE FROM organizations WHERE id = ?', (id,))
            db.commit()
            flash('Organisatie succesvol verwijderd!', 'success')
        except Exception as e:
            flash(f'Fout bij verwijderen: {e}', 'danger')
            traceback.print_exc()
    
    return redirect(url_for('list_organizations'))

# ================================================================
# Geavanceerde Routes (uit main_backup.py)
# ================================================================

@app.route('/document_types/organization/<int:org_id>')
@admin_required
def list_organization_document_types(org_id):
    """Toon document types voor een specifieke organisatie."""
    db = get_db()
    organization = db.execute('SELECT * FROM organizations WHERE id = ?', (org_id,)).fetchone()
    if organization is None:
        flash('Organisatie niet gevonden.', 'danger')
        return redirect(url_for('list_organizations'))
    
    document_types = db.execute('''
        SELECT dt.*, COUNT(s.id) as section_count
        FROM document_types dt
        LEFT JOIN sections s ON dt.id = s.document_type_id
        WHERE dt.organization_id = ?
        GROUP BY dt.id
        ORDER BY dt.name
    ''', (org_id,)).fetchall()
    
    return render_template('organization_document_types.html', 
                           organization=organization,
                           document_types=document_types)

@app.route('/document_types/organization/<int:org_id>/add', methods=('GET', 'POST'))
@admin_required
def add_organization_document_type(org_id):
    """Voeg document type toe voor een specifieke organisatie."""
    db = get_db()
    organization = db.execute('SELECT * FROM organizations WHERE id = ?', (org_id,)).fetchone()
    if organization is None:
        flash('Organisatie niet gevonden.', 'danger')
        return redirect(url_for('list_organizations'))
    
    if request.method == 'POST':
        name = request.form['name']
        identifier = request.form['identifier']
        description = request.form.get('description', '')
        
        if not name or not identifier:
            flash('Naam en identifier zijn verplicht!', 'danger')
        else:
            try:
                cursor = db.cursor()
                cursor.execute(
                    'INSERT INTO document_types (name, identifier, description, organization_id) VALUES (?, ?, ?, ?)',
                    (name, identifier, description, org_id)
                )
                db.commit()
                flash('Document type succesvol toegevoegd!', 'success')
                return redirect(url_for('list_organization_document_types', org_id=org_id))
            except Exception as e:
                flash(f'Fout bij toevoegen: {e}', 'danger')
                traceback.print_exc()

    return render_template('add_organization_document_type.html', organization=organization)

@app.route('/document_types/<int:doc_type_id>/sections/manage')
def manage_document_type_sections(doc_type_id):
    """Beheer secties voor een document type."""
    db = get_db()
    document_type = db.execute('SELECT * FROM document_types WHERE id = ?', (doc_type_id,)).fetchone()
    if document_type is None:
        flash('Document type niet gevonden.', 'danger')
        return redirect(url_for('list_document_types'))
    
    sections = db.execute('''
        SELECT s.*, CASE WHEN dts.section_id IS NOT NULL THEN 1 ELSE 0 END as is_assigned
        FROM sections s
        LEFT JOIN document_type_sections dts ON s.id = dts.section_id AND dts.document_type_id = ?
        ORDER BY s.name
    ''', (doc_type_id,)).fetchall()
    
    return render_template('manage_document_type_sections.html', 
                           document_type=document_type,
                           sections=sections)

@app.route('/document_types/<int:doc_type_id>/sections/add', methods=('POST',))
def add_section_to_document_type(doc_type_id):
    """Voeg sectie toe aan document type."""
    db = get_db()
    section_id = request.form.get('section_id')
    
    if not section_id:
        flash('Sectie is verplicht!', 'danger')
    else:
        try:
            db.execute(
                'INSERT INTO document_type_sections (document_type_id, section_id) VALUES (?, ?)',
                (doc_type_id, section_id)
            )
            db.commit()
            flash('Sectie succesvol toegevoegd aan document type!', 'success')
        except Exception as e:
            flash(f'Fout bij toevoegen: {e}', 'danger')
            traceback.print_exc()
    
    return redirect(url_for('manage_document_type_sections', doc_type_id=doc_type_id))

@app.route('/document_types/<int:doc_type_id>/sections/<int:section_id>/remove', methods=('POST',))
def remove_section_from_document_type(doc_type_id, section_id):
    """Verwijder sectie van document type."""
    db = get_db()
    try:
        db.execute(
            'DELETE FROM document_type_sections WHERE document_type_id = ? AND section_id = ?',
            (doc_type_id, section_id)
        )
        db.commit()
        flash('Sectie succesvol verwijderd van document type!', 'success')
    except Exception as e:
        flash(f'Fout bij verwijderen: {e}', 'danger')
        traceback.print_exc()
    
    return redirect(url_for('manage_document_type_sections', doc_type_id=doc_type_id))

@app.route('/criteria_templates')
@admin_required
def list_criteria_templates():
    """Overzichtspagina van criteria templates."""
    db = get_db()
    templates = db.execute('SELECT * FROM criteria_templates ORDER BY name').fetchall()
    return render_template('criteria_templates_list.html', templates=templates)

@app.route('/criteria_templates/add', methods=('GET', 'POST'))
@admin_required
def add_criteria_template():
    """Route voor het toevoegen van een criteria template."""
    db = get_db()
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description', '')
        
        if not name:
            flash('Naam is verplicht!', 'danger')
        else:
            try:
                cursor = db.cursor()
                cursor.execute(
                    'INSERT INTO criteria_templates (name, description) VALUES (?, ?)',
                    (name, description)
                )
                template_id = cursor.lastrowid
                
                # Voeg criteria toe aan template
                criteria_ids = request.form.getlist('criteria_ids')
                for criterion_id in criteria_ids:
                    db.execute(
                        'INSERT INTO criteria_template_items (template_id, criterion_id) VALUES (?, ?)',
                        (template_id, criterion_id)
                    )
                
                db.commit()
                flash('Criteria template succesvol toegevoegd!', 'success')
                return redirect(url_for('list_criteria_templates'))
            except Exception as e:
                flash(f'Fout bij toevoegen: {e}', 'danger')
                traceback.print_exc()

    criteria = db.execute('SELECT * FROM criteria ORDER BY name').fetchall()
    return render_template('add_criteria_template.html', criteria=criteria)

@app.route('/document_types/<int:doc_type_id>/criteria')
@admin_required
def list_document_type_criteria(doc_type_id):
    """Toon criteria voor een specifiek document type."""
    db = get_db()
    document_type = db.execute('SELECT * FROM document_types WHERE id = ?', (doc_type_id,)).fetchone()
    if document_type is None:
        flash('Document type niet gevonden.', 'danger')
        return redirect(url_for('list_document_types'))
    
    criteria_instances = db.execute('''
        SELECT ci.*, c.name, c.description
        FROM criteria_instances ci
        JOIN criteria c ON ci.criterion_id = c.id
        WHERE ci.document_type_id = ?
        ORDER BY ci.order_index
    ''', (doc_type_id,)).fetchall()
    
    return render_template('document_type_criteria.html', 
                           document_type=document_type,
                           criteria_instances=criteria_instances)

@app.route('/document_types/<int:doc_type_id>/criteria/add', methods=('GET', 'POST'))
@admin_required
def add_criteria_to_document_type(doc_type_id):
    """Voeg criteria toe aan document type."""
    db = get_db()
    document_type = db.execute('SELECT * FROM document_types WHERE id = ?', (doc_type_id,)).fetchone()
    if document_type is None:
        flash('Document type niet gevonden.', 'danger')
        return redirect(url_for('list_document_types'))
    
    if request.method == 'POST':
        criterion_id = request.form.get('criterion_id')
        weight = request.form.get('weight', 1.0)
        order_index = request.form.get('order_index', 0)
        
        if not criterion_id:
            flash('Criterium is verplicht!', 'danger')
        else:
            try:
                cursor = db.cursor()
                cursor.execute(
                    'INSERT INTO criteria_instances (criterion_id, document_type_id, weight, order_index) VALUES (?, ?, ?, ?)',
                    (criterion_id, doc_type_id, weight, order_index)
                )
                db.commit()
                flash('Criterium succesvol toegevoegd aan document type!', 'success')
                return redirect(url_for('list_document_type_criteria', doc_type_id=doc_type_id))
            except Exception as e:
                flash(f'Fout bij toevoegen: {e}', 'danger')
                traceback.print_exc()

    criteria = db.execute('SELECT * FROM criteria ORDER BY name').fetchall()
    return render_template('add_criteria_to_document_type.html', 
                           document_type=document_type,
                           criteria=criteria)

@app.route('/criteria_instances/<int:instance_id>/edit', methods=('GET', 'POST'))
@admin_required
def edit_criteria_instance(instance_id):
    """Bewerk criteria instance."""
    db = get_db()
    instance = db.execute('''
        SELECT ci.*, c.name, c.description, dt.name as document_type_name
        FROM criteria_instances ci
        JOIN criteria c ON ci.criterion_id = c.id
        JOIN document_types dt ON ci.document_type_id = dt.id
        WHERE ci.id = ?
    ''', (instance_id,)).fetchone()
    
    if instance is None:
        flash('Criteria instance niet gevonden.', 'danger')
        return redirect(url_for('list_document_types'))
    
    if request.method == 'POST':
        weight = request.form.get('weight', 1.0)
        order_index = request.form.get('order_index', 0)
        
        try:
            db.execute(
                'UPDATE criteria_instances SET weight = ?, order_index = ? WHERE id = ?',
                (weight, order_index, instance_id)
            )
            db.commit()
            flash('Criteria instance succesvol bijgewerkt!', 'success')
            return redirect(url_for('list_document_type_criteria', doc_type_id=instance['document_type_id']))
        except Exception as e:
            flash(f'Fout bij bijwerken: {e}', 'danger')
            traceback.print_exc()

    return render_template('edit_criteria_instance.html', instance=instance)

@app.route('/criteria_instances/<int:instance_id>/delete', methods=('POST',))
@admin_required
def delete_criteria_instance(instance_id):
    """Verwijder criteria instance."""
    db = get_db()
    instance = db.execute('SELECT * FROM criteria_instances WHERE id = ?', (instance_id,)).fetchone()
    
    if instance is None:
        flash('Criteria instance niet gevonden.', 'danger')
    else:
        try:
            document_type_id = instance['document_type_id']
            db.execute('DELETE FROM criteria_instances WHERE id = ?', (instance_id,))
            db.commit()
            flash('Criteria instance succesvol verwijderd!', 'success')
            return redirect(url_for('list_document_type_criteria', doc_type_id=document_type_id))
        except Exception as e:
            flash(f'Fout bij verwijderen: {e}', 'danger')
            traceback.print_exc()
    
    return redirect(url_for('list_document_types'))

# ================================================================
# Gebruikersbeheer Routes (alleen voor admins)
# ================================================================

@app.route('/users')
@admin_required
def list_users():
    """Overzichtspagina van alle gebruikers."""
    db = get_db()
    users = db.execute('''
        SELECT u.*, o.name AS org_name
        FROM users u
        LEFT JOIN organizations o ON u.organization_id = o.id
        ORDER BY u.role DESC, u.username
    ''').fetchall()
    organizations = db.execute('SELECT id, name FROM organizations ORDER BY name').fetchall()
    return render_template('users.html',
                           users=users,
                           organizations=organizations,
                           show_form=False,
                           edit_user=None,
                           session_user_id=session.get('user_id'))


@app.route('/users/add', methods=['GET', 'POST'])
@admin_required
def add_user():
    """Gebruiker toevoegen."""
    db = get_db()
    organizations = db.execute('SELECT id, name FROM organizations ORDER BY name').fetchall()
    if request.method == 'POST':
        username  = request.form.get('username', '').strip()
        password  = request.form.get('password', '')
        role      = request.form.get('role', 'consumer')
        full_name = request.form.get('full_name', '').strip()
        org_id    = request.form.get('organization_id') or None
        if not username or not password:
            flash('Gebruikersnaam en wachtwoord zijn verplicht.', 'danger')
        else:
            try:
                db.execute(
                    'INSERT INTO users (username, password_hash, role, full_name, organization_id) VALUES (?,?,?,?,?)',
                    (username, generate_password_hash(password), role, full_name or None, org_id)
                )
                db.commit()
                flash(f'Gebruiker "{username}" succesvol aangemaakt.', 'success')
                return redirect(url_for('list_users'))
            except Exception as e:
                flash(f'Fout: {e}', 'danger')
    users = db.execute('''
        SELECT u.*, o.name AS org_name FROM users u
        LEFT JOIN organizations o ON u.organization_id = o.id ORDER BY u.role DESC, u.username
    ''').fetchall()
    return render_template('users.html', users=users, organizations=organizations,
                           show_form=True, edit_user=None,
                           session_user_id=session.get('user_id'))


@app.route('/users/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_user(id):
    """Gebruiker bewerken."""
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (id,)).fetchone()
    if user is None:
        flash('Gebruiker niet gevonden.', 'danger')
        return redirect(url_for('list_users'))
    organizations = db.execute('SELECT id, name FROM organizations ORDER BY name').fetchall()
    if request.method == 'POST':
        username  = request.form.get('username', '').strip()
        password  = request.form.get('password', '')
        role      = request.form.get('role', 'consumer')
        full_name = request.form.get('full_name', '').strip()
        org_id    = request.form.get('organization_id') or None
        if not username:
            flash('Gebruikersnaam is verplicht.', 'danger')
        else:
            try:
                if password:
                    db.execute(
                        'UPDATE users SET username=?, password_hash=?, role=?, full_name=?, organization_id=? WHERE id=?',
                        (username, generate_password_hash(password), role, full_name or None, org_id, id)
                    )
                else:
                    db.execute(
                        'UPDATE users SET username=?, role=?, full_name=?, organization_id=? WHERE id=?',
                        (username, role, full_name or None, org_id, id)
                    )
                db.commit()
                # Sessie bijwerken als de gebruiker zichzelf bewerkt
                if id == session.get('user_id'):
                    session['username']  = username
                    session['user_role'] = role
                flash(f'Gebruiker "{username}" bijgewerkt.', 'success')
                return redirect(url_for('list_users'))
            except Exception as e:
                flash(f'Fout: {e}', 'danger')
    users = db.execute('''
        SELECT u.*, o.name AS org_name FROM users u
        LEFT JOIN organizations o ON u.organization_id = o.id ORDER BY u.role DESC, u.username
    ''').fetchall()
    return render_template('users.html', users=users, organizations=organizations,
                           show_form=True, edit_user=user,
                           session_user_id=session.get('user_id'))


@app.route('/users/delete/<int:id>', methods=['POST'])
@admin_required
def delete_user(id):
    """Gebruiker verwijderen."""
    if id == session.get('user_id'):
        flash('Je kunt je eigen account niet verwijderen.', 'danger')
        return redirect(url_for('list_users'))
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (id,)).fetchone()
    if user is None:
        flash('Gebruiker niet gevonden.', 'danger')
    else:
        try:
            db.execute('DELETE FROM users WHERE id = ?', (id,))
            db.commit()
            flash(f'Gebruiker "{user["username"]}" verwijderd.', 'success')
        except Exception as e:
            flash(f'Fout bij verwijderen: {e}', 'danger')
    return redirect(url_for('list_users'))


# ================================================================
# App Startup
# ================================================================

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)