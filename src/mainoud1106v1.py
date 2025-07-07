# ... (andere imports)
#!/usr/bin/env python3
"""
Werkende Feedback Tool - Deployment versie
"""
import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template_string, redirect, url_for, flash, request


# === FLASK APPLICATIE SETUP ===
app = Flask(__name__)
app.config['SECRET_KEY'] = 'feedback-tool-secret-key-2024'
app.config['DATABASE'] = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'feedback_tool.db') # Jouw huidige pad


# === HTML TEMPLATE MET GHIBLI KLEUREN ===
BASE_TEMPLATE = '''<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Feedback Tool{% endblock %}</title>
    <style>
        /* === RESET EN BASIS STYLING === */
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background: linear-gradient(135deg, #F8F9FA 0%, #E9ECEF 100%); 
            color: #2B2D42; 
            min-height: 100vh; 
        }

        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }

        /* === HEADER STYLING (GHIBLI KLEUREN) === */
        .header { 
            background: linear-gradient(135deg, #4D908E 0%, #52796F 100%); 
            color: white; 
            padding: 20px; 
            border-radius: 15px; 
            margin-bottom: 30px; 
            box-shadow: 0 4px 15px rgba(77, 144, 142, 0.3); 
        }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; }

        /* === NAVIGATIE === */
        .nav-breadcrumb { 
            background: rgba(255,255,255,0.1); 
            padding: 10px 15px; 
            border-radius: 8px; 
            margin-top: 15px; 
        }
        .nav-breadcrumb a { color: white; text-decoration: none; opacity: 0.8; }
        .nav-breadcrumb a:hover { opacity: 1; }

        /* === CARDS === */
        .card { 
            background: white; 
            border-radius: 15px; 
            padding: 25px; 
            margin-bottom: 20px; 
            box-shadow: 0 4px 15px rgba(0,0,0,0.1); 
            border: 1px solid #E9ECEF; 
        }

        /* === BUTTONS (GHIBLI KLEUREN) === */
        .btn { 
            background: #4D908E; 
            color: white; 
            padding: 12px 20px; 
            border: none; 
            border-radius: 8px; 
            text-decoration: none; 
            display: inline-block; 
            margin-right: 10px; 
            margin-bottom: 10px; 
            cursor: pointer; 
            font-size: 16px; 
            transition: all 0.3s ease; 
        }
        .btn:hover { 
            background: #52796F; 
            transform: translateY(-2px); 
            box-shadow: 0 4px 10px rgba(77, 144, 142, 0.3); 
        }
        .btn-secondary { background: #F6BD60; color: #2B2D42; }
        .btn-secondary:hover { background: #F4A261; }
        .btn-danger { background: #F94144; }
        .btn-danger:hover { background: #D90429; }
        .btn-success { background: #84A98C; }
        .btn-success:hover { background: #6A994E; }

        /* === FORMULIEREN === */
        .form-group { margin-bottom: 20px; }
        .form-group label { 
            display: block; 
            margin-bottom: 8px; 
            font-weight: 600; 
            color: #2B2D42; 
        }
        .form-group input, .form-group textarea, .form-group select { 
            width: 100%; 
            padding: 12px; 
            border: 2px solid #E9ECEF; 
            border-radius: 8px; 
            font-size: 16px; 
            transition: border-color 0.3s ease; 
        }
        .form-group input:focus, .form-group textarea:focus, .form-group select:focus { 
            outline: none; 
            border-color: #4D908E; 
            box-shadow: 0 0 0 3px rgba(77, 144, 142, 0.1); 
        }
        .form-group textarea { height: 120px; resize: vertical; }

        /* === TABELLEN === */
        .table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        .table th, .table td { padding: 12px; text-align: left; border-bottom: 1px solid #E9ECEF; }
        .table th { background: #F8F9FA; font-weight: 600; color: #2B2D42; }
        .table tr:hover { background: #F8F9FA; }

        /* === BADGES === */
        .badge { 
            display: inline-block; 
            padding: 4px 8px; 
            border-radius: 4px; 
            font-size: 0.8em; 
            font-weight: 600; 
        }
        .badge-success { background: #84A98C; color: white; }
        .badge-warning { background: #F9C74F; color: #2B2D42; }

        /* === LEGE STAAT === */
        .empty-state { text-align: center; padding: 60px 20px; color: #6C757D; }
        .empty-state h3 { margin-bottom: 10px; color: #495057; }

        /* === FLASH MESSAGES === */
        .flash-messages { margin-bottom: 20px; }
        .flash-success { 
            background: #84A98C; 
            color: white; 
            padding: 15px; 
            border-radius: 8px; 
            margin-bottom: 10px; 
        }
        .flash-error { 
            background: #F94144; 
            color: white; 
            padding: 15px; 
            border-radius: 8px; 
            margin-bottom: 10px; 
        }
    </style>
</head>
<body>
    <div class="container">
        {% block content %}{% endblock %}
    </div>
</body>
</html>'''

