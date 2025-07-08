import os
import sqlite3
import json
from datetime import datetime, timezone 
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, flash, g, current_app, abort, session
import traceback 

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

# Functie om database connectie te krijgen
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row # Zodat je kolommen via naam kunt benaderen (als een dict)
        
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
# Globale Context Processors
# ================================================================
@app.context_processor
def inject_global_data():
    """Injecteert algemene data in alle templates, zoals het huidige jaar."""
    return {'now': datetime.now()}

# ================================================================
# Hoofdroutes (Welkomst, Upload, Documenten Overzicht, Analyse)
# ================================================================
@app.route('/')
def index():
    """Welkomstpagina van de applicatie."""
    return render_template('index.html') 

@app.route('/upload', methods=['GET', 'POST'])
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


@app.route('/analysis/<int:document_id>')
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
            for heading in headings_in_document[:5]: 
                print(f"  Herkende Heading: Niveau {heading.get('level')}, Tekst: '{heading.get('text')}'")
            print(f"--- Einde DEBUGGING in extract_document_content ---")


            # 2. Sectieherkenning en verrijking (nieuwe structuur)
            expected_sections_metadata = db_utils.get_sections_for_document_type_new(db, document_type['id'])
            
            recognized_sections_raw = section_recognition.recognize_and_enrich_sections(
                full_document_text,
                document_paragraphs,
                headings_in_document,
                expected_sections_metadata
            )
            print(f"--- Start sectieherkenning. Totaal herkende (unieke) secties: {len(recognized_sections_raw)} ---")
            for sec in recognized_sections_raw:
                if sec['found']:
                    print(f"  Herkende Sectie: '{sec['name']}' (ID: {sec['db_id']}), Woorden: {sec['word_count']}, Kopjes: {len(sec['headings'])}")
                else:
                    print(f"  Niet herkende sectie (verplicht: {sec['is_required']}): '{sec['name']}' (ID: {sec['db_id']})")
            print(f"--- Einde sectieherkenning. ---")

            # 3. Criteria ophalen (nieuwe structuur)
            criteria_for_analysis = db_utils.get_criteria_for_document_type_new(db, document_type['id'])

            # 4. Feedback genereren
            generated_feedback_items = criterion_checking.generate_feedback(
                doc_content=full_document_text, 
                recognized_sections=recognized_sections_raw, 
                criteria_list=criteria_for_analysis,
                db_connection=db,
                document_id=document_id,
                document_type_id=document_type['id']
            )

            # 5. AI Feedback genereren (optioneel)
            ai_feedback_data = {}
            try:
                # Check of Gemini API key beschikbaar is
                gemini_api_key = os.getenv('GEMINI_API_KEY')
                if gemini_api_key:
                    print("DEBUG: Gemini API key gevonden, start AI feedback generatie...")
                    ai_generator = AIFeedbackGenerator(api_key=gemini_api_key)
                    
                    # Genereer AI feedback per sectie
                    section_ai_feedback = []
                    for section in recognized_sections_raw:
                        if section.get('found', False) and section.get('content', '').strip():
                            print(f"DEBUG: Genereer AI feedback voor sectie: {section['name']}")
                            ai_feedback = ai_generator.generate_section_feedback(
                                section_name=section['name'],
                                section_content=section['content'],
                                document_type=document_type['name']
                            )
                            section_ai_feedback.append(ai_feedback)
                    
                    # Genereer document-level AI feedback
                    if section_ai_feedback:
                        print("DEBUG: Genereer document-level AI feedback...")
                        document_ai_feedback = ai_generator.generate_document_overview(section_ai_feedback)
                        ai_feedback_data = {
                            'sections': section_ai_feedback,
                            'document': document_ai_feedback
                        }
                        print("DEBUG: AI feedback succesvol gegenereerd")
                    else:
                        print("DEBUG: Geen secties gevonden voor AI feedback")
                else:
                    print("DEBUG: Geen Gemini API key gevonden, sla AI feedback over")
            except Exception as e:
                print(f"DEBUG: Fout bij AI feedback generatie: {e}")
                ai_feedback_data = {}

            # 6. Resultaten opslaan in database
            # Update analysis_status van het document en sla de analysis_data op
            analysis_summary_for_db = {
                'sections': recognized_sections_raw, # De verrijkte secties die zijn herkend
                'feedback_items': [
                    {k: v for k, v in item.items() if k not in ['color', 'criteria_name', 'section_name']} 
                    for item in generated_feedback_items
                ],
                'ai_feedback': ai_feedback_data,  # AI feedback data
                'analysis_date': datetime.now().isoformat()
            }

            db.execute('UPDATE documents SET analysis_status = ?, analysis_data = ? WHERE id = ?', 
                       ('completed', json.dumps(analysis_summary_for_db), document_id))

            db.execute('DELETE FROM feedback_items WHERE document_id = ?', (document_id,))
            
            for feedback_item in generated_feedback_items:
                db_utils.save_feedback_item(db, feedback_item, document_id)
            
            db.commit() 

            flash('Documentanalyse voltooid!', 'success')

        except Exception as e:
            db.execute('UPDATE documents SET analysis_status = ? WHERE id = ?', ('failed', document_id))
            db.commit()
            flash(f"Fout tijdens documentanalyse: {e}", "danger")
            traceback.print_exc() 
            return redirect(url_for('list_documents')) 

    # Data ophalen voor weergave (altijd, of analyse nu net is voltooid of gecached)
    document = db.execute('SELECT * FROM documents WHERE id = ?', (document_id,)).fetchone()
    
    feedback_items_data = db.execute("""
        SELECT
            fi.status,
            fi.message,
            fi.suggestion,
            fi.location,
            fi.confidence,
            c.name AS criterion_name,
            c.color AS color,
            s.name AS section_name
        FROM feedback_items fi
        JOIN criteria c ON fi.criteria_id = c.id
        LEFT JOIN sections s ON fi.section_id = s.id
        WHERE fi.document_id = ?
        ORDER BY fi.generated_at DESC
    """, (document_id,)).fetchall()

    feedback_stats = {
        'violations': sum(1 for f in feedback_items_data if f['status'] == 'error' or f['status'] == 'violation'),
        'warnings': sum(1 for f in feedback_items_data if f['status'] == 'warning'),
        'passed': sum(1 for f in feedback_items_data if f['status'] == 'ok' or f['status'] == 'info'),
        'total': len(feedback_items_data)
    }

    # Haal de sectie data op zoals die in analysis_data is opgeslagen
    display_sections = []
    expected_sections_metadata = db_utils.get_sections_for_document_type_new(db, document_type['id'])

    if document['analysis_status'] == 'completed' and document['analysis_data']:
        analyzed_data_from_db = json.loads(document['analysis_data'])
        analyzed_sections_map = {s['identifier']: s for s in analyzed_data_from_db.get('sections', [])}
        for es_data in expected_sections_metadata:
            display_sections.append(analyzed_sections_map.get(es_data['identifier'], {
                'identifier': es_data['identifier'],
                'name': es_data['name'],
                'level': es_data.get('level', 0), 
                'found': False,
                'word_count': 0,
                'confidence': 0.0,
                'content': '',
                'headings': [],
                'db_id': es_data['id'],
                'is_required': es_data.get('is_required', False)
            }))
    else: 
        for es_data in expected_sections_metadata:
            display_sections.append({
                'identifier': es_data['identifier'],
                'name': es_data['name'],
                'level': es_data.get('level', 0),
                'found': False,
                'word_count': 0,
                'confidence': 0.0,
                'content': '',
                'headings': [],
                'db_id': es_data['id'],
                'is_required': es_data.get('is_required', False)
            })

    return render_template(
        'document_view.html', 
        document=document,
        document_type=document_type,
        organization=organization,
        sections=display_sections, 
        feedback_items=feedback_items_data,
        feedback_stats=feedback_stats
    )


