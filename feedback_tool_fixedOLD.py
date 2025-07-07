#!/usr/bin/env python3
"""
Werkende Feedback Tool met alle criteria beheer functionaliteit
"""
import os
import sqlite3
import json
from datetime import datetime
from flask import Flask, render_template_string, redirect, url_for, flash, request

app = Flask(__name__)
app.config['SECRET_KEY'] = 'feedback-tool-secret-key-2024'
app.config['DATABASE'] = '/home/ubuntu/feedback_tool/database/feedback_tool.db'

os.makedirs(os.path.dirname(app.config['DATABASE']), exist_ok=True)

def get_db_connection():
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        conn.row_factory = sqlite3.Row
        return conn
    except:
        return None

def init_database():
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS document_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_type_id INTEGER,
                name TEXT NOT NULL,
                identifier TEXT,
                parent_id INTEGER,
                level INTEGER DEFAULT 1,
                alternative_names TEXT,
                pattern TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (document_type_id) REFERENCES document_types (id),
                FOREIGN KEY (parent_id) REFERENCES sections (id))''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS criteria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                error_message TEXT,
                instruction_link TEXT,
                category TEXT DEFAULT 'Algemeen',
                color TEXT DEFAULT '#F94144',
                rule_type TEXT DEFAULT 'Tekstueel',
                application_scope TEXT DEFAULT 'specific_sections',
                max_occurrences_per TEXT DEFAULT 'paragraph',
                is_enabled BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS criteria_section_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                criteria_id INTEGER,
                section_id INTEGER,
                document_type_id INTEGER,
                is_excluded BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (criteria_id) REFERENCES criteria (id),
                FOREIGN KEY (section_id) REFERENCES sections (id),
                FOREIGN KEY (document_type_id) REFERENCES document_types (id))''')
            
            cursor.execute('SELECT COUNT(*) FROM document_types')
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO document_types (name, description) VALUES (?, ?)", 
                             ('Plan van Aanpak', 'Plan van Aanpak documenten voor HBO Rechten'))
                cursor.execute("INSERT INTO document_types (name, description) VALUES (?, ?)", 
                             ('Onderzoeksrapport', 'Onderzoeksrapport documenten voor HBO Rechten'))
                
                sections_data = [
                    (1, 'Hoofdstuk 1: Inleiding', 'H1', None, 1, 'H1,Hoofdstuk 1,Inleiding', ''),
                    (1, 'Handelingsprobleem', 'H1.2', 1, 2, '1.2,H1.2,Handelingsprobleem,Probleemstelling', ''),
                    (1, 'Hoofdvraag en deelvragen', 'H1.3', 1, 2, '1.3,H1.3,Hoofdvraag,Deelvragen', ''),
                    (1, 'Hoofdstuk 2: Juridische context', 'H2', None, 1, 'H2,Hoofdstuk 2,Juridische context', ''),
                    (1, 'Hoofdstuk 3: Methoden', 'H3', None, 1, 'H3,Hoofdstuk 3,Methoden,Methodologie', ''),
                ]
                
                for section_data in sections_data:
                    cursor.execute('''INSERT INTO sections (document_type_id, name, identifier, parent_id, level, alternative_names, pattern)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''', section_data)
                
                criteria_data = [
                    ('Handelingsprobleem SMART', 'Het handelingsprobleem moet SMART geformuleerd zijn', 
                     'Het handelingsprobleem is niet SMART geformuleerd', 'https://inholland.nl/smart-formuleren',
                     'Inhoudelijk', '#F94144', 'Inhoud', 'specific_sections', 'paragraph', 1),
                    ('Hoofdvraag aansluiting', 'De hoofdvraag moet aansluiten bij het handelingsprobleem',
                     'De hoofdvraag sluit niet aan bij het handelingsprobleem', '',
                     'Inhoudelijk', '#F94144', 'Inhoud', 'specific_sections', 'paragraph', 1),
                ]
                
                for criteria in criteria_data:
                    cursor.execute('''INSERT INTO criteria (name, description, error_message, instruction_link, category, color, rule_type, application_scope, max_occurrences_per, is_enabled)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', criteria)
                
                cursor.execute('INSERT INTO criteria_section_mappings (criteria_id, section_id, document_type_id) VALUES (1, 2, 1)')
                cursor.execute('INSERT INTO criteria_section_mappings (criteria_id, section_id, document_type_id) VALUES (2, 3, 1)')
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Database error: {e}")
            conn.close()
            return False
    return False

