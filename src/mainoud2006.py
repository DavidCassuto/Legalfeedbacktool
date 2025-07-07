import os
import docx
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, g, current_app, abort, session
import datetime
import json
import click
from .db_utils import get_db, init_app # close_db en init_db_command worden via init_app geregistreerd
# Importeer je analysemodules. Pas deze paden aan als je bestandsnamen anders zijn.
from .analysis import document_parsing
from .analysis import section_recognition
from .analysis import criterion_checking
from . import db_utils
# from .analysis import smart_utilities # Alleen decommenteren als je een smart_utilities.py bestand hebt.


# --- Configuratie ---
# Alle runtime-gegenereerde bestanden gaan naar de 'instance' map.
# Dit maakt de 'src' map schoon en faciliteert deployment.
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, '..', 'instance') # 'instance' map is nu een niveau hoger dan 'src'

DATABASE = os.path.join(INSTANCE_DIR, 'documents.db')
UPLOAD_FOLDER = os.path.join(INSTANCE_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'docx'}

app = Flask(__name__, instance_relative_config=True)
@app.context_processor
def inject_now():
    return {'now': datetime.datetime.now(datetime.UTC)}
app.config.from_mapping(
    SECRET_KEY='feedback-tool-secret-key-2024', # JOUW SECRET KEY
    DATABASE=DATABASE,
    UPLOAD_FOLDER=UPLOAD_FOLDER
)
init_app(app)
# Zorg ervoor dat de instance en uploadmappen bestaan
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.dirname(app.config['DATABASE']), exist_ok=True)


# --- Database Functies ---

# Jouw initialize_database functie met PRAGMA's
def apply_db_pragmas(conn_obj):
    """Initialiseert de SQLite-database met optimale instellingen (PRAGMA's)."""
    cursor = conn_obj.cursor()

    # Optimalisaties voor concurrentie
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")

    # Optimalisaties voor prestaties
    cursor.execute("PRAGMA cache_size=-10000")  # 10MB cache
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA temp_store=MEMORY")

    # Activeer foreign keys
    cursor.execute("PRAGMA foreign_keys=ON")

    conn_obj.commit()

# Jouw get_db_connection functie, aangepast voor Flask's g-object
def get_db():
    if 'db' not in g:
        try:
            conn = sqlite3.connect(
                app.config['DATABASE'],
                detect_types=sqlite3.PARSE_DECLTYPES
            )
            conn.row_factory = sqlite3.Row # Zorgt dat je rijen als dictionary-achtige objecten kunt benaderen
            g.db = conn
            apply_db_pragmas(g.db) # Roep je PRAGMA functie aan op de zojuist geopende connectie
        except sqlite3.Error as e:
            print(f"Fout bij verbinden met database: {e}")
            flash("Fout bij verbinden met de database.", "error")
            g.db = None # Zorg dat g.db None is als connectie faalt
    return g.db

# Functie om de database-verbinding te sluiten na elke request
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

app.teardown_appcontext(close_db) # Registreer de functie voor automatische sluiting


# -hieronder stond --def init_db_commands(): Functie om de database schema's te creëren en voorbeelddata te vullen ---
# Zorg dat de eerder gedefinieerde constanten BASE_DIR, INSTANCE_DIR, DATABASE, UPLOAD_FOLDER, ALLOWED_EXTENSIONS hierboven nog steeds bestaan.
# Bijvoorbeeld:
# BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# INSTANCE_DIR = os.path.join(BASE_DIR, '..', 'instance')
# DATABASE = os.path.join(INSTANCE_DIR, 'documents.db') # Dit moet dan ook gebruikt worden in app.config['DATABASE']


# Command-line functie om de database te initialiseren
@app.cli.command('init-db')
def init_db_command():
    """Clear the existing data and create new tables, then populate."""
    # Verwijder de bestaande databasefile als deze bestaat om opnieuw te beginnen
    if os.path.exists(app.config['DATABASE']):
        os.remove(app.config['DATABASE'])
        print(f"Bestaande database '{app.config['DATABASE']}' verwijderd.")
    
    # Roep de init_db_commands functie aan vanuit db_utils
    # Deze functie heeft een app context nodig als het current_app.config gebruikt
    with app.app_context():
        db_utils.init_db_commands() # <--- GEKORRIGEERD!
    click.echo('Database succesvol geïnitialiseerd.')


# --- Helper voor bestandsvalidatie ---
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Flask Routes ---

