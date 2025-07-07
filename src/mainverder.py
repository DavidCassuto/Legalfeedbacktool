import os
import sqlite3
import json
from flask import Flask, request, render_template, g, redirect, url_for, flash
from werkzeug.utils import secure_filename

# Importeer de analysefuncties
from src.analysis import document_parsing, section_recognition, criterion_evaluation
from src import db_utils

# Configuratie
UPLOAD_FOLDER = 'uploads'
DATABASE = 'instance/documents.db'
ALLOWED_EXTENSIONS = {'docx', 'txt'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['DATABASE'] = DATABASE
app.secret_key = 'your_secret_key_here' # VERANDER DIT VOOR PRODUCTIE!

# Zorg ervoor dat de uploadmap bestaat
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs('instance', exist_ok=True) # Zorg ervoor dat de instance map bestaat voor de database

def get_db():
    """Haalt een databaseverbinding op voor de huidige request context."""
    if 'db' not in g:
        g.db = sqlite3.connect(
            app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row # Dit zorgt ervoor dat rijen als dictionaries worden geretourneerd
        db_utils.initialize_db(g.db) # Initialiseer de database bij de eerste connectie
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    """Sluit de databaseverbinding aan het einde van de request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()
        print("Databaseverbinding gesloten (via close_db).") # Debugging print

def allowed_file(filename):
    """Controleert of de bestandsextensie is toegestaan."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """Startpagina: toont een lijst van geüploade documenten."""
    conn = get_db()
    cursor = conn.cursor()
    documents = cursor.execute("SELECT * FROM documents ORDER BY uploaded_at DESC").fetchall()
    return render_template('index.html', documents=documents)

@app.route('/upload', methods=['GET', 'POST'])
def upload_document():
    """Uploadpagina: verwerkt het uploaden en analyseren van documenten."""
    conn = get_db()
    document_types = db_utils.get_document_types(conn) # Haal documenttypen op
    organizations = db_utils.get_organizations(conn) # Haal organisaties op

    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Geen bestand geselecteerd', 'error')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('Geen bestand geselecteerd', 'error')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            doc_name = request.form.get('document_name')
            doc_type_id = request.form.get('document_type_id')
            organization_id = request.form.get('organization_id')

            # Sla documentinformatie op in de database
            doc_id = db_utils.add_document(conn, doc_name, filename, file_path, doc_type_id, organization_id)
            flash(f'Bestand {filename} succesvol geüpload!', 'success')

            # Start analyse
            print(f"Start analyse voor document ID: {doc_id}")
            analyze_document(doc_id)
            return redirect(url_for('analysis_result', doc_id=doc_id))
        else:
            flash('Ongeldig bestandstype', 'error')
            return redirect(request.url)
    
    return render_template('upload.html', document_types=document_types, organizations=organizations)

def analyze_document(doc_id):
    """Voert de analyse uit voor een gegeven document-ID."""
    conn = get_db()
    doc_info = db_utils.get_document_by_id(conn, doc_id)
    if not doc_info:
        print(f"Fout: Document met ID {doc_id} niet gevonden.")
        return

    doc_content, paragraphs, all_headings = document_parsing.extract_document_content(doc_info['file_path'])
    
    # Haal de verwachte secties en criteria op basis van documenttype
    expected_sections_metadata = db_utils.get_sections_for_document_type(conn, doc_info['document_type_id'])
    criteria_for_doc_type = db_utils.get_criteria_for_document_type(conn, doc_info['document_type_id'])

    # Herken secties
    recognized_sections = section_recognition.recognize_and_enrich_sections(
        doc_content, paragraphs, all_headings, expected_sections_metadata
    )
    
    # Evalueer criteria en genereer feedback
    feedback_items = criterion_evaluation.evaluate_document_criteria(
        doc_content, paragraphs, recognized_sections, criteria_for_doc_type
    )

    # Sla feedback op in de database
    for item in feedback_items:
        db_utils.save_feedback_item(conn, item, doc_id)
    
    # Update document status
    db_utils.update_document_analysis_status(conn, doc_id, 'completed')
    print(f"Analyse voor document ID: {doc_id} voltooid.")

@app.route('/analysis/<int:doc_id>')
def analysis_result(doc_id):
    """Toont de analyseresultaten voor een document."""
    conn = get_db()
    doc_info = db_utils.get_document_by_id(conn, doc_id)
    if not doc_info:
        flash('Document niet gevonden.', 'error')
        return redirect(url_for('index'))

    # Haal de werkelijk herkende secties op (uit de analyse_data als JSON)
    doc_content, paragraphs, all_headings = document_parsing.extract_document_content(doc_info['file_path'])
    expected_sections_metadata = db_utils.get_sections_for_document_type(conn, doc_info['document_type_id'])
    recognized_sections = section_recognition.recognize_and_enrich_sections(
        doc_content, paragraphs, all_headings, expected_sections_metadata
    )

    # Haal feedback items op
    feedback_items = db_utils.get_feedback_for_document(conn, doc_id)

    # Organiseer feedback per sectie
    feedback_by_section = {}
    for item in feedback_items:
        section_name = item['section_name'] if item['section_name'] else 'Algemeen Document'
        if section_name not in feedback_by_section:
            feedback_by_section[section_name] = []
        feedback_by_section[section_name].append(item)
    
    # Voeg ook de 'found' status en word_count toe aan de sections voor weergave
    sections_for_display = []
    for es in expected_sections_metadata:
        found_match = next((rs for rs in recognized_sections if rs['identifier'] == es['identifier']), None)
        if found_match:
            es['found'] = True
            es['content_found'] = found_match['content'] # Voeg de gevonden content toe
            es['word_count'] = found_match['word_count']
            es['found_level'] = found_match.get('found_level') # Toon het daadwerkelijk gevonden niveau
            es['headings'] = found_match['headings']
        else:
            es['found'] = False
            es['content_found'] = ""
            es['word_count'] = 0
            es['found_level'] = None
            es['headings'] = []
        sections_for_display.append(es)

    # Sorteer secties voor weergave (voor een consistente volgorde)
    sections_for_display.sort(key=lambda x: (x.get('order_index', 999), x.get('level', 999)))

    return render_template(
        'analysis_result.html',
        doc=doc_info,
        recognized_sections=sections_for_display,
        feedback_by_section=feedback_by_section
    )

@app.route('/sections', methods=['GET'])
def list_sections():
    """Toont een lijst van alle gedefinieerde secties."""
    conn = get_db()
    # Haal secties op inclusief de geparsede alternative_names
    sections = db_utils.get_sections_for_document_type(conn, 1) 
    return render_template('sections_list.html', sections=sections)

@app.route('/sections/add', methods=['GET', 'POST'])
def add_section():
    """Voegt een nieuwe sectie toe aan de database."""
    conn = get_db()
    sections = db_utils.get_sections_for_document_type(conn, 1) # Voor parent selectie
    if request.method == 'POST':
        name = request.form['name']
        identifier = request.form['identifier']
        is_required = 'is_required' in request.form
        parent_id = request.form.get('parent_id')
        alternative_names_str = request.form.get('alternative_names')
        order_index = request.form.get('order_index', type=int)
        level = request.form.get('level', type=int)

        alternative_names = [an.strip() for an in alternative_names_str.split(',') if an.strip()] if alternative_names_str else []
        
        db_utils.add_section(conn, name, identifier, is_required, parent_id, json.dumps(alternative_names), order_index, level)
        flash('Sectie succesvol toegevoegd!', 'success')
        return redirect(url_for('list_sections'))
    return render_template('add_section.html', sections=sections)

@app.route('/sections/edit/<int:section_id>', methods=['GET', 'POST'])
def edit_section(section_id):
    """Bewerkt een bestaande sectie."""
    conn = get_db()
    section = db_utils.get_section_by_id(conn, section_id)
    if not section:
        flash('Sectie niet gevonden.', 'error')
        return redirect(url_for('list_sections'))
    
    sections_for_parent = db_utils.get_sections_for_document_type(conn, 1) # Voor parent selectie
    
    # Parse alternative_names van JSON string naar Python list
    if section['alternative_names']:
        section_alternative_names = json.loads(section['alternative_names'])
    else:
        section_alternative_names = []
    
    if request.method == 'POST':
        name = request.form['name']
        identifier = request.form['identifier']
        is_required = 'is_required' in request.form
        parent_id = request.form.get('parent_id')
        alternative_names_str = request.form.get('alternative_names')
        order_index = request.form.get('order_index', type=int)
        level = request.form.get('level', type=int)

        alternative_names = [an.strip() for an in alternative_names_str.split(',') if an.strip()] if alternative_names_str else []
        
        db_utils.update_section(conn, section_id, name, identifier, is_required, parent_id, json.dumps(alternative_names), order_index, level)
        flash('Sectie succesvol bijgewerkt!', 'success')
        return redirect(url_for('list_sections'))
    
    # Geef de alternative_names als komma-gescheiden string door aan de template
    section['alternative_names'] = ", ".join(section_alternative_names)
    return render_template('edit_section.html', section=section, sections=sections_for_parent)

@app.route('/sections/delete/<int:section_id>', methods=['POST'])
def delete_section(section_id):
    """Verwijdert een sectie uit de database."""
    conn = get_db()
    db_utils.delete_section(conn, section_id)
    flash('Sectie succesvol verwijderd!', 'success')
    return redirect(url_for('list_sections'))

@app.route('/criteria', methods=['GET'])
def list_criteria():
    """Toont een lijst van alle gedefinieerde criteria."""
    conn = get_db()
    criteria = db_utils.get_all_criteria(conn)
    return render_template('criteria_list.html', criteria=criteria)

@app.route('/criteria/add', methods=['GET', 'POST'])
def add_criterion():
    """Voegt een nieuw criterium toe aan de database."""
    conn = get_db()
    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description')
        rule_type = request.form['rule_type']
        application_scope = request.form['application_scope']
        is_enabled = 'is_enabled' in request.form
        severity = request.form['severity']
        error_message = request.form.get('error_message')
        fixed_feedback_text = request.form.get('fixed_feedback_text')
        frequency_unit = request.form['frequency_unit']
        max_mentions_per = request.form.get('max_mentions_per', type=int)
        expected_value_min = request.form.get('expected_value_min', type=float)
        expected_value_max = request.form.get('expected_value_max', type=float)
        color = request.form.get('color')

        db_utils.add_criterion(
            conn, name, description, rule_type, application_scope,
            is_enabled, severity, error_message, fixed_feedback_text,
            frequency_unit, max_mentions_per, expected_value_min,
            expected_value_max, color
        )
        flash('Criterium succesvol toegevoegd!', 'success')
        return redirect(url_for('list_criteria'))
    return render_template('add_criterion.html')

@app.route('/criteria/edit/<int:criteria_id>', methods=['GET', 'POST'])
def edit_criterion(criteria_id):
    """Bewerkt een bestaand criterium."""
    conn = get_db()
    criterion = db_utils.get_criterion_by_id(conn, criteria_id)
    if not criterion:
        flash('Criterium niet gevonden.', 'error')
        return redirect(url_for('list_criteria'))
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form.get('description')
        rule_type = request.form['rule_type']
        application_scope = request.form['application_scope']
        is_enabled = 'is_enabled' in request.form
        severity = request.form['severity']
        error_message = request.form.get('error_message')
        fixed_feedback_text = request.form.get('fixed_feedback_text')
        frequency_unit = request.form['frequency_unit']
        max_mentions_per = request.form.get('max_mentions_per', type=int)
        expected_value_min = request.form.get('expected_value_min', type=float)
        expected_value_max = request.form.get('expected_value_max', type=float)
        color = request.form.get('color')

        db_utils.update_criterion(
            conn, criteria_id, name, description, rule_type, application_scope,
            is_enabled, severity, error_message, fixed_feedback_text,
            frequency_unit, max_mentions_per, expected_value_min,
            expected_value_max, color
        )
        flash('Criterium succesvol bijgewerkt!', 'success')
        return redirect(url_for('list_criteria'))
    
    return render_template('edit_criterion.html', criterion=criterion)

@app.route('/criteria/delete/<int:criteria_id>', methods=['POST'])
def delete_criterion(criteria_id):
    """Verwijdert een criterium uit de database."""
    conn = get_db()
    db_utils.delete_criterion(conn, criteria_id)
    flash('Criterium succesvol verwijderd!', 'success')
    return redirect(url_for('list_criteria'))

@app.route('/criteria/<int:criteria_id>/map_sections', methods=['GET', 'POST'])
def map_criteria_to_sections(criteria_id):
    """Beheert de mapping van een criterium aan secties (include/exclude)."""
    conn = get_db()
    criterion = db_utils.get_criterion_by_id(conn, criteria_id)
    if not criterion:
        flash('Criterium niet gevonden.', 'error')
        return redirect(url_for('list_criteria'))

    all_sections = db_utils.get_sections_for_document_type(conn, 1) # Alle secties ophalen
    current_mappings = db_utils.get_criterion_section_mappings(conn, criteria_id)
    
    # Maak dictionaries voor snelle lookup
    mapped_sections = {m['section_id']: m for m in current_mappings}

    if request.method == 'POST':
        # Verwijder eerst alle bestaande mappings voor dit criterium
        db_utils.delete_all_section_mappings_for_criterion(conn, criteria_id)

        # Voeg nieuwe mappings toe op basis van form data
        selected_section_ids = request.form.getlist('selected_sections')
        excluded_section_ids = request.form.getlist('excluded_sections')

        for section_id_str in selected_section_ids:
            section_id = int(section_id_str)
            db_utils.add_criterion_section_mapping(conn, criteria_id, section_id, is_excluded=0)
        
        for section_id_str in excluded_section_ids:
            section_id = int(section_id_str)
            db_utils.add_criterion_section_mapping(conn, criteria_id, section_id, is_excluded=1)
        
        # Update application_scope van het criterium op basis van geselecteerde optie
        application_scope = request.form.get('application_scope')
        if application_scope not in ['all', 'document_only', 'specific_sections', 'exclude_sections']:
             application_scope = 'all' # Fallback
        db_utils.update_criterion_application_scope(conn, criteria_id, application_scope)

        flash(f'Sectie mappings voor criterium "{criterion["name"]}" succesvol bijgewerkt!', 'success')
        return redirect(url_for('list_criteria'))

    return render_template(
        'criteria_section_mapping.html',
        criterion=criterion,
        all_sections=all_sections,
        mapped_sections=mapped_sections # Dict met {section_id: mapping_obj}
    )


# Run de applicatie
if __name__ == '__main__':
    app.run(debug=True)