BASE_TEMPLATE = '''<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Feedback Tool{% endblock %}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #F8F9FA 0%, #E9ECEF 100%); color: #2B2D42; min-height: 100vh; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { background: linear-gradient(135deg, #4D908E 0%, #52796F 100%); color: white; padding: 20px; border-radius: 15px; margin-bottom: 30px; box-shadow: 0 4px 15px rgba(77, 144, 142, 0.3); }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; }
        .nav-breadcrumb { background: rgba(255,255,255,0.1); padding: 10px 15px; border-radius: 8px; margin-top: 15px; }
        .nav-breadcrumb a { color: white; text-decoration: none; opacity: 0.8; }
        .nav-breadcrumb a:hover { opacity: 1; }
        .card { background: white; border-radius: 15px; padding: 25px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); border: 1px solid #E9ECEF; }
        .grid { display: grid; gap: 20px; }
        .grid-2 { grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }
        .btn { background: #4D908E; color: white; padding: 12px 20px; border: none; border-radius: 8px; text-decoration: none; display: inline-block; margin-right: 10px; margin-bottom: 10px; cursor: pointer; font-size: 16px; transition: all 0.3s ease; }
        .btn:hover { background: #52796F; transform: translateY(-2px); box-shadow: 0 4px 10px rgba(77, 144, 142, 0.3); }
        .btn-secondary { background: #F6BD60; color: #2B2D42; }
        .btn-secondary:hover { background: #F4A261; }
        .btn-danger { background: #F94144; }
        .btn-danger:hover { background: #D90429; }
        .btn-success { background: #84A98C; }
        .btn-success:hover { background: #6A994E; }
        .form-group { margin-bottom: 20px; }
        .form-group label { display: block; margin-bottom: 8px; font-weight: 600; color: #2B2D42; }
        .form-group input, .form-group textarea, .form-group select { width: 100%; padding: 12px; border: 2px solid #E9ECEF; border-radius: 8px; font-size: 16px; transition: border-color 0.3s ease; }
        .form-group input:focus, .form-group textarea:focus, .form-group select:focus { outline: none; border-color: #4D908E; box-shadow: 0 0 0 3px rgba(77, 144, 142, 0.1); }
        .form-group textarea { height: 120px; resize: vertical; }
        .table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        .table th, .table td { padding: 12px; text-align: left; border-bottom: 1px solid #E9ECEF; }
        .table th { background: #F8F9FA; font-weight: 600; color: #2B2D42; }
        .table tr:hover { background: #F8F9FA; }
        .badge { display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 0.8em; font-weight: 600; }
        .badge-success { background: #84A98C; color: white; }
        .badge-warning { background: #F9C74F; color: #2B2D42; }
        .empty-state { text-align: center; padding: 60px 20px; color: #6C757D; }
        .empty-state h3 { margin-bottom: 10px; color: #495057; }
        .flash-messages { margin-bottom: 20px; }
        .flash-success { background: #84A98C; color: white; padding: 15px; border-radius: 8px; margin-bottom: 10px; }
        .flash-error { background: #F94144; color: white; padding: 15px; border-radius: 8px; margin-bottom: 10px; }
        .checkbox-group { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; }
        .checkbox-item { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: #F8F9FA; border-radius: 6px; border: 1px solid #E9ECEF; }
        .checkbox-item input[type="checkbox"] { width: auto; }
    </style>
</head>
<body>
    <div class="container">
        {% block content %}{% endblock %}
    </div>
</body>
</html>'''