@app.route('/')
def index():
    # Stuurt direct door naar de upload-pagina voor nu
    return redirect(url_for('upload_file'))

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Geen bestand geselecteerd.', 'error')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('Geen geselecteerd bestand.', 'error')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            original_filename = file.filename
            
            # Genereer een unieke bestandsnaam om conflicten te voorkomen
            unique_filename = f"{os.urandom(16).hex()}_{original_filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)

            db = get_db()
            if db is None: # Controleer of de DB-verbinding gelukt is
                return redirect(request.url)

            cursor = db.cursor()

            # Voorlopig hardcode de organization_id en document_type_id.
            # Later haal je deze dynamisch op via een formulier of gebruikerssessie.
            org_id_for_upload = cursor.execute("SELECT id FROM organizations WHERE name = 'Hogeschool Inholland'").fetchone()
            if org_id_for_upload:
                org_id_for_upload = org_id_for_upload[0]
            else:
                flash('Fout: Organisatie "Hogeschool Inholland" niet gevonden.', 'error')
                return redirect(request.url)

            doc_type_id_for_upload = cursor.execute("SELECT id FROM document_types WHERE name = 'Plan van Aanpak' AND organization_id = ?", (org_id_for_upload,)).fetchone()
            if doc_type_id_for_upload:
                doc_type_id_for_upload = doc_type_id_for_upload[0]
            else:
                flash('Fout: Documenttype "Plan van Aanpak" niet gevonden voor deze organisatie.', 'error')
                return redirect(request.url)


            cursor.execute("""
                INSERT INTO documents (filename, original_filename, document_type_id, organization_id, file_path, file_size, analysis_status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (unique_filename, original_filename, doc_type_id_for_upload, org_id_for_upload, filepath, os.path.getsize(filepath), 'pending'))
            document_id = cursor.lastrowid
            db.commit()

            flash(f'Document "{original_filename}" succesvol geüpload en analyse gestart.', 'success')
            
            # TODO: Hier moet de asynchrone analyse getriggerd worden!
            # Voor nu redirecten we direct naar de analyse pagina met (nog) dummy data
            return redirect(url_for('analyze_document', document_id=document_id))
        else:
            flash('Ongeldig bestandstype. Alleen .docx is toegestaan.', 'error')
    return render_template('upload.html')

@app.route('/analysis/<int:document_id>')
def analyze_document(document_id):
    db = get_db()
    if db is None:
        flash("Kan document niet laden: geen databaseverbinding.", "error")
        return redirect(url_for('index'))

    document = db.execute('SELECT * FROM documents WHERE id = ?', (document_id,)).fetchone()
    if document is None:
        flash('Document niet gevonden.', 'error')
        return redirect(url_for('index'))

    document_type = db.execute('SELECT * FROM document_types WHERE id = ?', (document['document_type_id'],)).fetchone()
    if document_type is None:
        flash('Documenttype niet gevonden voor dit document.', 'error')
        return redirect(url_for('index'))

    # Nieuw: Haal organisatie-informatie op (nodig voor criteria filtering)
    organization = db.execute('SELECT * FROM organizations WHERE id = ?', (document['organization_id'],)).fetchone()
    if organization is None:
        flash('Organisatie niet gevonden voor dit document.', 'error')
        return redirect(url_for('index'))

    try:
        doc_content = document_parsing.extract_document_content(document['file_path'])
    except Exception as e:
        flash(f"Fout bij het parsen van het document: {e}", "error")
        return redirect(url_for('index'))

    recognized_sects = section_recognition.recognize_sections(
        doc_content,
        document_type['id'],
        db
    )

   # --- VOEG DEZE REGELS HIER TOE ---
    print("DEBUG: Recognized Sections Output:")
    for section in recognized_sects:
        print(f"  - Identifier: {section.get('identifier')}, Name: {section.get('name')}, DB ID: {section.get('id')}, Content snippet: {section.get('content', '')[:100]}...")
    print("-" * 50)
    # --- EINDE TOE TE VOEGEN REGELS ---

    # --- NIEUW: HAAL DE ECHTE CRITERIA OP ---
    # Gebruik de nieuwe helper functie
    criteria_for_analysis = db_utils.get_criteria_for_document_type(db, document_type['id'], organization['id'])

    # --- NIEUW: GENEREER FEEDBACK MET ECHTE DATA ---
    # Je hebt een functie zoals `criterion_checking.generate_feedback` nodig die:
    # 1. doc_content accepteert (gehele document tekst)
    # 2. recognized_sections accepteert (de herkende secties met hun content)
    # 3. criteria_list accepteert (de lijst met criteria uit de database)
    # 4. db_connection accepteert (om extra DB lookups te doen indien nodig)
    # 5. Uiteindelijk een lijst met feedback items retourneert
    
    # Deze functie moet ook de `max_occurrences_per` logica implementeren.
    # Als je deze functie nog niet hebt, moeten we die bouwen.
    # Ik ga er vanuit dat je in `analysis/criterion_checking.py` zoiets hebt.

    generated_feedback_items = criterion_checking.generate_feedback(
        doc_content,
        recognized_sects, # Gebruik de correcte variabele naam
        criteria_for_analysis,
        db,
        document_id,      # Dit is het document ID van het geanalyseerde document
        document_type['id'] # Dit is het ID van het documenttype
    )

    # --- NIEUW: SLA DE GEGENEREERDE FEEDBACK OP IN DE DATABASE ---
    cursor = db.cursor()
    for feedback_item in generated_feedback_items:
        # Zorg dat de velden overeenkomen met je feedback_items tabel
        cursor.execute("""
            INSERT INTO feedback_items (
                document_id, criteria_id, section_id, status, message, suggestion,
                location, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            document_id,
            feedback_item.get('criteria_id'), # Belangrijk: link naar het criterium ID
            feedback_item.get('section_id'), # Kan NULL zijn
            feedback_item.get('status'),
            feedback_item.get('message'),
            feedback_item.get('suggestion'),
            feedback_item.get('location'),
            feedback_item.get('confidence'),
            datetime.now() # Of een timestamp uit de feedback_item zelf als je die daar genereert
        ))
    db.commit()

    # --- NIEUW: HAAL DE OPGESLAGEN FEEDBACK ITEMS OP VOOR WEERGAVE ---
    feedback_items_data = db.execute("""
        SELECT
            fi.status,
            fi.message,
            fi.suggestion,
            fi.location,
            fi.confidence,
            c.name AS criterion_name,
            c.color AS color, -- Haal kleur op uit criteria tabel
            s.name AS section_name -- Haal sectienaam op uit sections tabel
        FROM feedback_items fi
        JOIN criteria c ON fi.criteria_id = c.id
        LEFT JOIN sections s ON fi.section_id = s.id -- LEFT JOIN omdat section_id NULL kan zijn
        WHERE fi.document_id = ?
        ORDER BY fi.created_at DESC
    """, (document_id,)).fetchall()

    # Bereken statistieken op basis van de NU ECHTE feedback_items_data
    feedback_stats = {
        'violations': sum(1 for f in feedback_items_data if f['status'] == 'error' or f['status'] == 'violation'),
        'warnings': sum(1 for f in feedback_items_data if f['status'] == 'warning'),
        'passed': sum(1 for f in feedback_items_data if f['status'] == 'ok' or f['status'] == 'info')
    }

    # Nu gebruik je de ECHTE data die uit de sectieherkenning komt
    sections_data = recognized_sects # Dit blijft correct

    # Verwijder de gedupliceerde en ongebruikte secties code hieronder.

    return render_template('document_view.html',
                                        document=document,
                                        document_type=document_type,
                                        sections=sections_data,
                                        feedback_items=feedback_items_data,
                                        feedback_stats=feedback_stats)

    # Dummy secties (vervang met echte data van section_recognition)
    # Gebruik de secties uit de DB die gekoppeld zijn aan het documenttype
    db_sections = db.execute("""
        SELECT id, name, identifier, level
        FROM sections
        WHERE document_type_id = ?
        ORDER BY order_index
    """, (document_type['id'],)).fetchall()

    sections_data = []
    for sec in db_sections:
        # Hier kun je de status (found, word_count, confidence) nog toevoegen na analyse
        sections_data.append({
            'id': sec['identifier'],
            'name': sec['name'],
            'level': sec['level'],
            'found': True, # Voor dummy: Stel in dat gevonden
            'word_count': 0, # Vul later met echte data
            'confidence': 0.0, # Vul later met echte data
            'subsections': [] # Subsecties later vullen als structuur complexer wordt
        })

    # Dummy feedback_items (vervang met echte data van generate_feedback, feedback_items tabel)
    # Voorbeeld feedback, haal later uit de feedback_items tabel
    feedback_items_data = [
        {'criterion_name': 'SMART doelstelling', 'section_name': 'Doelstelling', 'status': 'violation',
         'message': 'De doelstelling mist een tijdgebonden aspect.', 'suggestion': 'Voeg een concrete deadline of periode toe.',
         'location': 'Paragraaf 3, regel 2', 'confidence': 0.8, 'color': '#F94144'},
        {'criterion_name': 'Woordtelling Inleiding', 'section_name': 'Inleiding', 'status': 'warning',
         'message': 'De inleiding heeft 350 woorden, minder dan de verwachte 500.', 'suggestion': 'Breid de inleiding uit met meer achtergrondinformatie.',
         'location': 'Sectie Inleiding', 'confidence': 0.6, 'color': '#F9C74F'},
        {'criterion_name': 'APA bronvermelding', 'section_name': 'Literatuurlijst', 'status': 'ok',
         'message': 'De bronvermelding voldoet aan de APA-stijl.', 'suggestion': '',
         'location': 'Sectie Literatuurlijst', 'confidence': 0.9, 'color': '#84A98C'},
        {'criterion_name': 'Persoonlijk taalgebruik', 'section_name': 'Algemeen', 'status': 'warning',
         'message': 'Een persoonlijk schrijfstijl met het gebruik van ik, mij of mijn is niet de bedoeling. Hanteer een zakelijke schrijfstijl zonder persoonlijke voornaamwoorden.', 'suggestion': 'Vermijd persoonlijke voornaamwoorden.',
         'location': 'Hele document', 'confidence': 0.7, 'color': '#FFC107'}
    ]
    
    # Feedback statistieken berekenen uit de dummy data
    feedback_stats = {
        'violations': sum(1 for f in feedback_items_data if f['status'] == 'violation'),
        'warnings': sum(1 for f in feedback_items_data if f['status'] == 'warning'),
        'passed': sum(1 for f in feedback_items_data if f['status'] == 'ok' or f['status'] == 'info') # 'info' kan ook als 'passed' tellen
    }

    return render_template('document_view.html',
                           document=document,
                           document_type=document_type,
                           sections=sections_data,
                           feedback_items=feedback_items_data,
                           feedback_stats=feedback_stats)