def get_db_connection():
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        conn.row_factory = sqlite3.Row
        return conn
    except:
        return None

def init_database():
    conn = None # Initialiseer conn als None voor het geval get_db_connection faalt
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()

            # CREATE TABLE statement met alle kolommen
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS criteria (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    category TEXT DEFAULT 'Algemeen',
                    color TEXT DEFAULT '#F94144',
                    is_enabled BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    max_mentions_per INTEGER DEFAULT 0,
                    frequency_unit TEXT,
                    fixed_feedback_text TEXT,
                    instruction_video_link TEXT
                )
            ''')

            # Voeg ALTER TABLE statements toe voor het geval de tabel al bestaat
            # Deze worden in hun eigen try/except blokken geplaatst om fouten te voorkomen als de kolom al bestaat.
            try:
                cursor.execute("ALTER TABLE criteria ADD COLUMN max_mentions_per INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute("ALTER TABLE criteria ADD COLUMN frequency_unit TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute("ALTER TABLE criteria ADD COLUMN fixed_feedback_text TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute("ALTER TABLE criteria ADD COLUMN instruction_video_link TEXT")
            except sqlite3.OperationalError:
                pass

            # Commit de schema-wijzigingen
            conn.commit()

            # Controleer of er al initiële data is, en voeg toe indien nodig
            cursor.execute('SELECT COUNT(*) FROM criteria')
            if cursor.fetchone()[0] == 0:
                print("Initialiseren met standaard criteria...")

            # Update de voorbeelddata om alle nieuwe kolommen mee te nemen
            # Volgorde: (name, description, category, color, is_enabled, max_mentions_per, frequency_unit, fixed_feedback_text, instruction_video_link)
            voorbeelddata = [
                    ('Handelingsprobleem SMART', 'Het handelingsprobleem moet SMART geformuleerd zijn', 'Inhoudelijk', '#F94144', 1, 1, 'document', '', ''),
                    ('Hoofdvraag aansluiting', 'De hoofdvraag moet aansluiten bij het handelingsprobleem', 'Inhoudelijk', '#F94144', 1, 0, None, '', ''), # None voor NULL
                    ('Bronvermelding correct', 'Alle bronnen moeten correct vermeld zijn volgens APA-stijl', 'Referenties', '#4D908E', 1, 0, None, '', ''),
                    ('Structuur logisch', 'De documentstructuur moet logisch opgebouwd zijn', 'Structuur', '#84A98C', 1, 0, None, '', ''),
                # Jouw specifieke criterium 'Persoonlijk taalgebruik' hier toevoegen:
                    ('Persoonlijk taalgebruik', 'Een persoonlijk schrijfstijl met het gebruik van ik, mij of mijn is niet de bedoeling. Hanteer een zakelijke schrijfstijl zonder persoonlijke voornaamwoorden.', 'Taal', '#FFC107', 1, 1, 'document', 'Een persoonlijk schrijfstijl met het gebruik van ik, mij of mijn is niet de bedoeling. Hanteer een zakelijke schrijfstijl zonder persoonlijke voornaamwoorden.', 'https://www.youtube.com/watch?v=dQw4w9WgXcQ')
            ]

            for naam, beschrijving, categorie, kleur, is_actief, max_vermeldingen, frequentie_eenheid, vaste_feedback, video_link in voorbeelddata:
                cursor.execute(
                    'INSERT INTO criteria (name, description, category, color, is_enabled, max_mentions_per, frequency_unit, fixed_feedback_text, instruction_video_link) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (naam, beschrijving, categorie, kleur, is_actief, max_vermeldingen, frequentie_eenheid, vaste_feedback, video_link)
                )
            conn.commit() # Deze commit is belangrijk na de inserts
            print("Standaard criteria toegevoegd.")
            return True # Alles is succesvol uitgevoerd
        else:
            print("Geen database connectie beschikbaar in init_database.")
            return False

    except Exception as e:
        # Dit blok vangt eventuele fouten tijdens de database-operaties
        print(f"Fout bij initialiseren database: {e}")
        return False # Fout opgetreden

    finally:
        # Dit blok wordt ALTIJD uitgevoerd, ongeacht of er een fout optrad of niet.
        # Hier sluiten we de connectie. Geen 'return' hier, want dat zou vorige returns overschrijven.
        if conn: # Zorg ervoor dat conn niet None is voordat je probeert te sluiten
            conn.close()


# === ROUTES (URL HANDLERS) ===

@app.route('/')
def index():
    """Hoofdpagina van de Feedback Tool"""
    return render_template_string(BASE_TEMPLATE + '''
        <div class="header">
            <h1>🎯 Feedback Tool</h1>
            <p>Beheerinterface voor criteria en documentbeoordeling</p>
        </div>
        
        <div class="card">
            <h3>📋 Criteria Beheer</h3>
            <p>Voeg criteria toe, bewerk bestaande criteria en beheer beoordelingsregels.</p>
            <a href="/criteria" class="btn">Beheer Criteria</a>
        </div>
        
        <div class="card">
            <h3>ℹ️ Informatie</h3>
            <p><strong>Status:</strong> <span class="badge badge-success">Actief</span></p>
            <p><strong>Versie:</strong> Complete interface versie</p>
            <p><strong>Database:</strong> SQLite (lokaal bestand)</p>
        </div>
    ''')

@app.route('/criteria')
def criteria_list():
    """Overzicht van alle criteria"""
    conn = get_db_connection()
    criteria = []
    
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM criteria ORDER BY created_at DESC')
            criteria = cursor.fetchall()
            conn.close()
        except Exception as e:
            print(f"Fout bij ophalen criteria: {e}")
            conn.close()
    
    return render_template_string(BASE_TEMPLATE + '''
        <div class="header">
            <h1>📋 Criteria Beheer</h1>
            <p>Beheer alle criteria voor documentbeoordeling</p>
            <div class="nav-breadcrumb">
                <a href="/">Home</a> > Criteria Beheer
            </div>
        </div>
        
        <div class="card">
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    <div class="flash-messages">
                        {% for category, message in messages %}
                            <div class="flash-{{ category }}">{{ message }}</div>
                        {% endfor %}
                    </div>
                {% endif %}
            {% endwith %}
            
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h3>Alle Criteria</h3>
                <div>
                    <a href="/criteria/add" class="btn">+ Nieuw Criterium</a>
                </div>
            </div>
            
            {% if criteria %}
                <table class="table">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Naam</th>
                            <th>Beschrijving</th>
                            <th>Categorie</th>
                            <th>Max. Vermeldingen</th>
                            <th>Frequentie-eenheid</th>
                            <th>Vaste Feedback</th>
                            <th>Instructie Video</th>
                            <th>Status</th>
                            <th>Acties</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for criterion in criteria %}
                        <tr>
                            <td>{{ criterion.id }}</td>
                            <td><strong>{{ criterion.name }}</strong></td>
                            <td>{{ criterion.description or 'Geen beschrijving' }}</td>
                            <td>
                                <span class="badge" style="background-color: {{ criterion.color }}; color: white;">
                                    {{ criterion.category }}
                                </span>                                                           
                            </td>
                            <td>{{ criterion.max_mentions_per }}</td>
                            <td>{{ criterion.frequency_unit }}</td>
                            <td>
                                {% if criterion.fixed_feedback_text %}
                                    <span title="{{ criterion.fixed_feedback_text }}">Ja (hover)</span>
                                {% else %}
                                    Nee
                                {% endif %}
                            </td>
                            <td>
                                {% if criterion.instruction_video_link %}
                                    <a href="{{ criterion.instruction_video_link }}" target="_blank" class="btn" style="padding: 4px 8px; font-size: 12px; margin-right: 0;">Bekijk</a>
                                {% else %}
                                    Geen
                                {% endif %}
                            </td>
                            <td>
                                {% if criterion.is_enabled %}
                                    <span class="badge badge-success">Actief</span>
                                {% else %}
                                    <span class="badge badge-warning">Inactief</span>
                                {% endif %}
                            </td>
                            <td>
                                <a href="/criteria/edit/{{ criterion.id }}" class="btn" style="padding: 6px 12px; font-size: 14px;">✏️ Bewerken</a>
                                <a href="/criteria/delete/{{ criterion.id }}" class="btn btn-danger" style="padding: 6px 12px; font-size: 14px;"
                                   onclick="return confirm('Weet u zeker dat u dit criterium wilt verwijderen?')">🗑️ Verwijderen</a>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            {% else %}
                <div class="empty-state">
                    <h3>Geen criteria gevonden</h3>
                    <p>Er zijn nog geen criteria toegevoegd.</p>
                    <a href="/criteria/add" class="btn">+ Eerste Criterium Toevoegen</a>
                </div>
            {% endif %}
        </div>
    ''', criteria=criteria)

@app.route('/criteria/add', methods=['GET', 'POST'])
def criteria_add():
    """Toevoegen van een nieuw criterium."""
    conn = get_db_connection()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', 'Algemeen')
        color = request.form.get('color', '#F94144')
        is_enabled = 1 if request.form.get('is_enabled') else 0
        
        # NIEUW: Haal de waarden van de nieuwe velden op
        max_mentions_per = int(request.form.get('max_mentions_per', 0))
        frequency_unit = request.form.get('frequency_unit', 'document')
        fixed_feedback_text = request.form.get('fixed_feedback_text', '').strip()
        instruction_video_link = request.form.get('instruction_video_link', '').strip()

        if name:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO criteria (name, description, category, color, is_enabled, max_mentions_per, frequency_unit, fixed_feedback_text, instruction_video_link) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (name, description, category, color, is_enabled, max_mentions_per, frequency_unit, fixed_feedback_text, instruction_video_link)
                )
                conn.commit()
                flash('Criterium succesvol toegevoegd!', 'success')
                return redirect(url_for('criteria_list'))
            except Exception as e:
                flash(f'Fout bij toevoegen van criterium: {e}', 'error')
                print(f"Database error: {e}") # Print de fout voor debugging
        else:
            flash('Naam is verplicht.', 'error')
        conn.close() # Sluit de connectie na gebruik in POST
        # Indien er een fout is, render opnieuw het formulier met de ingevoerde data
        # Dit is de 'GET' return, dus de data wordt niet doorgegeven, maar we tonen de flash message
        # De gebruiker moet opnieuw invullen
    
    # GET request of POST met fout (formulier opnieuw tonen)
    conn.close() # Sluit de connectie voor GET request
    return render_template_string(BASE_TEMPLATE + '''
    <div class="header">
        <h1>➕ Nieuw Criterium Toevoegen</h1>
        <p>Voeg een nieuw beoordelingscriterium toe aan de lijst.</p>
        <div class="nav-breadcrumb">
            <a href="/">Home</a> > <a href="/criteria">Criteria Beheer</a> > Nieuw Criterium
        </div>
    </div>

    <div class="card">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <div class="flash-messages">
                    {% for category, message in messages %}
                        <div class="flash-{{ category }}">{{ message }}</div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}

        <form method="POST">
            <div class="form-group">
                <label for="name">Naam van het criterium *</label>
                <input type="text" id="name" name="name" required placeholder="Bijv. Correcte spelling">
            </div>
            
            <div class="form-group">
                <label for="description">Beschrijving</label>
                <textarea id="description" name="description" placeholder="Een duidelijke beschrijving van het criterium."></textarea>
            </div>
            
            <div class="form-group">
                <label for="category">Categorie</label>
                <select id="category" name="category">
                    <option value="Algemeen">Algemeen</option>
                    <option value="Tekstueel">Tekstueel</option>
                    <option value="Structuur">Structuur</option>
                    <option value="Inhoudelijk">Inhoudelijk</option>
                    <option value="Opmaak">Opmaak</option>
                    <option value="Referenties">Referenties</option>
                </select>
            </div>
            
            <div class="form-group">
                <label for="color">Kleur</label>
                <select id="color" name="color">
                    <option value="#F94144">🔴 Rood (Kritiek)</option>
                    <option value="#F9C74F">🟡 Geel (Waarschuwing)</option>
                    <option value="#84A98C">🟢 Groen (Info)</option>
                    <option value="#4D908E">🔵 Blauw (Structuur)</option>
                </select>
            </div>
            
            <div class="form-group">
                <label>
                    <input type="checkbox" name="is_enabled" checked> 
                    Criterium ingeschakeld (standaard aan)
                </label>
            </div>

            <div class="form-group">
                <label for="max_mentions_per">Max. aantal vermeldingen per eenheid (0 voor onbeperkt)</label>
                <input type="number" id="max_mentions_per" name="max_mentions_per" value="0" min="0">
            </div>
            
            <div class="form-group">
                <label for="frequency_unit">Frequentie-eenheid</label>
                <select id="frequency_unit" name="frequency_unit">
                    <option value="document">Document</option>
                    <option value="page">Pagina (nog niet geïmplementeerd)</option>
                    <option value="section">Sectie (nog niet geïmplementeerd)</option>
                </select>
            </div>

            <div class="form-group">
                <label for="fixed_feedback_text">Vaste feedback tekst (optioneel, indien niet AI-gegenereerd)</label>
                <textarea id="fixed_feedback_text" name="fixed_feedback_text" 
                          placeholder="Voer hier een vaste feedback tekst in die altijd wordt gebruikt voor dit criterium."></textarea>
            </div>

            <div class="form-group">
                <label for="instruction_video_link">Instructie video link (optioneel)</label>
                <input type="url" id="instruction_video_link" name="instruction_video_link" 
                            placeholder="Link naar een instructievideo (bijv. YouTube)">
            </div>
            <div style="margin-top: 30px;">
                <button type="submit" class="btn btn-success">➕ Criterium Toevoegen</button>
                <a href="/criteria" class="btn btn-secondary">❌ Annuleren</a>
            </div>
        </form>
    </div>
    ''')

@app.route('/criteria/edit/<int:criterion_id>', methods=['GET', 'POST'])
def criteria_edit(criterion_id):
    """Criterium bewerken"""
    conn = get_db_connection()
    if not conn:
        flash('Database verbinding mislukt.', 'error')
        return redirect(url_for('criteria_list'))
    
    try:
        cursor = conn.cursor()
        
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            category = request.form.get('category', 'Algemeen')
            color = request.form.get('color', '#F94144')
            is_enabled = 1 if request.form.get('is_enabled') else 0
            
# NIEUW: Haal de waarden van de nieuwe velden op
            max_mentions_per = int(request.form.get('max_mentions_per', 0))
            frequency_unit = request.form.get('frequency_unit', 'document')
            fixed_feedback_text = request.form.get('fixed_feedback_text', '').strip()
            instruction_video_link = request.form.get('instruction_video_link', '').strip()

        if name:
            # UPDATE HIER: Voeg alle nieuwe kolommen toe aan de UPDATE statement
            cursor.execute(
                'UPDATE criteria SET name=?, description=?, category=?, color=?, is_enabled=?, max_mentions_per=?, frequency_unit=?, fixed_feedback_text=?, instruction_video_link=? WHERE id=?',
                (name, description, category, color, is_enabled, max_mentions_per, frequency_unit, fixed_feedback_text, instruction_video_link, criterion_id)
            )
            conn.commit()
            conn.close()
            flash('Criterium succesvol bijgewerkt!', 'success')
            return redirect(url_for('criteria_list'))
        else:
            flash('Naam is verplicht.', 'error')
        
        # Haal criterium gegevens op
        cursor.execute('SELECT * FROM criteria WHERE id=?', (criterion_id,))
        criterion = cursor.fetchone()
        
        if not criterion:
            conn.close()
            flash('Criterium niet gevonden.', 'error')
            return redirect(url_for('criteria_list'))
        
        conn.close()
        
        return render_template_string(BASE_TEMPLATE + '''
        {% block title %}Criterium Bewerken - Feedback Tool{% endblock %}
        {% block content %}
            <div class="header">
                <h1>✏️ Criterium Bewerken</h1>
                <p>Bewerk het beoordelingscriterium</p>
                <div class="nav-breadcrumb">
                    <a href="/">Home</a> > <a href="/criteria">Criteria</a> > Bewerken
                </div>
            </div>
            
            <div class="card">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        <div class="flash-messages">
                            {% for category, message in messages %}
                                <div class="flash-{{ category }}">{{ message }}</div>
                            {% endfor %}
                        </div>
                    {% endif %}
                {% endwith %}
                
                <form method="POST">
                    <div class="form-group">
                        <label for="name">Naam van het criterium *</label>
                        <input type="text" id="name" name="name" required value="{{ criterion.name }}">
                    </div>
                    
                    <div class="form-group">
                        <label for="description">Beschrijving</label>
                        <textarea id="description" name="description">{{ criterion.description or '' }}</textarea>
                    </div>
                    
                    <div class="form-group">
                        <label for="category">Categorie</label>
                        <select id="category" name="category">
                            <option value="Algemeen" {% if criterion.category == 'Algemeen' %}selected{% endif %}>Algemeen</option>
                            <option value="Tekstueel" {% if criterion.category == 'Tekstueel' %}selected{% endif %}>Tekstueel</option>
                            <option value="Structuur" {% if criterion.category == 'Structuur' %}selected{% endif %}>Structuur</option>
                            <option value="Inhoudelijk" {% if criterion.category == 'Inhoudelijk' %}selected{% endif %}>Inhoudelijk</option>
                            <option value="Opmaak" {% if criterion.category == 'Opmaak' %}selected{% endif %}>Opmaak</option>
                            <option value="Referenties" {% if criterion.category == 'Referenties' %}selected{% endif %}>Referenties</option>
                        </select>
                    </div>
                    
                    <div class="form-group">
                        <label for="color">Kleur</label>
                        <select id="color" name="color">
                            <option value="#F94144" {% if criterion.color == '#F94144' %}selected{% endif %}>🔴 Rood (Kritiek)</option>
                            <option value="#F9C74F" {% if criterion.color == '#F9C74F' %}selected{% endif %}>🟡 Geel (Waarschuwing)</option>
                            <option value="#84A98C" {% if criterion.color == '#84A98C' %}selected{% endif %}>🟢 Groen (Info)</option>
                            <option value="#4D908E" {% if criterion.color == '#4D908E' %}selected{% endif %}>🔵 Blauw (Structuur)</option>
                        </select>
                    </div>


                    <div class="form-group">
                        <label for="max_mentions_per">Max. aantal vermeldingen per eenheid (0 voor onbeperkt)</label>
                        <input type="number" id="max_mentions_per" name="max_mentions_per" value="{{ criterion.max_mentions_per }}" min="0">
                    </div>
                    
                    <div class="form-group">
                        <label for="frequency_unit">Frequentie-eenheid</label>
                        <select id="frequency_unit" name="frequency_unit">
                            <option value="document" {% if criterion.frequency_unit == 'document' %}selected{% endif %}>Document</option>
                            <option value="page" {% if criterion.frequency_unit == 'page' %}selected{% endif %}>Pagina (nog niet geïmplementeerd)</option>
                            <option value="section" {% if criterion.frequency_unit == 'section' %}selected{% endif %}>Sectie (nog niet geïmplementeerd)</option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label for="fixed_feedback_text">Vaste feedback tekst (optioneel, indien niet AI-gegenereerd)</label>
                        <textarea id="fixed_feedback_text" name="fixed_feedback_text" 
                                placeholder="Voer hier een vaste feedback tekst in die altijd wordt gebruikt voor dit criterium.">{{ criterion.fixed_feedback_text or '' }}</textarea>
                    </div>

                    <div class="form-group">
                        <label for="instruction_video_link">Instructie video link (optioneel)</label>
                        <input type="url" id="instruction_video_link" name="instruction_video_link" 
                                    value="{{ criterion.instruction_video_link or '' }}"
                                    placeholder="Link naar een instructievideo (bijv. YouTube)">
                    </div>
                  
                    <div class="form-group">
                        <label>
                            <input type="checkbox" name="is_enabled" {% if criterion.is_enabled %}checked{% endif %}> 
                            Criterium ingeschakeld
                        </label>
                    </div>
                    
                    <div style="margin-top: 30px;">
                        <button type="submit" class="btn btn-success">💾 Wijzigingen Opslaan</button>
                        <a href="/criteria" class="btn btn-secondary">❌ Annuleren</a>
                    </div>
                </form>
            </div>
        {% endblock %}
        ''', criterion=criterion)
        
    except Exception as e:
        print(f"Fout bij bewerken: {e}")
        flash('Fout bij bewerken van criterium.', 'error')
        conn.close()
        return redirect(url_for('criteria_list'))

@app.route('/criteria/delete/<int:criterion_id>')
def criteria_delete(criterion_id):
    """Criterium verwijderen"""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM criteria WHERE id=?', (criterion_id,))
            conn.commit()
            conn.close()
            flash('Criterium succesvol verwijderd!', 'success')
        except Exception as e:
            print(f"Fout bij verwijderen: {e}")
            flash('Fout bij verwijderen van criterium.', 'error')
            conn.close()
    
    return redirect(url_for('criteria_list'))
    
if __name__ == '__main__':
    init_database()
    app.run(host='0.0.0.0', port=5000, debug=False)

@app.cli.command('init-db')
def init_db_command():
    """Initialiseert de database."""
    init_database()
    print('Database geïnitialiseerd.')

# OPTIONEEL: Als je de database altijd wilt initialiseren bij de eerste keer draaien,
# kun je ook de volgende regel toevoegen buiten elke functie:
# with app.app_context():
#     init_database()
# Echter, het CLI-commando is vaak veiliger voor productieomgevingen.