@app.route('/')
def index():
    return render_template_string(BASE_TEMPLATE + '''
    {% block title %}Feedback Tool - Beheerinterface{% endblock %}
    {% block content %}
        <div class="header">
            <h1>🎯 Feedback Tool</h1>
            <p>Beheerinterface voor criteria, secties en documenttypes</p>
        </div>
        <div class="grid grid-2">
            <div class="card">
                <h3>📋 Criteria Beheer</h3>
                <p>Voeg criteria toe, bewerk bestaande criteria en koppel ze aan documenttypes en secties.</p>
                <a href="/criteria" class="btn">Beheer Criteria</a>
            </div>
            <div class="card">
                <h3>📑 Sectie Beheer</h3>
                <p>Beheer documentstructuren, secties en hun hiërarchische relaties.</p>
                <a href="/sections" class="btn">Beheer Secties</a>
            </div>
        </div>
    {% endblock %}
    ''')

@app.route('/criteria')
def criteria_list():
    conn = get_db_connection()
    criteria = []
    document_types = []
    selected_doc_type = request.args.get('doc_type', '1')
    
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM document_types ORDER BY name')
            document_types = cursor.fetchall()
            cursor.execute('SELECT * FROM criteria ORDER BY created_at DESC')
            criteria = cursor.fetchall()
            conn.close()
        except Exception as e:
            print(f"Error: {e}")
            conn.close()
    
    return render_template_string(BASE_TEMPLATE + '''
    {% block title %}Criteria Beheer - Feedback Tool{% endblock %}
    {% block content %}
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
                <div>
                    <label for="doc_type">Documenttype:</label>
                    <select id="doc_type" style="margin-left: 10px; padding: 8px;">
                        {% for dt in document_types %}
                        <option value="{{ dt.id }}">{{ dt.name }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div>
                    <a href="/criteria/add" class="btn">+ Nieuw Criterium</a>
                    <a href="/criteria/import" class="btn btn-secondary">📊 Importeren</a>
                    <a href="/criteria/export" class="btn btn-secondary">📤 Exporteren</a>
                </div>
            </div>
            
            {% if criteria %}
                <table class="table">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Beschrijving</th>
                            <th>Categorie</th>
                            <th>Status</th>
                            <th>Acties</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for criterion in criteria %}
                        <tr>
                            <td>{{ criterion.id }}</td>
                            <td>
                                <strong>{{ criterion.name }}</strong><br>
                                <small style="color: #6C757D;">{{ criterion.description or 'Geen beschrijving' }}</small>
                            </td>
                            <td>
                                <span class="badge" style="background-color: {{ criterion.color }}; color: white;">
                                    {{ criterion.category }}
                                </span>
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
    {% endblock %}
    ''', criteria=criteria, document_types=document_types)

