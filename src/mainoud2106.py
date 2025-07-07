# C:\ProjectFT\src\main.py

import os
import sqlite3
import json
from datetime import datetime # Gebruik deze import, zoals eerder besproken
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, flash, g, current_app, abort, session

# Importeer functies uit je eigen modules
from .db_utils import get_db, init_app # init_app registreert close_db en init_db_command
from src.analysis import document_parsing
from src.analysis import section_recognition
from src.analysis import criterion_checking

# ================================================================
# Flask App Configuratie
# ================================================================
app = Flask(__name__, instance_relative_config=True)

# Defineer de paden
BASE_DIR = os.path.abspath(os.path.dirname(__file__)) # src directory
INSTANCE_PATH = os.path.join(BASE_DIR, '..', 'instance') # parent directory van src, dan 'instance'
UPLOAD_FOLDER = os.path.join(INSTANCE_PATH, 'uploads')
DATABASE = os.path.join(INSTANCE_PATH, 'documents.db')

# Zorg ervoor dat de 'instance' en 'uploads' mappen bestaan
os.makedirs(INSTANCE_PATH, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config.from_mapping(
    SECRET_KEY='feedback-tool-secret-key-2024', # JOUW SECRET KEY (vervang dit in een productieomgeving!)
    DATABASE=DATABASE,
    UPLOAD_FOLDER=UPLOAD_FOLDER
)

# Initialiseer de app met databasefuncties
init_app(app)

# ================================================================
# Globale Context Processors
# ================================================================
@app.context_processor
def inject_global_data():
    """Injecteert algemene data in alle templates, zoals het huidige jaar."""
    return {'now': datetime.now(datetime.UTC)} # Gebruik timezone-aware UTC datetime


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
    organizations = db.execute('SELECT id, name FROM organizations').fetchall()

    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Geen bestand geselecteerd!', 'danger')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('Geen bestand geselecteerd!', 'danger')
            return redirect(request.url)
        if file:
            original_filename = file.filename
            filename = secure_filename(original_filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            file_size = os.path.getsize(file_path)
            document_type_id = request.form.get('document_type')
            organization_id = request.form.get('organization')

            if not document_type_id:
                flash('Selecteer een documenttype!', 'danger')
                return redirect(request.url)

            # Sla document op in DB met status 'pending'
            cursor = db.cursor()
            cursor.execute(
                'INSERT INTO documents (filename, original_filename, file_path, file_size, document_type_id, organization_id, analysis_status) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (filename, original_filename, file_path, file_size, document_type_id, organization_id, 'pending')
            )
            document_id = cursor.lastrowid
            db.commit()

            flash('Document succesvol geüpload! Starten met analyse...', 'success')
            # Direct doorsturen naar analyse pagina
            return redirect(url_for('document_analysis', document_id=document_id))
    
    return render_template('upload.html', document_types=document_types, organizations=organizations)

@app.route('/documents')
def list_documents():
    """Overzichtspagina van alle geüploade documenten."""
    db = get_db()
    documents = db.execute('''
        SELECT d.*, dt.name AS document_type_name, o.name AS organization_name
        FROM documents d
        JOIN document_types dt ON d.document_type_id = dt.id
        LEFT JOIN organizations o ON d.organization_id = o.id
        ORDER BY d.upload_time DESC
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
    if organization is None:
        flash('Organisatie niet gevonden voor dit document.', 'danger')
        return redirect(url_for('list_documents'))

    # Start analyse als de status pending is of geforceerd opnieuw analyseren
    if document['analysis_status'] == 'pending' or request.args.get('reanalyze'):
        try:
            # 1. Document parsen (uit .docx halen van tekst)
            doc_content = document_parsing.extract_document_content(document['file_path'])
            
            # 2. Sectieherkenning
            recognized_sects_raw = section_recognition.recognize_sections(
                doc_content,
                document_type['id'],
                db # Geef de db-verbinding door
            )

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
                recognized_sec = next((s for s in recognized_sects_raw if s.get('db_id') == db_sec_info['id']), None)
                
                section_data = {
                    'id': db_sec_info['id'], # DB ID van de sectie
                    'name': db_sec_info['name'],
                    'level': db_sec_info['level'],
                    'found': True if recognized_sec and recognized_sec.get('content_snippet') else False,
                    'word_count': recognized_sec.get('word_count', 0) if recognized_sec else 0,
                    'confidence': recognized_sec.get('confidence', None) if recognized_sec else None,
                    'content': recognized_sec.get('content', '') if recognized_sec else '', # Sla content op voor latere weergave
                    'identifier': db_sec_info['identifier'] # Nodig voor JS `showSectionContent`
                }
                display_sections.append(section_data)

            # 3. Criteria ophalen en feedback genereren
            criteria_for_analysis = db_utils.get_criteria_for_document_type(db, document_type['id'], organization['id'])
            
            # Voer de feedback generatie uit (simulatie of echte LLM-call)
            generated_feedback_items = criterion_checking.generate_feedback(
                doc_content,
                recognized_sects_raw, # Geef de ruwe herkende secties mee
                criteria_for_analysis,
                db, # Geef de db-verbinding door voor eventuele extra lookups
                document_id,
                document_type['id']
            )

            # 4. Sla geanalyseerde data op in het document (optioneel, voor caching)
            # Voor een meer robuuste opslag: sla de sectie-data en feedback apart op
            # Hier slaan we een samenvatting op in de analysis_data kolom van het document
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
                'feedback_items': [
                    {
                        'criteria_id': fi.get('criteria_id'),
                        'section_id': fi.get('section_id'),
                        'status': fi.get('status'),
                        'message': fi.get('message'),
                        'suggestion': fi.get('suggestion'),
                        'location': fi.get('location'),
                        'confidence': fi.get('confidence')
                    } for fi in generated_feedback_items
                ]
            }

            db.execute(
                'UPDATE documents SET analysis_status = ?, analysis_data = ? WHERE id = ?',
                ('completed', json.dumps(analysis_summary), document_id)
            )
            db.commit()

            # Verwijder oude feedback items als er opnieuw geanalyseerd wordt
            db.execute('DELETE FROM feedback_items WHERE document_id = ?', (document_id,))
            
            # Sla de nieuwe feedback items op in de feedback_items tabel
            cursor = db.cursor()
            for feedback_item in generated_feedback_items:
                cursor.execute("""
                    INSERT INTO feedback_items (
                        document_id, criteria_id, section_id, status, message, suggestion,
                        location, confidence, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    document_id,
                    feedback_item.get('criteria_id'),
                    feedback_item.get('section_id'),
                    feedback_item.get('status'),
                    feedback_item.get('message'),
                    feedback_item.get('suggestion'),
                    feedback_item.get('location'),
                    feedback_item.get('confidence'),
                    datetime.now() # Of een timestamp uit de feedback_item zelf als je die daar genereert
                ))
            db.commit()
            
            flash('Documentanalyse voltooid!', 'success')

        except Exception as e:
            db.execute('UPDATE documents SET analysis_status = ? WHERE id = ?', ('failed', document_id))
            db.commit()
            flash(f"Fout tijdens documentanalyse: {e}", "danger")
            # Log de volledige traceback in de console voor debugging
            import traceback
            traceback.print_exc() 
            return redirect(url_for('list_documents'))

    # Data ophalen voor weergave (nu uit de DB, die is net gevuld of was al gevuld)
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
        ORDER BY fi.created_at DESC
    """, (document_id,)).fetchall()

    feedback_stats = {
        'violations': sum(1 for f in feedback_items_data if f['status'] == 'error' or f['status'] == 'violation'),
        'warnings': sum(1 for f in feedback_items_data if f['status'] == 'warning'),
        'passed': sum(1 for f in feedback_items_data if f['status'] == 'ok' or f['status'] == 'info'),
        'total': len(feedback_items_data)
    }

    # Haal secties op om te tonen in de 'Gevonden Secties' tabel
    display_sections = []
    all_db_sections = db.execute(
        'SELECT id, name, level, identifier, is_required FROM sections WHERE document_type_id = ? ORDER BY order_index',
        (document_type['id'],)
    ).fetchall()

    # Gebruik de analysis_data uit het document om 'found', 'word_count', 'confidence' te bepalen
    analysis_data_from_db = json.loads(document['analysis_data']) if document['analysis_data'] else {'sections': []}
    analyzed_sections_map = {s['id']: s for s in analysis_data_from_db.get('sections', [])}
    
    for db_sec_info in all_db_sections:
        analyzed_sec = analyzed_sections_map.get(db_sec_info['id'])
        section_data = {
            'id': db_sec_info['id'],
            'name': db_sec_info['name'],
            'level': db_sec_info['level'],
            'found': analyzed_sec.get('found', False) if analyzed_sec else False,
            'word_count': analyzed_sec.get('word_count', 0) if analyzed_sec else 0,
            'confidence': analyzed_sec.get('confidence', None) if analyzed_sec else None,
            'content': analyzed_sec.get('content', '') if analyzed_sec else '',
            'identifier': db_sec_info['identifier']
        }
        display_sections.append(section_data)

    return render_template(
        'analysis.html',
        document=document,
        document_type=document_type,
        organization=organization,
        sections=display_sections, # De lijst van gecombineerde secties
        feedback_items=feedback_items_data, # De verrijkte feedback items
        feedback_stats=feedback_stats
    )

@app.route('/documents/<int:document_id>/export')
def export_document(document_id):
    """Placeholder voor PDF export."""
    flash(f'Export PDF rapport functie voor document {document_id} nog niet geïmplementeerd.', 'info')
    return redirect(url_for('document_analysis', document_id=document_id))

@app.route('/documents/<int:document_id>/reanalyze')
def reanalyze_document(document_id):
    """Triggert een nieuwe analyse voor een document."""
    flash(f'Document {document_id} wordt opnieuw geanalyseerd...', 'info')
    # Doorsturen naar analyse pagina met 'reanalyze' argument
    return redirect(url_for('document_analysis', document_id=document_id, reanalyze=True))


# ================================================================
# Criteria Management Routes
# ================================================================
@app.route('/criteria')
def list_criteria():
    """Overzicht van alle criteria."""
    conn = get_db()
    criteria = conn.execute('''
        SELECT c.*, o.name AS organization_name, dt.name AS document_type_name
        FROM criteria c
        LEFT JOIN organizations o ON c.organization_id = o.id
        LEFT JOIN document_types dt ON c.document_type_id = dt.id
        ORDER BY c.name
    ''').fetchall()
    conn.close() # Close conn after fetchall()
    return render_template('criteria_list.html', criteria=criteria)

@app.route('/criteria/add', methods=('GET', 'POST'))
def add_criterion():
    """Formulier om een nieuw criterium toe te voegen."""
    conn = get_db()
    organizations = conn.execute('SELECT id, name FROM organizations').fetchall()
    document_types = conn.execute('SELECT id, name FROM document_types').fetchall()

    if request.method == 'POST':
        # Haal alle velden op volgens de criteria tabel
        org_id = request.form.get('organization_id')
        doc_type_id = request.form.get('document_type_id')
        name = request.form['name']
        description = request.form.get('description')
        category = request.form.get('category')
        color = request.form.get('color')
        severity = request.form.get('severity')
        is_enabled = 1 if request.form.get('is_enabled') == 'on' else 0
        fixed_feedback_text = request.form.get('fixed_feedback_text')
        error_message = request.form.get('error_message')
        instruction_link = request.form.get('instruction_link')
        rule_type = request.form.get('rule_type')
        application_scope = request.form.get('application_scope')
        max_mentions_per = request.form.get('max_mentions_per')
        frequency_unit = request.form.get('frequency_unit')

        # Typeconversie en standaardwaarden voor numerieke/FK velden
        org_id = int(org_id) if org_id else None
        doc_type_id = int(doc_type_id) if doc_type_id else None
        max_mentions_per = int(max_mentions_per) if max_mentions_per is not None and max_mentions_per.isdigit() else 0


        if not name:
            flash('Criterium naam is verplicht!', 'danger')
        else:
            try:
                conn.execute(
                    '''INSERT INTO criteria (
                        organization_id, document_type_id, name, description, category, color, severity,
                        is_enabled, fixed_feedback_text, error_message, instruction_link,
                        rule_type, application_scope, max_mentions_per, frequency_unit
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (org_id, doc_type_id, name, description, category, color, severity,
                     is_enabled, fixed_feedback_text, error_message, instruction_link,
                     rule_type, application_scope, max_mentions_per, frequency_unit)
                )
                conn.commit()
                flash('Criterium succesvol toegevoegd!', 'success')
                return redirect(url_for('list_criteria'))
            except sqlite3.IntegrityError as e:
                flash(f'Fout bij toevoegen: een criterium met deze naam en documenttype bestaat mogelijk al. {e}', 'danger')
            except Exception as e:
                flash(f'Er is een onverwachte fout opgetreden: {e}', 'danger')
            finally:
                conn.close()
    
    # Sluit de connectie voor GET request of POST met fout
    if conn:
        conn.close()
    
    return render_template('add_criterion.html', 
                           organizations=organizations, 
                           document_types=document_types,
                           form_data=request.form) # Pass form data back to pre-fill on error

@app.route('/criteria/edit/<int:id>', methods=('GET', 'POST'))
def edit_criterion(id):
    """Formulier om een bestaand criterium te bewerken."""
    conn = get_db()
    criterion = conn.execute('SELECT * FROM criteria WHERE id = ?', (id,)).fetchone()
    organizations = conn.execute('SELECT id, name FROM organizations').fetchall()
    document_types = conn.execute('SELECT id, name FROM document_types').fetchall()

    if criterion is None:
        conn.close()
        abort(404)

    if request.method == 'POST':
        org_id = request.form.get('organization_id')
        doc_type_id = request.form.get('document_type_id')
        name = request.form['name']
        description = request.form.get('description')
        category = request.form.get('category')
        color = request.form.get('color')
        severity = request.form.get('severity')
        is_enabled = 1 if request.form.get('is_enabled') == 'on' else 0
        fixed_feedback_text = request.form.get('fixed_feedback_text')
        error_message = request.form.get('error_message')
        instruction_link = request.form.get('instruction_link')
        rule_type = request.form.get('rule_type')
        application_scope = request.form.get('application_scope')
        max_mentions_per = request.form.get('max_mentions_per')
        frequency_unit = request.form.get('frequency_unit')

        org_id = int(org_id) if org_id else None
        doc_type_id = int(doc_type_id) if doc_type_id else None
        max_mentions_per = int(max_mentions_per) if max_mentions_per is not None and max_mentions_per.isdigit() else 0

        if not name:
            flash('Criterium naam is verplicht!', 'danger')
        else:
            try:
                conn.execute(
                    '''UPDATE criteria SET
                        organization_id = ?, document_type_id = ?, name = ?, description = ?, category = ?, color = ?, severity = ?,
                        is_enabled = ?, fixed_feedback_text = ?, error_message = ?, instruction_link = ?,
                        rule_type = ?, application_scope = ?, max_mentions_per = ?, frequency_unit = ?
                    WHERE id = ?''',
                    (org_id, doc_type_id, name, description, category, color, severity,
                     is_enabled, fixed_feedback_text, error_message, instruction_link,
                     rule_type, application_scope, max_mentions_per, frequency_unit, id)
                )
                conn.commit()
                flash('Criterium succesvol bijgewerkt!', 'success')
                return redirect(url_for('list_criteria'))
            except sqlite3.IntegrityError as e:
                flash(f'Fout bij bijwerken: een criterium met deze naam en documenttype bestaat mogelijk al. {e}', 'danger')
            except Exception as e:
                flash(f'Er is een onverwachte fout opgetreden: {e}', 'danger')
            finally:
                conn.close()

    # Sluit de connectie voor GET request of POST met fout
    if conn:
        conn.close()

    return render_template('edit_criterion.html', 
                           criterion=criterion, 
                           organizations=organizations, 
                           document_types=document_types,
                           form_data=request.form) # Pass form data for sticky fields


@app.route('/criteria/delete/<int:id>', methods=('POST',))
def delete_criterion(id):
    """Verwijder een criterium."""
    conn = get_db()
    try:
        conn.execute('DELETE FROM criteria WHERE id = ?', (id,))
        conn.commit()
        flash('Criterium succesvol verwijderd!', 'success')
    except sqlite3.Error as e:
        flash(f'Fout bij verwijderen van criterium: {e}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('list_criteria'))

# ================================================================
# Sectie Management Routes
# ================================================================
@app.route('/sections')
def list_sections():
    """Overzicht van alle secties."""
    conn = get_db()
    sections = conn.execute('''
        SELECT s.*, dt.name AS document_type_name, p.name AS parent_section_name
        FROM sections s
        JOIN document_types dt ON s.document_type_id = dt.id
        LEFT JOIN sections p ON s.parent_id = p.id
        ORDER BY dt.name, s.order_index
    ''').fetchall()
    conn.close()
    return render_template('sections_list.html', sections=sections)

@app.route('/sections/add', methods=('GET', 'POST'))
def add_section():
    """Formulier om een nieuwe sectie toe te voegen."""
    conn = get_db()
    document_types = conn.execute('SELECT id, name FROM document_types').fetchall()
    
    # Haal alle bestaande secties op voor de parent_id selectie (voor alle doc types)
    all_sections = conn.execute('SELECT id, name, document_type_id FROM sections').fetchall()

    if request.method == 'POST':
        doc_type_id = request.form['document_type_id']
        name = request.form['name']
        identifier = request.form['identifier']
        parent_id = request.form.get('parent_id')
        level = request.form.get('level', type=int)
        order_index = request.form.get('order_index', type=int)
        alternative_names_str = request.form.get('alternative_names', '')
        pattern = request.form.get('pattern')
        is_required = 1 if request.form.get('is_required') == 'on' else 0
        description = request.form.get('description')

        parent_id = int(parent_id) if parent_id else None
        
        # Converteer alternative_names naar JSON string
        try:
            alternative_names_list = [n.strip() for n in alternative_names_str.split(',') if n.strip()]
            alternative_names_json = json.dumps(alternative_names_list)
        except Exception:
            alternative_names_json = json.dumps([]) # Fallback

        if not name or not identifier or not doc_type_id or not pattern:
            flash('Naam, identifier, documenttype en patroon zijn verplicht!', 'danger')
        else:
            try:
                conn.execute(
                    '''INSERT INTO sections (document_type_id, name, identifier, parent_id, level, order_index, alternative_names, pattern, is_required, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (doc_type_id, name, identifier, parent_id, level, order_index, alternative_names_json, pattern, is_required, description)
                )
                conn.commit()
                flash('Sectie succesvol toegevoegd!', 'success')
                return redirect(url_for('list_sections'))
            except sqlite3.IntegrityError as e:
                flash(f'Fout bij toevoegen: een sectie met deze identifier en documenttype bestaat mogelijk al. {e}', 'danger')
            except Exception as e:
                flash(f'Er is een onverwachte fout opgetreden: {e}', 'danger')
            finally:
                conn.close()
    
    if conn:
        conn.close()
    
    return render_template('add_section.html', 
                           document_types=document_types, 
                           all_sections=all_sections, # Pass all sections for parent dropdown
                           form_data=request.form)

@app.route('/sections/edit/<int:id>', methods=('GET', 'POST'))
def edit_section(id):
    """Formulier om een bestaande sectie te bewerken."""
    conn = get_db()
    section = conn.execute('SELECT * FROM sections WHERE id = ?', (id,)).fetchone()
    document_types = conn.execute('SELECT id, name FROM document_types').fetchall()
    all_sections = conn.execute('SELECT id, name, document_type_id FROM sections').fetchall() # Alle secties voor parent selectie

    if section is None:
        conn.close()
        abort(404)

    if request.method == 'POST':
        doc_type_id = request.form['document_type_id']
        name = request.form['name']
        identifier = request.form['identifier']
        parent_id = request.form.get('parent_id')
        level = request.form.get('level', type=int)
        order_index = request.form.get('order_index', type=int)
        alternative_names_str = request.form.get('alternative_names', '')
        pattern = request.form.get('pattern')
        is_required = 1 if request.form.get('is_required') == 'on' else 0
        description = request.form.get('description')

        parent_id = int(parent_id) if parent_id else None
        
        try:
            alternative_names_list = [n.strip() for n in alternative_names_str.split(',') if n.strip()]
            alternative_names_json = json.dumps(alternative_names_list)
        except Exception:
            alternative_names_json = json.dumps([])

        if not name or not identifier or not doc_type_id or not pattern:
            flash('Naam, identifier, documenttype en patroon zijn verplicht!', 'danger')
        else:
            try:
                conn.execute(
                    '''UPDATE sections SET
                        document_type_id = ?, name = ?, identifier = ?, parent_id = ?, level = ?, order_index = ?, alternative_names = ?, pattern = ?, is_required = ?, description = ?
                    WHERE id = ?''',
                    (doc_type_id, name, identifier, parent_id, level, order_index, alternative_names_json, pattern, is_required, description, id)
                )
                conn.commit()
                flash('Sectie succesvol bijgewerkt!', 'success')
                return redirect(url_for('list_sections'))
            except sqlite3.IntegrityError as e:
                flash(f'Fout bij bijwerken: een sectie met deze identifier en documenttype bestaat mogelijk al. {e}', 'danger')
            except Exception as e:
                flash(f'Er is een onverwachte fout opgetreden: {e}', 'danger')
            finally:
                conn.close()

    if conn:
        conn.close()
    
    # Voor GET request, converteer alternative_names JSON terug naar string
    if section and section['alternative_names']:
        try:
            section_alt_names_list = json.loads(section['alternative_names'])
            section_alt_names_str = ", ".join(section_alt_names_list)
        except (json.JSONDecodeError, TypeError):
            section_alt_names_str = section['alternative_names'] # Fallback
    else:
        section_alt_names_str = ""

    return render_template('edit_section.html', 
                           section=section, 
                           document_types=document_types, 
                           all_sections=all_sections,
                           alternative_names_str=section_alt_names_str, # Pass string for form field
                           form_data=request.form)

@app.route('/sections/delete/<int:id>', methods=('POST',))
def delete_section(id):
    """Verwijder een sectie."""
    conn = get_db()
    try:
        conn.execute('DELETE FROM sections WHERE id = ?', (id,))
        conn.commit()
        flash('Sectie succesvol verwijderd!', 'success')
    except sqlite3.Error as e:
        flash(f'Fout bij verwijderen van sectie: {e}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('list_sections'))


# ================================================================
# Document Type Management Routes
# ================================================================
@app.route('/document_types')
def list_document_types():
    """Overzicht van alle documenttypes."""
    conn = get_db()
    document_types = conn.execute('''
        SELECT dt.*, o.name AS organization_name
        FROM document_types dt
        LEFT JOIN organizations o ON dt.organization_id = o.id
        ORDER BY dt.name
    ''').fetchall()
    conn.close()
    return render_template('document_types_list.html', document_types=document_types)

@app.route('/document_types/add', methods=('GET', 'POST'))
def add_document_type():
    """Formulier om een nieuw documenttype toe te voegen."""
    conn = get_db()
    organizations = conn.execute('SELECT id, name FROM organizations').fetchall()

    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description')
        organization_id = request.form.get('organization_id')

        organization_id = int(organization_id) if organization_id else None

        if not name:
            flash('Naam van documenttype is verplicht!', 'danger')
        else:
            try:
                conn.execute(
                    'INSERT INTO document_types (name, description, organization_id) VALUES (?, ?, ?)',
                    (name, description, organization_id)
                )
                conn.commit()
                flash('Documenttype succesvol toegevoegd!', 'success')
                return redirect(url_for('list_document_types'))
            except sqlite3.IntegrityError as e:
                flash(f'Fout bij toevoegen: een documenttype met deze naam bestaat al voor deze organisatie. {e}', 'danger')
            except Exception as e:
                flash(f'Er is een onverwachte fout opgetreden: {e}', 'danger')
            finally:
                conn.close()
    
    if conn:
        conn.close()

    return render_template('add_document_type.html', organizations=organizations, form_data=request.form)

@app.route('/document_types/edit/<int:id>', methods=('GET', 'POST'))
def edit_document_type(id):
    """Formulier om een bestaand documenttype te bewerken."""
    conn = get_db()
    doc_type = conn.execute('SELECT * FROM document_types WHERE id = ?', (id,)).fetchone()
    organizations = conn.execute('SELECT id, name FROM organizations').fetchall()

    if doc_type is None:
        conn.close()
        abort(404)

    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description')
        organization_id = request.form.get('organization_id')

        organization_id = int(organization_id) if organization_id else None

        if not name:
            flash('Naam van documenttype is verplicht!', 'danger')
        else:
            try:
                conn.execute(
                    'UPDATE document_types SET name = ?, description = ?, organization_id = ? WHERE id = ?',
                    (name, description, organization_id, id)
                )
                conn.commit()
                flash('Documenttype succesvol bijgewerkt!', 'success')
                return redirect(url_for('list_document_types'))
            except sqlite3.IntegrityError as e:
                flash(f'Fout bij bijwerken: een documenttype met deze naam bestaat al voor deze organisatie. {e}', 'danger')
            except Exception as e:
                flash(f'Er is een onverwachte fout opgetreden: {e}', 'danger')
            finally:
                conn.close()

    if conn:
        conn.close()

    return render_template('edit_document_type.html', doc_type=doc_type, organizations=organizations, form_data=request.form)

@app.route('/document_types/delete/<int:id>', methods=('POST',))
def delete_document_type(id):
    """Verwijder een documenttype."""
    conn = get_db()
    try:
        # Check for dependent sections before deleting
        sections_count = conn.execute('SELECT COUNT(*) FROM sections WHERE document_type_id = ?', (id,)).fetchone()[0]
        if sections_count > 0:
            flash(f'Kan documenttype niet verwijderen: {sections_count} gekoppelde secties gevonden. Verwijder eerst de secties.', 'danger')
        else:
            # Check for dependent documents
            documents_count = conn.execute('SELECT COUNT(*) FROM documents WHERE document_type_id = ?', (id,)).fetchone()[0]
            if documents_count > 0:
                flash(f'Kan documenttype niet verwijderen: {documents_count} gekoppelde documenten gevonden. Verwijder eerst de documenten.', 'danger')
            else:
                conn.execute('DELETE FROM document_types WHERE id = ?', (id,))
                conn.commit()
                flash('Documenttype succesvol verwijderd!', 'success')
    except sqlite3.Error as e:
        flash(f'Fout bij verwijderen van documenttype: {e}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('list_document_types'))


# ================================================================
# Organisatie Management Routes
# ================================================================
@app.route('/organizations')
def list_organizations():
    """Overzicht van alle organisaties."""
    conn = get_db()
    organizations = conn.execute('SELECT * FROM organizations ORDER BY name').fetchall()
    conn.close()
    return render_template('organizations_list.html', organizations=organizations)

@app.route('/organizations/add', methods=('GET', 'POST'))
def add_organization():
    """Formulier om een nieuwe organisatie toe te voegen."""
    conn = get_db()
    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description')

        if not name:
            flash('Naam van organisatie is verplicht!', 'danger')
        else:
            try:
                conn.execute('INSERT INTO organizations (name, description) VALUES (?, ?)', (name, description))
                conn.commit()
                flash('Organisatie succesvol toegevoegd!', 'success')
                return redirect(url_for('list_organizations'))
            except sqlite3.IntegrityError:
                flash('Een organisatie met deze naam bestaat al.', 'danger')
            except Exception as e:
                flash(f'Er is een onverwachte fout opgetreden: {e}', 'danger')
            finally:
                conn.close()
    
    if conn:
        conn.close()

    return render_template('add_organization.html', form_data=request.form)

@app.route('/organizations/edit/<int:id>', methods=('GET', 'POST'))
def edit_organization(id):
    """Formulier om een bestaande organisatie te bewerken."""
    conn = get_db()
    organization = conn.execute('SELECT * FROM organizations WHERE id = ?', (id,)).fetchone()

    if organization is None:
        conn.close()
        abort(404)

    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description')

        if not name:
            flash('Naam van organisatie is verplicht!', 'danger')
        else:
            try:
                conn.execute('UPDATE organizations SET name = ?, description = ? WHERE id = ?', (name, description, id))
                conn.commit()
                flash('Organisatie succesvol bijgewerkt!', 'success')
                return redirect(url_for('list_organizations'))
            except sqlite3.IntegrityError:
                flash('Een organisatie met deze naam bestaat al.', 'danger')
            except Exception as e:
                flash(f'Er is een onverwachte fout opgetreden: {e}', 'danger')
            finally:
                conn.close()

    if conn:
        conn.close()

    return render_template('edit_organization.html', organization=organization, form_data=request.form)

@app.route('/organizations/delete/<int:id>', methods=('POST',))
def delete_organization(id):
    """Verwijder een organisatie."""
    conn = get_db()
    try:
        # Check for dependent document_types
        doc_types_count = conn.execute('SELECT COUNT(*) FROM document_types WHERE organization_id = ?', (id,)).fetchone()[0]
        if doc_types_count > 0:
            flash(f'Kan organisatie niet verwijderen: {doc_types_count} gekoppelde documenttypes gevonden. Verwijder eerst de documenttypes.', 'danger')
        else:
            # Check for dependent documents
            documents_count = conn.execute('SELECT COUNT(*) FROM documents WHERE organization_id = ?', (id,)).fetchone()[0]
            if documents_count > 0:
                flash(f'Kan organisatie niet verwijderen: {documents_count} gekoppelde documenten gevonden. Verwijder eerst de documenten.', 'danger')
            else:
                conn.execute('DELETE FROM organizations WHERE id = ?', (id,))
                conn.commit()
                flash('Organisatie succesvol verwijderd!', 'success')
    except sqlite3.Error as e:
        flash(f'Fout bij verwijderen van organisatie: {e}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('list_organizations'))
    
# ================================================================
# Hoofduitvoerder voor de applicatie
# ================================================================
if __name__ == '__main__':
    # Flask's ingebouwde development server
    # Zorg dat debug=True is tijdens ontwikkeling voor automatische herlaad en debugger
    app.run(debug=True)
# ================================================================
# Functie om de database pragmas toe te passen
# (Moet worden aangeroepen bij elke nieuwe DB-verbinding)
# Nu aangeroepen in db_utils.get_db()
# ================================================================