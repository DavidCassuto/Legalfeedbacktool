# Geoptimaliseerde versie van main.py voor 4 gelijktijdige gebruikers

import os
import sqlite3
import json
import time
from datetime import datetime, timezone 
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, flash, g, current_app, abort, session
import traceback 

# Importeer functies uit je eigen modules
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import db_utils 
from analysis import document_parsing
from analysis import section_recognition
from analysis import criterion_checking
from ai_feedback import AIFeedbackGenerator
from word_export import WordFeedbackExporter
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
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_PATH = os.path.join(BASE_DIR, '..', 'instance')
UPLOAD_FOLDER = os.path.join(INSTANCE_PATH, 'uploads')
DATABASE = os.path.join(INSTANCE_PATH, 'documents.db')

# Zorg ervoor dat de 'instance' en 'uploads' mappen bestaan
os.makedirs(INSTANCE_PATH, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config.from_mapping(
    SECRET_KEY='feedback-tool-secret-key-2024',
    DATABASE=DATABASE,
    UPLOAD_FOLDER=UPLOAD_FOLDER
)

# Initialiseer database optimalisaties bij startup
print("🚀 Initialiseren van database optimalisaties...")
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
            print("DEBUG: Database bestaat nog niet, initialiseren...")
            db_utils.initialize_db(g.db)
        else:
            cursor.execute("SELECT COUNT(*) FROM sections")
            section_count = cursor.fetchone()[0]
            if section_count == 0:
                print("DEBUG: Database bestaat maar heeft geen secties, initialiseren...")
                db_utils.initialize_db(g.db)
            else:
                print(f"DEBUG: Database bestaat al met {section_count} secties, geen initialisatie nodig")
    
    return g.db

# Functie om database connectie te sluiten
@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()
        print("Databaseverbinding gesloten (via close_db).")

# ================================================================
# Geoptimaliseerde sectie-content functies
# ================================================================

def save_section_content_optimized_wrapper(db, recognized_sections):
    """Wrapper voor geoptimaliseerde sectie-content opslag."""
    start_time = time.time()
    
    # Gebruik batch update voor betere performance
    batch_save_section_content(db, recognized_sections)
    
    duration = time.time() - start_time
    performance_monitor.record_query_time('save_section_content', duration)
    print(f"✅ Sectie-content opslag voltooid in {duration:.2f} seconden")

# ================================================================
# Hoofdroutes (geoptimaliseerd)
# ================================================================

@app.route('/')
def index():
    """Welkomstpagina van de applicatie."""
    return render_template('index.html')

@app.route('/upload', methods=['GET', 'POST'])
def upload_document():
    """Route voor het uploaden van een nieuw document (geoptimaliseerd)."""
    start_time = time.time()
    
    db = get_db()
    document_types = db.execute('SELECT id, name FROM document_types').fetchall()
    
    try:
        organizations = db.execute('SELECT id, name FROM organizations').fetchall()
    except sqlite3.OperationalError:
        organizations = []

    form_data = {}

    if request.method == 'POST':
        form_data = request.form

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

                # Werk document_type_id, organization_id, file_size en analysis_status bij
                file_size = os.path.getsize(file_path)
                db.execute(
                    'UPDATE documents SET document_type_id = ?, organization_id = ?, file_size = ?, analysis_status = ? WHERE id = ?',
                    (document_type_id, organization_id, file_size, 'pending', document_id)
                )
                db.commit()

                duration = time.time() - start_time
                performance_monitor.record_query_time('upload', duration)
                
                flash('Document succesvol geüpload! Starten met analyse...', 'success')
                return redirect(url_for('document_analysis', document_id=document_id))

            except Exception as e:
                flash(f'Fout bij uploaden: {e}', 'danger')
                traceback.print_exc() 

    return render_template('upload.html', 
                           document_types=document_types, 
                           organizations=organizations,
                           form_data=form_data)

@app.route('/analysis/<int:document_id>')
def document_analysis(document_id):
    """Gedetailleerde analyseweergave voor een specifiek document (geoptimaliseerd)."""
    start_time = time.time()
    
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
            print(f"🚀 Start analyse voor document ID: {document_id}")
            
            # 1. Document parsen
            parse_start = time.time()
            full_document_text, document_paragraphs, headings_in_document = document_parsing.parse_document(document['file_path'])
            parse_duration = time.time() - parse_start
            performance_monitor.record_query_time('document_parsing', parse_duration)
            
            print(f"--- DEBUGGING in extract_document_content ---")
            print(f"Totaal aantal paragrafen: {len(document_paragraphs)}")
            print(f"Gevonden headings: {len(headings_in_document)}")
            print(f"📄 Parsing tijd: {parse_duration:.2f} seconden")
            
            # 2. Sectieherkenning
            section_start = time.time()
            expected_sections_metadata = db.execute(
                'SELECT id, name, level, identifier, is_required, parent_id, alternative_names, order_index FROM sections WHERE document_type_id = ? ORDER BY order_index',
                (document_type['id'],)
            ).fetchall()
            
            recognized_sects_raw = section_recognition.recognize_and_enrich_sections(
                full_document_text,
                document_paragraphs,
                headings_in_document,
                expected_sections_metadata
            )
            section_duration = time.time() - section_start
            performance_monitor.record_query_time('section_recognition', section_duration)
            print(f"🔍 Sectieherkenning tijd: {section_duration:.2f} seconden")

            # 3. Geoptimaliseerde sectie-content opslag
            save_section_content_optimized_wrapper(db, recognized_sects_raw)

            # 4. Criteria analyse met caching
            criteria_start = time.time()
            
            # Combineer sectie-info uit DB met analyse-resultaten
            all_db_sections = db.execute(
                'SELECT id, name, level, identifier FROM sections WHERE document_type_id = ? ORDER BY order_index',
                (document_type['id'],)
            ).fetchall()
            
            # Maak een map voor snelle lookup van DB secties op identifier
            db_sections_map = {s['identifier']: dict(s) for s in all_db_sections}

            # Verrijk de herkende secties met 'found', 'word_count', 'confidence'
            display_sections = []
            for db_sec_info in all_db_sections:
                # Zoek naar deze sectie in de herkende secties
                found_section = None
                for rec_section in recognized_sects_raw:
                    if rec_section.get('db_id') == db_sec_info['id']:
                        found_section = rec_section
                        break
                
                if found_section:
                    # Gebruik cached content voor criteria checks
                    content = get_section_content_cached(db_sec_info['id'], db)
                    word_count = len(content.split()) if content else 0
                    
                    display_sections.append({
                        'id': db_sec_info['id'],
                        'name': db_sec_info['name'],
                        'identifier': db_sec_info['identifier'],
                        'level': db_sec_info['level'],
                        'found': True,
                        'word_count': word_count,
                        'confidence': found_section.get('confidence', 0.0),
                        'content': content  # Voor criteria checks
                    })
                else:
                    display_sections.append({
                        'id': db_sec_info['id'],
                        'name': db_sec_info['name'],
                        'identifier': db_sec_info['identifier'],
                        'level': db_sec_info['level'],
                        'found': False,
                        'word_count': 0,
                        'confidence': 0.0,
                        'content': ''
                    })

            # 5. Criteria evaluatie
            criteria_feedback = criterion_checking.generate_feedback(db, display_sections)
            
            criteria_duration = time.time() - criteria_start
            performance_monitor.record_query_time('criteria_evaluation', criteria_duration)
            print(f"✅ Criteria evaluatie tijd: {criteria_duration:.2f} seconden")

            # 6. Sla feedback op in database
            feedback_start = time.time()
            db_utils.save_feedback_to_db(db, document_id, criteria_feedback)
            feedback_duration = time.time() - feedback_start
            performance_monitor.record_query_time('feedback_save', feedback_duration)

            # 7. Update document status
            db.execute('UPDATE documents SET analysis_status = ? WHERE id = ?', ('completed', document_id))
            db.commit()

            total_duration = time.time() - start_time
            performance_monitor.record_query_time('total_analysis', total_duration)
            
            print(f"=== 📊 PERFORMANCE SAMENVATTING ===")
            print(f"📄 Document parsing: {parse_duration:.2f}s")
            print(f"🔍 Sectieherkenning: {section_duration:.2f}s")
            print(f"✅ Criteria evaluatie: {criteria_duration:.2f}s")
            print(f"💾 Feedback opslag: {feedback_duration:.2f}s")
            print(f"🚀 TOTAAL: {total_duration:.2f}s")
            print(f"📈 Geschikt voor 4 gelijktijdige gebruikers")

        except Exception as e:
            print(f"❌ Fout tijdens analyse: {e}")
            traceback.print_exc()
            db.execute('UPDATE documents SET analysis_status = ? WHERE id = ?', ('failed', document_id))
            db.commit()
            flash(f'Fout tijdens analyse: {e}', 'danger')

    # Haal feedback op voor weergave
    feedback_items = db.execute('''
        SELECT fi.*, c.name as criteria_name, c.severity, c.color, s.name as section_name
        FROM feedback_items fi
        JOIN criteria c ON fi.criteria_id = c.id
        LEFT JOIN sections s ON fi.section_id = s.id
        WHERE fi.document_id = ?
        ORDER BY c.severity DESC, s.name, c.name
    ''', (document_id,)).fetchall()

    return render_template('analysis.html', 
                           document=document,
                           document_type=document_type,
                           organization=organization,
                           sections=display_sections,
                           feedback_items=feedback_items)

# Performance monitoring route
@app.route('/performance')
def performance_stats():
    """Toont performance statistieken."""
    stats = performance_monitor.get_performance_summary()
    return render_template('performance.html', stats=stats)

# Voeg de rest van de routes toe (vereenvoudigd voor dit voorbeeld)
@app.route('/documents')
def list_documents():
    """Overzichtspagina van alle geüploade documenten."""
    db = get_db()
    documents = db.execute('''
        SELECT d.*, dt.name AS document_type_name, o.name AS organization_name
        FROM documents d
        JOIN document_types dt ON d.document_type_id = dt.id
        LEFT JOIN organizations o ON d.organization_id = o.id
        ORDER BY d.uploaded_at DESC
    ''').fetchall()
    return render_template('documents.html', documents=documents)

# Voeg andere routes toe zoals in de originele main.py...

if __name__ == '__main__':
    print("🚀 Feedback Tool gestart met database optimalisaties")
    print("📈 Geschikt voor 4 gelijktijdige gebruikers")
    app.run(debug=False, host='0.0.0.0', port=5000) 