@app.route('/criteria/add', methods=['GET', 'POST'])
def criteria_add():
    conn = get_db_connection()
    document_types = []
    sections = []
    
    if conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM document_types ORDER BY name')
        document_types = cursor.fetchall()
        cursor.execute('SELECT * FROM sections WHERE document_type_id = 1 ORDER BY level, name')
        sections = cursor.fetchall()
        
        if request.method == 'POST':
            name = request.form.get('name')
            description = request.form.get('description')
            error_message = request.form.get('error_message')
            instruction_link = request.form.get('instruction_link')
            category = request.form.get('category')
            color = request.form.get('color')
            is_enabled = 1 if request.form.get('is_enabled') else 0
            selected_sections = request.form.getlist('sections')
            
            if name:
                try:
                    cursor.execute('''INSERT INTO criteria (name, description, error_message, instruction_link, category, color, is_enabled)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''', (name, description, error_message, instruction_link, category, color, is_enabled))
                    
                    criteria_id = cursor.lastrowid
                    for section_id in selected_sections:
                        cursor.execute('INSERT INTO criteria_section_mappings (criteria_id, section_id, document_type_id) VALUES (?, ?, ?)', 
                                     (criteria_id, section_id, 1))
                    
                    conn.commit()
                    conn.close()
                    flash('Criterium succesvol toegevoegd!', 'success')
                    return redirect(url_for('criteria_list'))
                except Exception as e:
                    print(f"Error: {e}")
                    flash('Fout bij toevoegen van criterium.', 'error')
            else:
                flash('Naam is verplicht.', 'error')
        
        conn.close()
    
    return render_template_string(BASE_TEMPLATE + '''
    {% block title %}Nieuw Criterium - Feedback Tool{% endblock %}
    {% block content %}
        <div class="header">
            <h1>➕ Nieuw Criterium Toevoegen</h1>
            <p>Voeg een nieuw beoordelingscriterium toe</p>
            <div class="nav-breadcrumb">
                <a href="/">Home</a> > <a href="/criteria">Criteria</a> > Nieuw Criterium
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
                <div class="grid grid-2">
                    <div>
                        <div class="form-group">
                            <label for="name">Naam van het criterium *</label>
                            <input type="text" id="name" name="name" required placeholder="Bijv. Handelingsprobleem SMART">
                        </div>
                        
                        <div class="form-group">
                            <label for="description">Beschrijving</label>
                            <textarea id="description" name="description" placeholder="Beschrijf wat dit criterium controleert..."></textarea>
                        </div>
                        
                        <div class="form-group">
                            <label for="error_message">Foutmelding</label>
                            <textarea id="error_message" name="error_message" placeholder="Melding die wordt getoond bij overtreding..."></textarea>
                        </div>
                        
                        <div class="form-group">
                            <label for="instruction_link">Link naar instructie</label>
                            <input type="url" id="instruction_link" name="instruction_link" placeholder="https://inholland.nl/instructie">
                        </div>
                    </div>
                    
                    <div>
                        <div class="form-group">
                            <label for="category">Categorie</label>
                            <select id="category" name="category">
                                <option value="Algemeen">Algemeen</option>
                                <option value="Tekstueel">Tekstueel</option>
                                <option value="Structuur">Structuur</option>
                                <option value="Inhoudelijk" selected>Inhoudelijk</option>
                                <option value="Opmaak">Opmaak</option>
                                <option value="Referenties">Referenties</option>
                            </select>
                        </div>
                        
                        <div class="form-group">
                            <label for="color">Kleur</label>
                            <select id="color" name="color">
                                <option value="#F94144" selected>🔴 Rood (Kritiek)</option>
                                <option value="#F9C74F">🟡 Geel (Waarschuwing)</option>
                                <option value="#84A98C">🟢 Groen (Info)</option>
                                <option value="#4D908E">🔵 Blauw (Structuur)</option>
                            </select>
                        </div>
                        
                        <div class="form-group">
                            <label>
                                <input type="checkbox" name="is_enabled" checked> Criterium ingeschakeld
                            </label>
                        </div>
                    </div>
                </div>
                
                <div class="form-group">
                    <label>Secties selecteren:</label>
                    <div class="checkbox-group">
                        {% for section in sections %}
                        <div class="checkbox-item">
                            <input type="checkbox" name="sections" value="{{ section.id }}" id="section_{{ section.id }}">
                            <label for="section_{{ section.id }}">{{ section.name }}</label>
                        </div>
                        {% endfor %}
                    </div>
                </div>
                
                <div style="margin-top: 30px;">
                    <button type="submit" class="btn btn-success">💾 Criterium Opslaan</button>
                    <a href="/criteria" class="btn btn-secondary">❌ Annuleren</a>
                </div>
            </form>
        </div>
    {% endblock %}
    ''', document_types=document_types, sections=sections)