@app.route('/documents/<int:document_id>/export')
def export_document(document_id):
    """Export document met feedback naar Word document."""
    # Haal comment type op uit query parameters
    comment_type = request.args.get('comment_type', 'real')  # Default naar echte comments
    
    db = get_db()
    
    # Haal document en analyse data op
    document = db.execute('SELECT * FROM documents WHERE id = ?', (document_id,)).fetchone()
    if document is None:
        flash('Document niet gevonden.', 'danger')
        return redirect(url_for('list_documents'))
    
    if document['analysis_status'] != 'completed':
        flash('Document analyse nog niet voltooid.', 'danger')
        return redirect(url_for('document_analysis', document_id=document_id))
    
    try:
        # Haal analyse data op
        analysis_data = json.loads(document['analysis_data'])
        
        # Haal feedback items op
        feedback_items = db.execute("""
            SELECT
                fi.status,
                fi.message,
                fi.suggestion,
                fi.location,
                fi.confidence,
                c.name AS criterion_name,
                c.color AS color,
                s.name AS section_name
            FROM feedback_items fi
            JOIN criteria c ON fi.criteria_id = c.id
            LEFT JOIN sections s ON fi.section_id = s.id
            WHERE fi.document_id = ?
            ORDER BY fi.generated_at DESC
        """, (document_id,)).fetchall()
        
        # Converteer feedback items naar dictionaries
        feedback_items_dict = []
        for item in feedback_items:
            feedback_items_dict.append(dict(item))
        
        # Voeg feedback items toe aan analysis data
        analysis_data['feedback_items'] = feedback_items_dict
        
        # Maak export directory
        export_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'exports')
        os.makedirs(export_dir, exist_ok=True)
        
        # Genereer output bestandsnaam met comment type indicator
        base_name = os.path.splitext(document['original_filename'])[0]
        comment_suffix = "_met_comments" if comment_type == 'real' else "_met_feedback"
        output_filename = f"{base_name}{comment_suffix}.docx"
        output_path = os.path.join(export_dir, output_filename)
        
        # Bepaal of echte comments of tekst-based feedback gebruikt moet worden
        use_real_comments = (comment_type == 'real')
        
        # Export naar Word met feedback
        exporter = WordFeedbackExporter()
        exporter.add_feedback_to_document(
            original_file_path=document['file_path'],
            feedback_data=analysis_data,
            output_file_path=output_path,
            use_real_comments=use_real_comments
        )
        
        # Stuur bestand naar gebruiker
        from flask import send_file
        return send_file(
            output_path,
            as_attachment=True,
            download_name=output_filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        
    except Exception as e:
        flash(f'Fout bij export: {e}', 'danger')
        import traceback
        traceback.print_exc()
        return redirect(url_for('document_analysis', document_id=document_id))

@app.route('/documents/<int:document_id>/reanalyze')
def reanalyze_document(document_id):
    """Triggert een nieuwe analyse voor een document."""
    flash(f'Document {document_id} wordt opnieuw geanalyseerd...', 'info')
    return redirect(url_for('document_analysis', document_id=document_id, reanalyze=True))


# ================================================================
# Criteria Management Routes
# ================================================================
@app.route('/criteria')
def list_criteria():
    """Overzicht van alle criteria."""
    db = get_db()
    criteria = db.execute('''
        SELECT c.*, dt.name AS document_type_name
        FROM criteria c
        JOIN document_type_criteria_mappings dtcm ON c.id = dtcm.criteria_id
        JOIN document_types dt ON dtcm.document_type_id = dt.id
        ORDER BY c.name
    ''').fetchall()
    return render_template('criteria_list.html', criteria=criteria)

@app.route('/criteria/add', methods=('GET', 'POST'))
def add_criterion():
    """Formulier om een nieuw criterium toe te voegen."""
    db = get_db()
    document_types = db.execute('SELECT id, name FROM document_types').fetchall()
    try:
        organizations = db.execute('SELECT id, name FROM organizations').fetchall()
    except sqlite3.OperationalError:
        organizations = [] 

    if request.method == 'POST':
        doc_type_id = request.form.get('document_type_id') 
        name = request.form['name']
        description = request.form.get('description')
        rule_type = request.form.get('rule_type')
        application_scope = request.form.get('application_scope')
        severity = request.form.get('severity')
        is_enabled = 1 if request.form.get('is_enabled') == 'on' else 0
        error_message = request.form.get('error_message')
        fixed_feedback_text = request.form.get('fixed_feedback_text')
        frequency_unit = request.form.get('frequency_unit')
        max_mentions_per = request.form.get('max_mentions_per')
        expected_value_min = request.form.get('expected_value_min')
        expected_value_max = request.form.get('expected_value_max')
        color = request.form.get('color')

        doc_type_id = int(doc_type_id) if doc_type_id else None
        max_mentions_per = int(max_mentions_per) if max_mentions_per and max_mentions_per.isdigit() else 0
        expected_value_min = float(expected_value_min) if expected_value_min else None
        expected_value_max = float(expected_value_max) if expected_value_max else None

        if not name or not doc_type_id or not rule_type or not application_scope:
            flash('Naam, documenttype, regeltype en toepassingsgebied zijn verplicht!', 'danger')
        else:
            try:
                cursor = db.cursor()
                cursor.execute(
                    '''INSERT INTO criteria (
                        name, description, rule_type, application_scope, is_enabled, severity,
                        error_message, fixed_feedback_text, frequency_unit, max_mentions_per,
                        expected_value_min, expected_value_max, color
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (name, description, rule_type, application_scope, is_enabled, severity,
                     error_message, fixed_feedback_text, frequency_unit, max_mentions_per,
                     expected_value_min, expected_value_max, color)
                )
                criterion_id = cursor.lastrowid

                db.execute(
                    'INSERT INTO document_type_criteria_mappings (document_type_id, criteria_id) VALUES (?, ?)',
                    (doc_type_id, criterion_id)
                )
                db.commit()
                flash('Criterium succesvol toegevoegd!', 'success')
                return redirect(url_for('list_criteria'))
            except sqlite3.IntegrityError as e:
                flash(f'Fout bij toevoegen: een criterium met deze naam bestaat mogelijk al. {e}', 'danger')
            except Exception as e:
                flash(f'Er is een onverwachte fout opgetreden: {e}', 'danger')
            
    return render_template('add_criterion.html', 
                           document_types=document_types, 
                           organizations=organizations,
                           form_data=request.form)

@app.route('/criteria/edit/<int:id>', methods=('GET', 'POST'))
def edit_criterion(id):
    """Formulier om een bestaand criterium te bewerken."""
    print(f"=== DEBUG: edit_criterion called with ID: {id} ===")
    db = get_db()
    
    # Debug: Check welk criterium we gaan bewerken
    criterion = db.execute('SELECT * FROM criteria WHERE id = ?', (id,)).fetchone()
    if criterion:
        print(f"DEBUG: Found criterion to edit: ID={criterion['id']}, Name='{criterion['name']}'")
    else:
        print(f"DEBUG: Criterion with ID {id} not found!")
        abort(404)

    document_types = db.execute('SELECT id, name FROM document_types').fetchall()
    try:
        organizations = db.execute('SELECT id, name FROM organizations').fetchall()
    except sqlite3.OperationalError:
        organizations = []

    current_doc_type_mapping = db.execute(
        'SELECT document_type_id FROM document_type_criteria_mappings WHERE criteria_id = ?', (id,)
    ).fetchone()
    current_doc_type_id = current_doc_type_mapping['document_type_id'] if current_doc_type_mapping else None
    print(f"DEBUG: Current document type ID: {current_doc_type_id}")

    if request.method == 'POST':
        print("DEBUG: Processing POST request for criterion edit")
        
        # Debug: Log alle form data
        print("DEBUG: Form data received:")
        for key, value in request.form.items():
            print(f"  {key}: {value}")
        
        doc_type_id = request.form.get('document_type_id')
        name = request.form['name']
        description = request.form.get('description')
        rule_type = request.form.get('rule_type')
        application_scope = request.form.get('application_scope')
        severity = request.form.get('severity')
        is_enabled = 1 if request.form.get('is_enabled') == 'on' else 0
        error_message = request.form.get('error_message')
        fixed_feedback_text = request.form.get('fixed_feedback_text')
        frequency_unit = request.form.get('frequency_unit')
        max_mentions_per = request.form.get('max_mentions_per')
        expected_value_min = request.form.get('expected_value_min')
        expected_value_max = request.form.get('expected_value_max')
        color = request.form.get('color')

        doc_type_id = int(doc_type_id) if doc_type_id else None
        max_mentions_per = int(max_mentions_per) if max_mentions_per and max_mentions_per.isdigit() else 0
        expected_value_min = float(expected_value_min) if expected_value_min else None
        expected_value_max = float(expected_value_max) if expected_value_max else None

        print(f"DEBUG: Processed values - doc_type_id: {doc_type_id}, name: '{name}', rule_type: '{rule_type}', application_scope: '{application_scope}'")

        if not name or not doc_type_id or not rule_type or not application_scope:
            print("DEBUG: Validation failed - missing required fields")
            flash('Naam, documenttype, regeltype en toepassingsgebied zijn verplicht!', 'danger')
        else:
            try:
                print("DEBUG: Updating criterion in database...")
                result = db.execute(
                    '''UPDATE criteria SET
                        name = ?, description = ?, rule_type = ?, application_scope = ?,
                        is_enabled = ?, severity = ?, error_message = ?, fixed_feedback_text = ?,
                        frequency_unit = ?, max_mentions_per = ?, expected_value_min = ?,
                        expected_value_max = ?, color = ?
                    WHERE id = ?''',
                    (name, description, rule_type, application_scope,
                     is_enabled, severity, error_message, fixed_feedback_text,
                     frequency_unit, max_mentions_per, expected_value_min,
                     expected_value_max, color, id)
                )
                print(f"DEBUG: UPDATE query affected {result.rowcount} rows")
                
                if doc_type_id != current_doc_type_id:
                    print(f"DEBUG: Updating document type mapping from {current_doc_type_id} to {doc_type_id}")
                    mapping_result = db.execute(
                        'UPDATE document_type_criteria_mappings SET document_type_id = ? WHERE criteria_id = ?',
                        (doc_type_id, id)
                    )
                    print(f"DEBUG: Mapping UPDATE query affected {mapping_result.rowcount} rows")
                
                db.commit()
                print("DEBUG: Database committed successfully")
                flash('Criterium succesvol bijgewerkt!', 'success')
                return redirect(url_for('list_criteria'))
            except sqlite3.IntegrityError as e:
                print(f"DEBUG: SQLite IntegrityError: {e}")
                flash(f'Fout bij bijwerken: een criterium met deze naam bestaat mogelijk al. {e}', 'danger')
            except Exception as e:
                print(f"DEBUG: Unexpected error: {e}")
                flash(f'Er is een onverwachte fout opgetreden: {e}', 'danger')
    else:
        print("DEBUG: Processing GET request for criterion edit")
    
    print("=== DEBUG: edit_criterion completed ===")
    return render_template('edit_criterion.html', 
                           criterion=criterion, 
                           document_types=document_types, 
                           organizations=organizations,
                           current_doc_type_id=current_doc_type_id,
                           form_data=request.form)

@app.route('/criteria/delete/<int:id>', methods=('POST',))
def delete_criterion(id):
    """Verwijder een criterium."""
    db = get_db()
    try:
        db.execute('DELETE FROM document_type_criteria_mappings WHERE criteria_id = ?', (id,))
        db.execute('DELETE FROM criteria_section_mappings WHERE criteria_id = ?', (id,))
        db.execute('DELETE FROM criteria WHERE id = ?', (id,))
        db.commit()
        flash('Criterium succesvol verwijderd!', 'success')
    except sqlite3.Error as e:
        flash(f'Fout bij verwijderen van criterium: {e}', 'danger')
    return redirect(url_for('list_criteria'))


@app.route('/criteria/<int:id>/map_sections', methods=('GET', 'POST'))
def map_criteria_to_sections(id):
    """Beheert de mapping van een criterium aan secties (include/exclude)."""
    db = get_db()
    criterion = db.execute('SELECT * FROM criteria WHERE id = ?', (id,)).fetchone()
    if not criterion:
        flash('Criterium niet gevonden.', 'danger')
        return redirect(url_for('list_criteria'))

    # Haal alle secties op in document volgorde
    all_sections = db.execute('SELECT * FROM sections ORDER BY order_index, name').fetchall()
    
    # Haal huidige mappings op
    current_mappings = db.execute('''
        SELECT csm.*, s.name as section_name 
        FROM criteria_section_mappings csm
        JOIN sections s ON csm.section_id = s.id
        WHERE csm.criteria_id = ?
    ''', (id,)).fetchall()
    
    # Maak dictionary voor snelle lookup
    mapped_sections = {m['section_id']: m for m in current_mappings}

    if request.method == 'POST':
        # Verwijder eerst alle bestaande mappings voor dit criterium
        db.execute('DELETE FROM criteria_section_mappings WHERE criteria_id = ?', (id,))

        # Voeg nieuwe mappings toe op basis van form data
        selected_section_ids = request.form.getlist('selected_sections')
        excluded_section_ids = request.form.getlist('excluded_sections')

        for section_id_str in selected_section_ids:
            section_id = int(section_id_str)
            db.execute(
                'INSERT INTO criteria_section_mappings (criteria_id, section_id, is_excluded) VALUES (?, ?, ?)',
                (id, section_id, 0)
            )
        
        for section_id_str in excluded_section_ids:
            section_id = int(section_id_str)
            db.execute(
                'INSERT INTO criteria_section_mappings (criteria_id, section_id, is_excluded) VALUES (?, ?, ?)',
                (id, section_id, 1)
            )
        
        # Update application_scope van het criterium
        application_scope = request.form.get('application_scope', 'all')
        if application_scope not in ['all', 'document_only', 'specific_sections', 'exclude_sections']:
            application_scope = 'all'
        
        db.execute('UPDATE criteria SET application_scope = ? WHERE id = ?', (application_scope, id))
        db.commit()

        flash(f'Sectie mappings voor criterium "{criterion["name"]}" succesvol bijgewerkt!', 'success')
        return redirect(url_for('list_criteria'))

    return render_template(
        'criteria_section_mapping.html',
        criterion=criterion,
        all_sections=all_sections,
        mapped_sections=mapped_sections
    )


# ================================================================
# Section Management Routes 
# ================================================================
@app.route('/sections')
def list_sections():
    """Overzicht van alle secties."""
    print("=== DEBUG: list_sections called ===")
    db = get_db() # Gebruik db in plaats van conn
    sections = db.execute('''
        SELECT s.* FROM sections s ORDER BY s.order_index, s.name
    ''').fetchall()
    
    print(f"DEBUG: Retrieved {len(sections)} sections from database:")
    for section in sections:
        print(f"  - ID: {section['id']}, Name: '{section['name']}', Identifier: '{section['identifier']}', Order: {section['order_index']}")
    
    print("=== DEBUG: list_sections completed ===")
    return render_template('sections_list.html', sections=sections)

@app.route('/sections/add', methods=('GET', 'POST'))
def add_section():
    """Formulier om een nieuwe sectie toe te voegen."""
    db = get_db() 
    document_types = db.execute('SELECT id, name FROM document_types').fetchall()
    # all_sections niet nodig voor toevoegen van een nieuwe sectie in deze setup
    all_sections = [] 

    if request.method == 'POST':
        name = request.form['name']
        identifier = request.form['identifier']
        is_required = 1 if request.form.get('is_required') == 'on' else 0
        order_index = request.form.get('order_index', type=int)
        level = request.form.get('level', type=int)

        if not name or not identifier:
            flash('Naam en identifier zijn verplicht!', 'danger')
        else:
            try:
                db.execute(
                    'INSERT INTO sections (name, identifier, is_required, order_index, level) VALUES (?, ?, ?, ?, ?)',
                    (name, identifier, is_required, order_index, level)
                )
                db.commit()
                flash('Sectie succesvol toegevoegd!', 'success')
                return redirect(url_for('list_sections'))
            except sqlite3.IntegrityError:
                flash('Fout bij toevoegen: een sectie met deze identifier bestaat al.', 'danger')
            except Exception as e:
                flash(f'Er is een onverwachte fout opgetreden: {e}', 'danger')
    
    return render_template('add_section.html', 
                           document_types=document_types, 
                           all_sections=all_sections, # Dit kan leeg blijven of verwijderd worden uit template
                           form_data=request.form)

@app.route('/sections/edit/<int:id>', methods=('GET', 'POST'))
def edit_section(id):
    """Formulier om een bestaande sectie te bewerken."""
    db = get_db() 
    section = db.execute('SELECT * FROM sections WHERE id = ?', (id,)).fetchone()
    if section is None:
        abort(404)

    document_types = db.execute('SELECT id, name FROM document_types').fetchall()
    all_sections = [] 

    if request.method == 'POST':
        name = request.form['name']
        identifier = request.form['identifier']
        is_required = 1 if request.form.get('is_required') == 'on' else 0
        order_index = request.form.get('order_index', type=int)
        level = request.form.get('level', type=int)

        if not name or not identifier:
            flash('Naam en identifier zijn verplicht!', 'danger')
        else:
            try:
                db.execute(
                    'UPDATE sections SET name = ?, identifier = ?, is_required = ?, order_index = ?, level = ? WHERE id = ?',
                    (name, identifier, is_required, order_index, level, id)
                )
                db.commit()
                flash('Sectie succesvol bijgewerkt!', 'success')
                return redirect(url_for('list_sections'))
            except sqlite3.IntegrityError:
                flash('Fout bij bijwerken: een sectie met deze identifier bestaat al.', 'danger')
            except Exception as e:
                flash(f'Er is een onverwachte fout opgetreden: {e}', 'danger')
    
    return render_template('edit_section.html', 
                           section=section, 
                           document_types=document_types, 
                           all_sections=all_sections, # Dit kan leeg blijven of verwijderd worden uit template
                           form_data=request.form)

@app.route('/sections/delete/<int:id>', methods=('POST',))
def delete_section(id):
    """Verwijder een sectie."""
    print(f"=== DEBUG: Delete section called with ID: {id} ===")
    db = get_db() 
    
    # Debug: Check welke sectie we gaan verwijderen
    section_info = db.execute('SELECT id, name, identifier FROM sections WHERE id = ?', (id,)).fetchone()
    if section_info:
        print(f"DEBUG: Found section to delete: ID={section_info['id']}, Name='{section_info['name']}', Identifier='{section_info['identifier']}'")
    else:
        print(f"DEBUG: Section with ID {id} not found!")
        flash(f'Sectie met ID {id} niet gevonden!', 'danger')
        return redirect(url_for('list_sections'))
    
    try:
        feedback_count = db.execute('SELECT COUNT(*) FROM feedback_items WHERE section_id = ?', (id,)).fetchone()[0]
        criteria_mapping_count = db.execute('SELECT COUNT(*) FROM criteria_section_mappings WHERE section_id = ?', (id,)).fetchone()[0]
        
        print(f"DEBUG: Dependencies - feedback_count: {feedback_count}, criteria_mapping_count: {criteria_mapping_count}")

        if feedback_count > 0 or criteria_mapping_count > 0:
            print(f"DEBUG: Cannot delete - dependencies found")
            flash(f'Kan sectie niet verwijderen: {feedback_count} feedback items en {criteria_mapping_count} criterium mappings gekoppeld. Verwijder eerst de gekoppelde items.', 'danger')
        else:
            print(f"DEBUG: Deleting section from database...")
            result = db.execute('DELETE FROM sections WHERE id = ?', (id,))
            print(f"DEBUG: DELETE query affected {result.rowcount} rows")
            db.commit()
            print(f"DEBUG: Database committed successfully")
            
            # Verify deletion
            check_section = db.execute('SELECT id FROM sections WHERE id = ?', (id,)).fetchone()
            if check_section:
                print(f"DEBUG: ERROR - Section still exists after deletion!")
                flash('Fout: Sectie bestaat nog steeds na verwijdering!', 'danger')
            else:
                print(f"DEBUG: SUCCESS - Section successfully deleted")
                flash('Sectie succesvol verwijderd!', 'success')
    except sqlite3.Error as e:
        print(f"DEBUG: SQLite error: {e}")
        flash(f'Fout bij verwijderen van sectie: {e}', 'danger')
    except Exception as e:
        print(f"DEBUG: Unexpected error: {e}")
        flash(f'Onverwachte fout bij verwijderen van sectie: {e}', 'danger')
    
    print(f"=== DEBUG: Delete section function completed ===")
    return redirect(url_for('list_sections'))

# ================================================================
# Document Type Management Routes 
# ================================================================
@app.route('/document_types')
def list_document_types():
    """Overzicht van alle documenttypes."""
    db = get_db()
    document_types = db.execute('SELECT * FROM document_types ORDER BY name').fetchall()
    return render_template('document_types_list.html', document_types=document_types)

@app.route('/document_types/add', methods=('GET', 'POST'))
def add_document_type():
    """Formulier om een nieuw documenttype toe te voegen."""
    db = get_db()
    try:
        organizations = db.execute('SELECT id, name FROM organizations').fetchall()
    except sqlite3.OperationalError:
        organizations = [] 

    if request.method == 'POST':
        name = request.form['name']
        identifier = request.form['identifier']

        if not name or not identifier:
            flash('Naam en identifier zijn verplicht!', 'danger')
        else:
            try:
                db.execute('INSERT INTO document_types (name, identifier) VALUES (?, ?)', (name, identifier))
                db.commit()
                flash('Documenttype succesvol toegevoegd!', 'success')
                return redirect(url_for('list_document_types'))
            except sqlite3.IntegrityError:
                flash('Een documenttype met deze naam of identifier bestaat al.', 'danger')
            except Exception as e:
                flash(f'Er is een onverwachte fout opgetreden: {e}', 'danger')
    
    return render_template('add_document_type.html', organizations=organizations, form_data=request.form)

@app.route('/document_types/edit/<int:id>', methods=('GET', 'POST'))
def edit_document_type(id):
    """Formulier om een bestaand documenttype te bewerken."""
    db = get_db()
    doc_type = db.execute('SELECT * FROM document_types WHERE id = ?', (id,)).fetchone()
    if doc_type is None:
        abort(404)

    try:
        organizations = db.execute('SELECT id, name FROM organizations').fetchall()
    except sqlite3.OperationalError:
        organizations = [] 

    if request.method == 'POST':
        name = request.form['name']
        identifier = request.form['identifier']

        if not name or not identifier:
            flash('Naam en identifier zijn verplicht!', 'danger')
        else:
            try:
                db.execute('UPDATE document_types SET name = ?, identifier = ? WHERE id = ?', (name, identifier, id))
                db.commit()
                flash('Documenttype succesvol bijgewerkt!', 'success')
                return redirect(url_for('list_document_types'))
            except sqlite3.IntegrityError:
                flash('Een documenttype met deze naam of identifier bestaat al.', 'danger')
            except Exception as e:
                flash(f'Er is een onverwachte fout opgetreden: {e}', 'danger')
    
    return render_template('edit_document_type.html', doc_type=doc_type, organizations=organizations, form_data=request.form)

@app.route('/document_types/delete/<int:id>', methods=('POST',))
def delete_document_type(id):
    """Verwijder een documenttype."""
    db = get_db()
    try:
        # Check op afhankelijke records (als organization_id een FK is in document_types)
        # In de huidige db_utils is organization_id GEEN FK in document_types
        # Secties zijn ook niet direct gekoppeld aan document_types via een mappingtabel in de huidige db_utils
        # Dus we controleren alleen documents en criteria mappings

        documents_count = db.execute('SELECT COUNT(*) FROM documents WHERE document_type_id = ?', (id,)).fetchone()[0]
        criteria_mapping_count = db.execute('SELECT COUNT(*) FROM document_type_criteria_mappings WHERE document_type_id = ?', (id,)).fetchone()[0]
        
        if documents_count > 0 or criteria_mapping_count > 0:
            flash(f'Kan documenttype niet verwijderen: {documents_count} gekoppelde documenten en {criteria_mapping_count} criteria gevonden. Verwijder eerst de gekoppelde items.', 'danger')
        else:
            db.execute('DELETE FROM document_types WHERE id = ?', (id,))
            db.commit()
            flash('Documenttype succesvol verwijderd!', 'success')
    except sqlite3.Error as e:
        flash(f'Fout bij verwijderen van documenttype: {e}', 'danger')
    return redirect(url_for('list_document_types'))

# ================================================================
# Organisatie Management Routes 
# ================================================================
@app.route('/organizations')
def list_organizations():
    """Overzicht van alle organisaties."""
    db = get_db()
    try:
        organizations = db.execute('SELECT * FROM organizations ORDER BY name').fetchall()
    except sqlite3.OperationalError:
        organizations = [] 
        flash('De "organizations" tabel bestaat niet in de database. Deze route zal niet functioneren.', 'info')
    return render_template('organizations_list.html', organizations=organizations)

@app.route('/organizations/add', methods=('GET', 'POST'))
def add_organization():
    """Formulier om een nieuwe organisatie toe te voegen."""
    db = get_db()
    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description')

        if not name:
            flash('Naam van organisatie is verplicht!', 'danger')
        else:
            try:
                db.execute('INSERT INTO organizations (name, description) VALUES (?, ?)', (name, description))
                db.commit()
                flash('Organisatie succesvol toegevoegd!', 'success')
                return redirect(url_for('list_organizations'))
            except sqlite3.IntegrityError:
                flash('Een organisatie met deze naam bestaat al.', 'danger')
            except Exception as e:
                flash(f'Er is een onverwachte fout opgetreden: {e}', 'danger')
    
    return render_template('add_organization.html', form_data=request.form)

@app.route('/organizations/edit/<int:id>', methods=('GET', 'POST'))
def edit_organization(id):
    """Formulier om een bestaande organisatie te bewerken."""
    db = get_db()
    try:
        organization = db.execute('SELECT * FROM organizations WHERE id = ?', (id,)).fetchone()
    except sqlite3.OperationalError:
        flash('De "organizations" tabel bestaat niet.', 'danger')
        return redirect(url_for('list_organizations'))

    if organization is None:
        abort(404)

    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description')

        if not name:
            flash('Naam van organisatie is verplicht!', 'danger')
        else:
            try:
                db.execute('UPDATE organizations SET name = ?, description = ? WHERE id = ?', (name, description, id))
                db.commit()
                flash('Organisatie succesvol bijgewerkt!', 'success')
                return redirect(url_for('list_organizations'))
            except sqlite3.IntegrityError:
                flash('Een organisatie met deze naam bestaat al.', 'danger')
            except Exception as e:
                flash(f'Er is een onverwachte fout opgetreden: {e}', 'danger')
    
    return render_template('edit_organization.html', organization=organization, form_data=request.form)

@app.route('/organizations/delete/<int:id>', methods=('POST',))
def delete_organization(id):
    """Verwijder een organisatie."""
    db = get_db()
    try:
        # Check op afhankelijke records (documents)
        documents_count = db.execute('SELECT COUNT(*) FROM documents WHERE organization_id = ?', (id,)).fetchone()[0]
        
        if documents_count > 0:
            flash(f'Kan organisatie niet verwijderen: {documents_count} gekoppelde documenten gevonden. Verwijder eerst de gekoppelde items.', 'danger')
        else:
            db.execute('DELETE FROM organizations WHERE id = ?', (id,))
            db.commit()
            flash('Organisatie succesvol verwijderd!', 'success')
    except sqlite3.OperationalError:
        flash('De "organizations" tabel bestaat niet.', 'danger')
    except sqlite3.Error as e:
        flash(f'Fout bij verwijderen van organisatie: {e}', 'danger')
    return redirect(url_for('list_organizations'))

# ================================================================
# Nieuwe Document Type Management Routes (per organisatie)
# ================================================================

@app.route('/document_types/organization/<int:org_id>')
def list_organization_document_types(org_id):
    """Overzicht van document types voor een specifieke organisatie."""
    db = get_db()
    
    # Haal organisatie op
    organization = db.execute('SELECT * FROM organizations WHERE id = ?', (org_id,)).fetchone()
    if not organization:
        flash('Organisatie niet gevonden.', 'danger')
        return redirect(url_for('list_organizations'))
    
    # Haal document types op voor deze organisatie
    document_types = db.execute('''
        SELECT dt.*, COUNT(d.id) as document_count
        FROM document_types dt
        LEFT JOIN documents d ON dt.id = d.document_type_id
        WHERE dt.organization_id = ? OR dt.organization_id IS NULL
        GROUP BY dt.id
        ORDER BY dt.name
    ''', (org_id,)).fetchall()
    
    return render_template('organization_document_types.html', 
                         organization=organization, 
                         document_types=document_types)

@app.route('/document_types/organization/<int:org_id>/add', methods=('GET', 'POST'))
def add_organization_document_type(org_id):
    """Voeg een nieuw document type toe voor een organisatie."""
    db = get_db()
    
    # Haal organisatie op
    organization = db.execute('SELECT * FROM organizations WHERE id = ?', (org_id,)).fetchone()
    if not organization:
        flash('Organisatie niet gevonden.', 'danger')
        return redirect(url_for('list_organizations'))
    
    if request.method == 'POST':
        name = request.form['name']
        identifier = request.form.get('identifier', '').lower().replace(' ', '_')
        description = request.form.get('description', '')
        
        if not name:
            flash('Naam is verplicht!', 'danger')
        else:
            try:
                cursor = db.cursor()
                cursor.execute(
                    'INSERT INTO document_types (name, identifier, description, organization_id) VALUES (?, ?, ?, ?)',
                    (name, identifier, description, org_id)
                )
                document_type_id = cursor.lastrowid
                db.commit()
                
                flash('Document type succesvol toegevoegd!', 'success')
                return redirect(url_for('manage_document_type_sections', 
                                      org_id=org_id, 
                                      doc_type_id=document_type_id))
            except sqlite3.IntegrityError:
                flash('Een document type met deze naam bestaat al.', 'danger')
            except Exception as e:
                flash(f'Fout bij toevoegen: {e}', 'danger')
    
    return render_template('add_organization_document_type.html', organization=organization)

@app.route('/document_types/<int:doc_type_id>/sections/manage')
def manage_document_type_sections(doc_type_id):
    """Beheer secties voor een document type."""
    db = get_db()
    
    # Haal document type op
    document_type = db.execute('SELECT * FROM document_types WHERE id = ?', (doc_type_id,)).fetchone()
    if not document_type:
        flash('Document type niet gevonden.', 'danger')
        return redirect(url_for('list_document_types'))
    
    # Haal organisatie op
    organization = db.execute('SELECT * FROM organizations WHERE id = ?', (document_type['organization_id'],)).fetchone()
    
    # Haal gekoppelde secties op
    sections = db.execute('''
        SELECT s.*, dts.is_required, dts.order_index
        FROM sections s
        JOIN document_type_sections dts ON s.id = dts.section_id
        WHERE dts.document_type_id = ?
        ORDER BY dts.order_index
    ''', (doc_type_id,)).fetchall()
    
    # Haal beschikbare secties op (nog niet gekoppeld)
    available_sections = db.execute('''
        SELECT s.* FROM sections s
        WHERE s.id NOT IN (
            SELECT section_id FROM document_type_sections WHERE document_type_id = ?
        )
        ORDER BY s.name
    ''', (doc_type_id,)).fetchall()
    
    return render_template('manage_document_type_sections.html',
                         document_type=document_type,
                         organization=organization,
                         sections=sections,
                         available_sections=available_sections)

@app.route('/document_types/<int:doc_type_id>/sections/add', methods=('POST',))
def add_section_to_document_type(doc_type_id):
    """Voeg een sectie toe aan een document type."""
    db = get_db()
    
    section_id = request.form.get('section_id')
    is_required = 1 if request.form.get('is_required') == 'on' else 0
    order_index = request.form.get('order_index', 0)
    
    if not section_id:
        flash('Sectie is verplicht!', 'danger')
    else:
        try:
            db.execute('''
                INSERT INTO document_type_sections (document_type_id, section_id, is_required, order_index)
                VALUES (?, ?, ?, ?)
            ''', (doc_type_id, section_id, is_required, order_index))
            db.commit()
            flash('Sectie succesvol toegevoegd aan document type!', 'success')
        except sqlite3.IntegrityError:
            flash('Deze sectie is al gekoppeld aan dit document type.', 'danger')
        except Exception as e:
            flash(f'Fout bij toevoegen: {e}', 'danger')
    
    return redirect(url_for('manage_document_type_sections', doc_type_id=doc_type_id))

@app.route('/document_types/<int:doc_type_id>/sections/<int:section_id>/remove', methods=('POST',))
def remove_section_from_document_type(doc_type_id, section_id):
    """Verwijder een sectie van een document type."""
    db = get_db()
    
    try:
        db.execute('''
            DELETE FROM document_type_sections 
            WHERE document_type_id = ? AND section_id = ?
        ''', (doc_type_id, section_id))
        db.commit()
        flash('Sectie succesvol verwijderd van document type!', 'success')
    except Exception as e:
        flash(f'Fout bij verwijderen: {e}', 'danger')
    
    return redirect(url_for('manage_document_type_sections', doc_type_id=doc_type_id))

# ================================================================
# Nieuwe Criteria Management Routes
# ================================================================

@app.route('/criteria_templates')
def list_criteria_templates():
    """Overzicht van beschikbare criteria templates."""
    db = get_db()
    
    templates = db.execute('''
        SELECT ct.*, COUNT(ci.id) as usage_count
        FROM criteria_templates ct
        LEFT JOIN criteria_instances ci ON ct.id = ci.template_id
        GROUP BY ct.id
        ORDER BY ct.name
    ''').fetchall()
    
    return render_template('criteria_templates.html', templates=templates)

@app.route('/criteria_templates/add', methods=('GET', 'POST'))
def add_criteria_template():
    """Voeg een nieuw criteria template toe."""
    db = get_db()
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description', '')
        rule_type = request.form.get('rule_type')
        application_scope = request.form.get('application_scope')
        severity = request.form.get('severity')
        error_message = request.form.get('error_message', '')
        fixed_feedback_text = request.form.get('fixed_feedback_text', '')
        color = request.form.get('color', '#F94144')
        is_global = 1 if request.form.get('is_global') == 'on' else 0
        
        if not name or not rule_type or not application_scope:
            flash('Naam, regeltype en toepassingsgebied zijn verplicht!', 'danger')
        else:
            try:
                db.execute('''
                    INSERT INTO criteria_templates (
                        name, description, rule_type, application_scope, severity,
                        error_message, fixed_feedback_text, color, is_global
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (name, description, rule_type, application_scope, severity,
                     error_message, fixed_feedback_text, color, is_global))
                db.commit()
                flash('Criteria template succesvol toegevoegd!', 'success')
                return redirect(url_for('list_criteria_templates'))
            except sqlite3.IntegrityError:
                flash('Een template met deze naam bestaat al.', 'danger')
            except Exception as e:
                flash(f'Fout bij toevoegen: {e}', 'danger')
    
    return render_template('add_criteria_template.html')

@app.route('/document_types/<int:doc_type_id>/criteria')
def list_document_type_criteria(doc_type_id):
    """Overzicht van criteria voor een document type."""
    db = get_db()
    
    # Haal document type op
    document_type = db.execute('SELECT * FROM document_types WHERE id = ?', (doc_type_id,)).fetchone()
    if not document_type:
        flash('Document type niet gevonden.', 'danger')
        return redirect(url_for('list_document_types'))
    
    # Haal organisatie op
    organization = db.execute('SELECT * FROM organizations WHERE id = ?', (document_type['organization_id'],)).fetchone()
    
    # Haal criteria instances op
    criteria_instances = db.execute('''
        SELECT ci.*, ct.name as template_name, ct.description as template_description
        FROM criteria_instances ci
        LEFT JOIN criteria_templates ct ON ci.template_id = ct.id
        WHERE ci.document_type_id = ?
        ORDER BY ci.name
    ''', (doc_type_id,)).fetchall()
    
    # Haal beschikbare templates op
    available_templates = db.execute('''
        SELECT * FROM criteria_templates 
        WHERE is_global = 1 OR organization_id = ?
        ORDER BY name
    ''', (document_type['organization_id'],)).fetchall()
    
    return render_template('document_type_criteria.html',
                         document_type=document_type,
                         organization=organization,
                         criteria_instances=criteria_instances,
                         available_templates=available_templates)

@app.route('/document_types/<int:doc_type_id>/criteria/add', methods=('GET', 'POST'))
def add_criteria_to_document_type(doc_type_id):
    """Voeg criteria toe aan een document type."""
    db = get_db()
    
    # Haal document type op
    document_type = db.execute('SELECT * FROM document_types WHERE id = ?', (doc_type_id,)).fetchone()
    if not document_type:
        flash('Document type niet gevonden.', 'danger')
        return redirect(url_for('list_document_types'))
    
    # Haal beschikbare templates op
    available_templates = db.execute('''
        SELECT * FROM criteria_templates 
        WHERE is_global = 1 OR organization_id = ?
        ORDER BY name
    ''', (document_type['organization_id'],)).fetchall()
    
    if request.method == 'POST':
        template_id = request.form.get('template_id')
        name = request.form['name']
        description = request.form.get('description', '')
        rule_type = request.form.get('rule_type')
        application_scope = request.form.get('application_scope')
        severity = request.form.get('severity')
        error_message = request.form.get('error_message', '')
        fixed_feedback_text = request.form.get('fixed_feedback_text', '')
        color = request.form.get('color', '#F94144')
        
        if not name or not rule_type or not application_scope:
            flash('Naam, regeltype en toepassingsgebied zijn verplicht!', 'danger')
        else:
            try:
                cursor = db.cursor()
                cursor.execute('''
                    INSERT INTO criteria_instances (
                        template_id, document_type_id, organization_id, name, description,
                        rule_type, application_scope, severity, error_message, 
                        fixed_feedback_text, color
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (template_id, doc_type_id, document_type['organization_id'], name, description,
                     rule_type, application_scope, severity, error_message, fixed_feedback_text, color))
                
                criteria_instance_id = cursor.lastrowid
                db.commit()
                
                flash('Criteria succesvol toegevoegd!', 'success')
                return redirect(url_for('list_document_type_criteria', doc_type_id=doc_type_id))
            except Exception as e:
                flash(f'Fout bij toevoegen: {e}', 'danger')
    
    return render_template('add_criteria_to_document_type.html',
                         document_type=document_type,
                         available_templates=available_templates)

@app.route('/criteria_instances/<int:instance_id>/edit', methods=('GET', 'POST'))
def edit_criteria_instance(instance_id):
    """Bewerk een criteria instance."""
    db = get_db()
    
    # Haal criteria instance op
    instance = db.execute('SELECT * FROM criteria_instances WHERE id = ?', (instance_id,)).fetchone()
    if not instance:
        flash('Criteria instance niet gevonden.', 'danger')
        return redirect(url_for('list_document_types'))
    
    # Haal document type op
    document_type = db.execute('SELECT * FROM document_types WHERE id = ?', (instance['document_type_id'],)).fetchone()
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description', '')
        severity = request.form.get('severity')
        error_message = request.form.get('error_message', '')
        fixed_feedback_text = request.form.get('fixed_feedback_text', '')
        color = request.form.get('color', '#F94144')
        is_enabled = 1 if request.form.get('is_enabled') == 'on' else 0
        
        if not name:
            flash('Naam is verplicht!', 'danger')
        else:
            try:
                db.execute('''
                    UPDATE criteria_instances 
                    SET name = ?, description = ?, severity = ?, error_message = ?,
                        fixed_feedback_text = ?, color = ?, is_enabled = ?
                    WHERE id = ?
                ''', (name, description, severity, error_message, fixed_feedback_text, color, is_enabled, instance_id))
                db.commit()
                flash('Criteria succesvol bijgewerkt!', 'success')
                return redirect(url_for('list_document_type_criteria', doc_type_id=instance['document_type_id']))
            except Exception as e:
                flash(f'Fout bij bijwerken: {e}', 'danger')
    
    return render_template('edit_criteria_instance.html', instance=instance, document_type=document_type)

@app.route('/criteria_instances/<int:instance_id>/delete', methods=('POST',))
def delete_criteria_instance(instance_id):
    """Verwijder een criteria instance."""
    db = get_db()
    
    # Haal criteria instance op
    instance = db.execute('SELECT * FROM criteria_instances WHERE id = ?', (instance_id,)).fetchone()
    if not instance:
        flash('Criteria instance niet gevonden.', 'danger')
        return redirect(url_for('list_document_types'))
    
    try:
        db.execute('DELETE FROM criteria_instances WHERE id = ?', (instance_id,))
        db.commit()
        flash('Criteria succesvol verwijderd!', 'success')
    except Exception as e:
        flash(f'Fout bij verwijderen: {e}', 'danger')
    
    return redirect(url_for('list_document_type_criteria', doc_type_id=instance['document_type_id']))

# ================================================================
# Hoofduitvoerder voor de applicatie
# ================================================================
if __name__ == '__main__':
    print("Attempting to run Feedback Tool Flask App...")
    app.run(debug=True)