# --- Criteria Management Routes (AANGEPAST AAN JOUW SCHEMA) ---
@app.route('/criteria')
def list_criteria():
    """Overzicht van alle criteria."""
    conn = get_db()
    # Selecteer alle kolommen uit de criteria tabel
    criteria = conn.execute('''
        SELECT c.*, o.name AS organization_name, dt.name AS document_type_name
        FROM criteria c
        LEFT JOIN organizations o ON c.organization_id = o.id
        LEFT JOIN document_types dt ON c.document_type_id = dt.id
        ORDER BY c.name
    ''').fetchall()
    conn.close()
    return render_template('criteria_list.html', criteria=criteria)

@app.route('/criteria/add', methods=('GET', 'POST'))
def add_criterion():
    """Formulier om een nieuw criterium toe te voegen."""
    conn = get_db()
    organizations = conn.execute('SELECT id, name FROM organizations').fetchall()
    document_types = conn.execute('SELECT id, name FROM document_types').fetchall()

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
        max_mentions_per = request.form.get('max_mentions_per', type=int)
        frequency_unit = request.form.get('frequency_unit')

        # Converteer naar None als string leeg is, voor INTEGER en FOREIGN KEY velden
        org_id = int(org_id) if org_id else None
        doc_type_id = int(doc_type_id) if doc_type_id else None
        max_mentions_per = int(max_mentions_per) if max_mentions_per is not None else 0

        if not name:
            flash('Criterium naam is verplicht!', 'error')
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
                flash(f'Fout bij toevoegen: {e}. Controleer unieke velden en FKs.', 'error')
            except Exception as e:
                flash(f'Er is een onverwachte fout opgetreden: {e}', 'error')
            finally:
                conn.close()
    
    # Sluit de connectie voor GET request of POST met fout
    if conn:
        conn.close()
    
    return render_template('add_criterion.html', 
                           organizations=organizations, 
                           document_types=document_types,
                           # Pass form data back to pre-fill on error
                           form_data=request.form)

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
        max_mentions_per = request.form.get('max_mentions_per', type=int)
        frequency_unit = request.form.get('frequency_unit')

        org_id = int(org_id) if org_id else None
        doc_type_id = int(doc_type_id) if doc_type_id else None
        max_mentions_per = int(max_mentions_per) if max_mentions_per is not None else 0

        if not name:
            flash('Criterium naam is verplicht!', 'error')
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
                flash(f'Fout bij bijwerken: {e}. Controleer unieke velden en FKs.', 'error')
            except Exception as e:
                flash(f'Er is een onverwachte fout opgetreden: {e}', 'error')
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
        flash(f'Fout bij verwijderen van criterium: {e}', 'error')
    finally:
        conn.close()
    return redirect(url_for('list_criteria'))


# --- Flask Run Command ---
if __name__ == '__main__':
    # Normaal run je Flask met 'flask run' vanuit je terminal.
    # Dit blok is handig als je liever 'python main.py' uitvoert.
    # Let op: debug=True NIET gebruiken in productie!
    app.run(debug=True)