@app.route('/criteria/edit/<int:criterion_id>', methods=['GET', 'POST'])
def criteria_edit(criterion_id):
    conn = get_db_connection()
    if not conn:
        flash('Database verbinding mislukt.', 'error')
        return redirect(url_for('criteria_list'))
    
    try:
        cursor = conn.cursor()
        
        if request.method == 'POST':
            name = request.form.get('name')
            description = request.form.get('description')
            error_message = request.form.get('error_message')
            instruction_link = request.form.get('instruction_link')
            category = request.form.get('category')
            color = request.form.get('color')
            is_enabled = 1 if request.form.get('is_enabled') else 0
            selected_sections = request.form.getlist('sections')
            
            if name:
                cursor.execute('''UPDATE criteria SET name=?, description=?, error_message=?, instruction_link=?, category=?, color=?, is_enabled=? WHERE id=?''', 
                             (name, description, error_message, instruction_link, category, color, is_enabled, criterion_id))
                
                cursor.execute('DELETE FROM criteria_section_mappings WHERE criteria_id=?', (criterion_id,))
                for section_id in selected_sections:
                    cursor.execute('INSERT INTO criteria_section_mappings (criteria_id, section_id, document_type_id) VALUES (?, ?, ?)', 
                                 (criterion_id, section_id, 1))
                
                conn.commit()
                flash('Criterium succesvol bijgewerkt!', 'success')
                return redirect(url_for('criteria_list'))
            else:
                flash('Naam is verplicht.', 'error')
        
        cursor.execute('SELECT * FROM criteria WHERE id=?', (criterion_id,))
        criterion = cursor.fetchone()
        
        if not criterion:
            flash('Criterium niet gevonden.', 'error')
            return redirect(url_for('criteria_list'))
        
        cursor.execute('SELECT * FROM sections WHERE document_type_id=1 ORDER BY level, name')
        sections = cursor.fetchall()
        
        cursor.execute('SELECT section_id FROM criteria_section_mappings WHERE criteria_id=?', (criterion_id,))
        linked_sections = [row[0] for row in cursor.fetchall()]
        
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
                    <div class="grid grid-2">
                        <div>
                            <div class="form-group">
                                <label for="name">Naam van het criterium *</label>
                                <input type="text" id="name" name="name" required value="{{ criterion.name }}">
                            </div>
                            
                            <div class="form-group">
                                <label for="description">Beschrijving</label>
                                <textarea id="description" name="description">{{ criterion.description or '' }}</textarea>
                            </div>
                            
                            <div class="form-group">
                                <label for="error_message">Foutmelding</label>
                                <textarea id="error_message" name="error_message">{{ criterion.error_message or '' }}</textarea>
                            </div>
                            
                            <div class="form-group">
                                <label for="instruction_link">Link naar instructie</label>
                                <input type="url" id="instruction_link" name="instruction_link" value="{{ criterion.instruction_link or '' }}">
                            </div>
                        </div>
                        
                        <div>
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
                                <label>
                                    <input type="checkbox" name="is_enabled" {% if criterion.is_enabled %}checked{% endif %}> Criterium ingeschakeld
                                </label>
                            </div>
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label>Secties selecteren:</label>
                        <div class="checkbox-group">
                            {% for section in sections %}
                            <div class="checkbox-item">
                                <input type="checkbox" name="sections" value="{{ section.id }}" id="section_{{ section.id }}"
                                       {% if section.id in linked_sections %}checked{% endif %}>
                                <label for="section_{{ section.id }}">{{ section.name }}</label>
                            </div>
                            {% endfor %}
                        </div>
                    </div>
                    
                    <div style="margin-top: 30px;">
                        <button type="submit" class="btn btn-success">💾 Wijzigingen Opslaan</button>
                        <a href="/criteria" class="btn btn-secondary">❌ Annuleren</a>
                    </div>
                </form>
            </div>
        {% endblock %}
        ''', criterion=criterion, sections=sections, linked_sections=linked_sections)
        
    except Exception as e:
        print(f"Error: {e}")
        flash('Fout bij bewerken van criterium.', 'error')
        conn.close()
        return redirect(url_for('criteria_list'))

@app.route('/criteria/delete/<int:criterion_id>')
def criteria_delete(criterion_id):
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM criteria_section_mappings WHERE criteria_id=?', (criterion_id,))
            cursor.execute('DELETE FROM criteria WHERE id=?', (criterion_id,))
            conn.commit()
            conn.close()
            flash('Criterium succesvol verwijderd!', 'success')
        except Exception as e:
            print(f"Error: {e}")
            flash('Fout bij verwijderen van criterium.', 'error')
            conn.close()
    return redirect(url_for('criteria_list'))

@app.route('/criteria/import')
def criteria_import():
    return "Import functionaliteit - wordt binnenkort toegevoegd. <a href='/criteria'>Terug naar criteria</a>"

@app.route('/criteria/export')
def criteria_export():
    return "Export functionaliteit - wordt binnenkort toegevoegd. <a href='/criteria'>Terug naar criteria</a>"

@app.route('/sections')
def sections():
    return "Sectie beheer - wordt binnenkort toegevoegd. <a href='/'>Terug naar hoofdmenu</a>"

if __name__ == '__main__':
    print("Starting Working Feedback Tool...")
    if init_database():
        print("Database initialized successfully")
    app.run(host='0.0.0.0', port=5001, debug=False)

