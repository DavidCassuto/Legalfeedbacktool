import sqlite3
from datetime import datetime
import json # Nodig voor JSON velden zoals alternative_names

def initialize_db(conn: sqlite3.Connection):
    """
    Initialiseert de database: maakt tabellen aan en vult deze met initiële data.
    """
    cursor = conn.cursor()

    # Tabel: document_types
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            identifier TEXT NOT NULL UNIQUE
        )
    """)

    # Tabel: organizations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT
        )
    """)

    # AANGEPAST: Tabel: sections - Nu met parent_id, alternative_names, order_index, level
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            identifier TEXT NOT NULL UNIQUE,
            is_required BOOLEAN DEFAULT 0,
            parent_id INTEGER, -- NIEUW: Hiërarchie van secties
            alternative_names TEXT, -- NIEUW: JSON array van alternatieve namen (bijv. "intro", "inleiding")
            order_index INTEGER, -- NIEUW: Volgorde van sectie in een standaarddocument
            level INTEGER, -- NIEUW: Verwacht kopniveau (H1, H2, etc.)
            FOREIGN KEY (parent_id) REFERENCES sections(id)
        )
    """)

    # Tabel: documents
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            file_path TEXT UNIQUE NOT NULL,
            file_size INTEGER,
            document_type_id INTEGER,
            organization_id INTEGER,
            uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            analysis_status TEXT DEFAULT 'pending', -- 'pending', 'completed', 'failed'
            analysis_data TEXT, -- Slaat JSON-geformatteerde samenvatting van analyse op
            FOREIGN KEY (document_type_id) REFERENCES document_types(id),
            FOREIGN KEY (organization_id) REFERENCES organizations(id)
        )
    """)

    # Tabel: criteria (algemene definitie van een criterium)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS criteria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            rule_type TEXT NOT NULL, -- 'tekstueel', 'structureel', 'inhoudelijk', etc.
            application_scope TEXT NOT NULL, -- 'document_only', 'all', 'specific_sections', 'exclude_sections'
            is_enabled BOOLEAN DEFAULT 1,
            severity TEXT DEFAULT 'warning', -- 'ok', 'info', 'warning', 'violation', 'error'
            error_message TEXT,
            fixed_feedback_text TEXT, -- Voorgestelde oplossing voor feedback
            frequency_unit TEXT DEFAULT 'document', -- 'document', 'section', 'paragraph', 'occurrence'
            max_mentions_per INTEGER DEFAULT 0, -- 0 = onbeperkt
            expected_value_min REAL, -- Algemeen veld voor numerieke checks (bv. min woorden, min paragrafen)
            expected_value_max REAL, -- Algemeen veld voor numerieke checks (bv. max woorden, max paragrafen)
            color TEXT -- Hex code voor UI weergave (bijv. #FF0000)
        )
    """)

    # Tabel: document_type_criteria_mappings (welke criteria gelden voor welk documenttype)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_type_criteria_mappings (
            document_type_id INTEGER,
            criteria_id INTEGER,
            PRIMARY KEY (document_type_id, criteria_id),
            FOREIGN KEY (document_type_id) REFERENCES document_types(id),
            FOREIGN KEY (criteria_id) REFERENCES criteria(id)
        )
    """)

    # Tabel: criteria_section_mappings (welke criteria gelden voor welke specifieke secties)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS criteria_section_mappings (
            criteria_id INTEGER,
            section_id INTEGER,
            is_excluded BOOLEAN DEFAULT 0, -- Als True, dan is deze sectie UITGESLOTEN voor dit criterium
            weight REAL DEFAULT 1.0, -- Optioneel: gewicht van criterium voor deze sectie
            PRIMARY KEY (criteria_id, section_id),
            FOREIGN KEY (criteria_id) REFERENCES criteria(id),
            FOREIGN KEY (section_id) REFERENCES sections(id)
        )
    """)

    # Tabel: feedback_items (opgeslagen feedback van analyses)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            criteria_id INTEGER NOT NULL,
            section_id INTEGER, -- Kan NULL zijn voor document-brede checks
            status TEXT NOT NULL, -- 'ok', 'info', 'warning', 'violation', 'error'
            message TEXT NOT NULL,
            suggestion TEXT,
            location TEXT, -- Meer specifieke locatie info (bijv. "Paragraaf 3", "Regel 15")
            confidence REAL,
            generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id),
            FOREIGN KEY (criteria_id) REFERENCES criteria(id),
            FOREIGN KEY (section_id) REFERENCES sections(id)
        )
    """)

    # --- Initiële Data Invoegen (Idempotent) ---

    # Document Types
    document_types_data = [
        ('Rapport', 'rapport'),
        ('Scriptie', 'scriptie'),
        ('Plan van Aanpak', 'plan_van_aanpak')
    ]
    for name, identifier in document_types_data:
        cursor.execute("INSERT OR IGNORE INTO document_types (name, identifier) VALUES (?, ?)", (name, identifier))

    # Organizations
    organizations_data = [
        ('Hogeschool Inholland', 'Een fictieve hogeschool'),
        ('Tech Solutions B.V.', 'Technologie adviesbureau')
    ]
    for name, description in organizations_data:
        cursor.execute("INSERT OR IGNORE INTO organizations (name, description) VALUES (?, ?)", (name, description))

    # BELANGRIJK: Secties - Nu met alle velden en hiërarchie
    # Zorg dat ALLE dictionaries de 'parent_id' key hebben, zelfs als deze None is.
    sections_initial_data = [
        # Top-level sections (level 1)
        {'name': 'Inleiding', 'identifier': 'inleiding', 'is_required': 0, 'parent_id': None, 'alternative_names': ['introductie', 'voorwoord'], 'order_index': 10, 'level': 1},
        {'name': 'Probleemanalyse', 'identifier': 'probleemanalyse', 'is_required': 1, 'parent_id': None, 'alternative_names': ['probleemstelling', 'vraagstelling', 'het probleem'], 'order_index': 20, 'level': 1},
        {'name': 'Doelstelling', 'identifier': 'doelstelling', 'is_required': 0, 'parent_id': None, 'alternative_names': ['doel', 'doelen'], 'order_index': 30, 'level': 1},
        {'name': 'Hoofd- en Deelvragen', 'identifier': 'hoofd_deelvragen', 'is_required': 0, 'parent_id': None, 'alternative_names': ['onderzoeksvragen', 'vragen'], 'order_index': 40, 'level': 1},
        {'name': 'Theorie en Achtergrond', 'identifier': 'theorie_achtergrond', 'is_required': 0, 'parent_id': None, 'alternative_names': ['theorie', 'achtergrond', 'theoretisch kader', 'literatuurstudie'], 'order_index': 50, 'level': 1},
        {'name': 'Methode', 'identifier': 'methode', 'is_required': 1, 'parent_id': None, 'alternative_names': ['methodologie', 'onderzoeksmethode', 'methoden', 'methoden: juridisch', 'methoden: praktijk', 'methode representatie'], 'order_index': 60, 'level': 1}, # Uitgebreid
        {'name': 'Resultaten', 'identifier': 'resultaten', 'is_required': 0, 'parent_id': None, 'alternative_names': ['bevindingen'], 'order_index': 70, 'level': 1},
        {'name': 'Discussie', 'identifier': 'discussie', 'is_required': 0, 'parent_id': None, 'alternative_names': [], 'order_index': 80, 'level': 1},
        {'name': 'Conclusie', 'identifier': 'conclusie', 'is_required': 1, 'parent_id': None, 'alternative_names': ['slot'], 'order_index': 90, 'level': 1},
        {'name': 'Aanbevelingen', 'identifier': 'aanbevelingen', 'is_required': 0, 'parent_id': None, 'alternative_names': [], 'order_index': 100, 'level': 1},
        {'name': 'Literatuurlijst', 'identifier': 'literatuur', 'is_required': 1, 'parent_id': None, 'alternative_names': ['referenties', 'bibliografie'], 'order_index': 110, 'level': 1},
        {'name': 'Bijlagen', 'identifier': 'bijlagen', 'is_required': 0, 'parent_id': None, 'alternative_names': ['appendix', 'appendices', 'bijlage', 'bijlagen', 'bijlagen:'], 'order_index': 120, 'level': 1}, # Uitgebreid
        {'name': 'Hoofdstuk Algemeen', 'identifier': 'hoofdstuk_algemeen', 'is_required': 0, 'parent_id': None, 'alternative_names': ['hoofdstuk'], 'order_index': 5, 'level': 1}, # NIEUW: Voor algemene hoofdstukkoppen

        # Sub-sections (levels > 1) - Parent IDs worden later ingevuld
        {'name': 'Handelingsprobleem', 'identifier': 'handelingsprobleem', 'is_required': 0, 'parent_id': None, 'parent_name': 'Probleemanalyse', 'alternative_names': ['het handelingsprobleem'], 'order_index': 21, 'level': 2},
        {'name': 'Hoofdvraag', 'identifier': 'hoofdvraag', 'is_required': 0, 'parent_id': None, 'parent_name': 'Hoofd- en Deelvragen', 'alternative_names': ['de hoofdvraag'], 'order_index': 41, 'level': 2},
        {'name': 'Deelvragen', 'identifier': 'deelvragen', 'is_required': 0, 'parent_id': None, 'parent_name': 'Hoofd- en Deelvragen', 'alternative_names': ['de deelvragen'], 'order_index': 42, 'level': 2},
        {'name': 'Output', 'identifier': 'output', 'is_required': 0, 'parent_id': None, 'parent_name': 'Doelstelling', 'alternative_names': ['de output'], 'order_index': 31, 'level': 2},
        {'name': 'Outcome', 'identifier': 'outcome', 'is_required': 0, 'parent_id': None, 'parent_name': 'Doelstelling', 'alternative_names': ['de outcome'], 'order_index': 32, 'level': 2},
        {'name': 'Leeswijzer', 'identifier': 'leeswijzer', 'is_required': 0, 'parent_id': None, 'parent_name': 'Inleiding', 'alternative_names': ['de leeswijzer'], 'order_index': 11, 'level': 2},
        {'name': 'Juridische context', 'identifier': 'juridische_context', 'is_required': 0, 'parent_id': None, 'parent_name': 'Theorie en Achtergrond', 'alternative_names': ['de juridische context'], 'order_index': 51, 'level': 2},
        {'name': 'Vereisten voor aansprakelijkheid', 'identifier': 'vereisten_aansprakelijkheid', 'is_required': 0, 'parent_id': None, 'parent_name': 'Juridische context', 'alternative_names': ['vereisten aansprakelijkheid', 'art. 6:162 BW'], 'order_index': 52, 'level': 3},
        {'name': 'Kwalitatieve aansprakelijkheid', 'identifier': 'kwalitatieve_aansprakelijkheid', 'is_required': 0, 'parent_id': None, 'parent_name': 'Juridische context', 'alternative_names': ['kwalitatieve aansprakelijkheid van ondergeschikten', 'art. 6:170 BW'], 'order_index': 53, 'level': 3},
        {'name': 'Logboek en Planning', 'identifier': 'logboek_planning', 'is_required': 0, 'parent_id': None, 'parent_name': 'Methode', 'alternative_names': ['logboek', 'planning'], 'order_index': 61, 'level': 2},
        {'name': 'Risicoanalyse', 'identifier': 'risicoanalyse', 'is_required': 0, 'parent_id': None, 'parent_name': 'Methode', 'alternative_names': [], 'order_index': 62, 'level': 2}
    ]

    # Eerst de top-level secties invoegen
    parent_id_map = {} # Om parent_id's op te zoeken bij subsecties
    for s_data in sections_initial_data:
        # Gebruik .get() om veilig 'parent_id' te benaderen; standaard None als de sleutel ontbreekt.
        current_parent_id = s_data.get('parent_id', None)
        
        # Check nu of het een top-level sectie is (geen parent_id EN geen parent_name)
        # De 'Hoofdstuk Algemeen' sectie wordt hier ook als top-level behandeld.
        if current_parent_id is None and 'parent_name' not in s_data: 
            # Check eerst of de sectie al bestaat
            existing_section = cursor.execute("SELECT id FROM sections WHERE identifier = ?", (s_data['identifier'],)).fetchone()
            if not existing_section:
                cursor.execute("""
                    INSERT INTO sections (name, identifier, is_required, parent_id, alternative_names, order_index, level)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (s_data['name'], s_data['identifier'], s_data['is_required'], current_parent_id,
                      json.dumps(s_data['alternative_names']), s_data['order_index'], s_data['level']))
                if cursor.lastrowid:
                    parent_id_map[s_data['name']] = cursor.lastrowid
            else:
                parent_id_map[s_data['name']] = existing_section[0]
            

    # Nu de sub-secties invoegen en hun parent_id instellen
    for s_data in sections_initial_data:
        # Als het een subsectie is met een gedefinieerde parent_name
        if 'parent_name' in s_data and s_data['parent_name'] in parent_id_map:
            # Update de parent_id in de dictionary voor de insert
            s_data['parent_id'] = parent_id_map[s_data['parent_name']] 
            # Check eerst of de subsectie al bestaat
            existing_section = cursor.execute("SELECT id FROM sections WHERE identifier = ?", (s_data['identifier'],)).fetchone()
            if not existing_section:
                cursor.execute("""
                    INSERT INTO sections (name, identifier, is_required, parent_id, alternative_names, order_index, level)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (s_data['name'], s_data['identifier'], s_data['is_required'], s_data['parent_id'],
                      json.dumps(s_data['alternative_names']), s_data['order_index'], s_data['level']))
                if cursor.lastrowid:
                    parent_id_map[s_data['name']] = cursor.lastrowid
            else:
                parent_id_map[s_data['name']] = existing_section[0]
            
        elif 'parent_name' in s_data and s_data['parent_name'] not in parent_id_map:
            print(f"Waarschuwing: Parent sectie '{s_data['parent_name']}' niet gevonden voor '{s_data['name']}'. Zorg dat parent secties eerst worden gedefinieerd en ingevoegd.")


    # Criteria (verbeterd om dubbele inserts te voorkomen)
    criteria_data = [
        (1, 'Woordtelling Inleiding', 'De inleiding moet tussen de 5 en 200 woorden bevatten.', 'structureel', 'specific_sections', 1, 'warning', 'De inleiding is te kort of te lang.', 'Zorg dat de inleiding tussen de 5 en 200 woorden bevat.', 'section', 1, 5, 200, '#FFD700'),
        (2, 'SMART formulering Probleemstelling', 'De probleemstelling moet SMART geformuleerd zijn (Specifiek, Meetbaar, Acceptabel, Realistisch, Tijdgebonden).', 'inhoudelijk', 'specific_sections', 1, 'violation', 'De probleemstelling is niet SMART geformuleerd.', 'Herschrijf de probleemstelling volgens de SMART-principes.', 'section', 1, None, None, '#FF0000'),
        (3, 'Geen persoonlijk taalgebruik', 'Vermijd persoonlijke voornaamwoorden zoals "ik", "wij", "ons".', 'tekstueel', 'all', 1, 'warning', 'Persoonlijk taalgebruik gevonden.', 'Hanteer een zakelijke schrijfstijl zonder persoonlijke voornaamwoorden.', 'section', 3, None, None, '#FFD700'),
        (4, 'Minimaal 2 paragrafen Methode', 'De methode sectie moet minimaal twee paragrafen bevatten voor structuur.', 'structureel', 'specific_sections', 1, 'warning', 'De methode sectie heeft te weinig paragrafen.', 'Splits de methode sectie op in meer paragrafen voor duidelijkheid.', 'section', 1, 2, None, '#FFD700'),
        (5, 'Verplichte sectie aanwezigheid: Probleemstelling', 'De probleemstelling sectie is verplicht voor dit documenttype.', 'structureel', 'document_only', 1, 'violation', 'De sectie "Probleemstelling" is niet gevonden in het document.', 'Zorg ervoor dat de sectie "Probleemstelling" duidelijk aanwezig is.', 'document', 1, None, None, '#FF0000'),
        (6, 'Sectievolgorde: Inleiding voor Methode', 'De inleiding moet voor de methodesectie komen.', 'structureel', 'document_only', 1, 'violation', 'De sectie "Methode" staat vóór de "Inleiding".', 'Controleer de volgorde van de secties. De Inleiding moet voor de Methode-sectie komen.', 'document', 1, None, None, '#FF0000')
    ]
    
    # Controleer eerst welke criteria al bestaan
    existing_criteria = cursor.execute("SELECT id, name FROM criteria").fetchall()
    existing_ids = {row[0] for row in existing_criteria}
    existing_names = {row[1] for row in existing_criteria}
    
    for crit_id, name, desc, r_type, app_scope, enabled, severity, err_msg, fix_txt, freq_unit, max_mentions, min_val, max_val, color in criteria_data:
        # Skip als criterium al bestaat (op ID of naam)
        if crit_id in existing_ids or name in existing_names:
            print(f"Skipping existing criterion: {name}")
            continue
            
        cursor.execute("""
            INSERT INTO criteria (id, name, description, rule_type, application_scope, is_enabled, severity, error_message, fixed_feedback_text, frequency_unit, max_mentions_per, expected_value_min, expected_value_max, color)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (crit_id, name, desc, r_type, app_scope, enabled, severity, err_msg, fix_txt, freq_unit, max_mentions, min_val, max_val, color))

    # Mappings: DocumentType naar Criteria (alleen voor nieuwe criteria)
    rapport_type_id = cursor.execute("SELECT id FROM document_types WHERE identifier = 'rapport'").fetchone()[0]
    for criteria_id in [1, 2, 3, 4, 5, 6]:
        if criteria_id in existing_ids:
            continue  # Skip als criterium al bestond
        cursor.execute("INSERT OR IGNORE INTO document_type_criteria_mappings (document_type_id, criteria_id) VALUES (?, ?)", (rapport_type_id, criteria_id))

    # Mappings: Criteria naar Specifieke Secties (alleen voor nieuwe criteria)
    try:
        inleiding_id = cursor.execute("SELECT id FROM sections WHERE identifier = 'inleiding'").fetchone()[0]
        probleemstelling_id = cursor.execute("SELECT id FROM sections WHERE identifier = 'probleemanalyse'").fetchone()[0]
        methode_id = cursor.execute("SELECT id FROM sections WHERE identifier = 'methode'").fetchone()[0]
        
        # Alleen mappings toevoegen voor criteria die nieuw zijn toegevoegd
        if 1 not in existing_ids:
            cursor.execute("INSERT OR IGNORE INTO criteria_section_mappings (criteria_id, section_id, is_excluded) VALUES (?, ?, ?)", (1, inleiding_id, 0))
        if 2 not in existing_ids:
            cursor.execute("INSERT OR IGNORE INTO criteria_section_mappings (criteria_id, section_id, is_excluded) VALUES (?, ?, ?)", (2, probleemstelling_id, 0))
        if 4 not in existing_ids:
            cursor.execute("INSERT OR IGNORE INTO criteria_section_mappings (criteria_id, section_id, is_excluded) VALUES (?, ?, ?)", (4, methode_id, 0))
    except (TypeError, IndexError) as e:
        print(f"Warning: Could not create section mappings: {e}")

    conn.commit()


def get_or_create_document(conn: sqlite3.Connection, name: str, file_path: str):
    """
    Haalt een document ID op of maakt een nieuw document aan in de database.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE file_path = ?", (file_path,))
    result = cursor.fetchone()
    if result:
        return result['id']
    else:
        cursor.execute("INSERT INTO documents (name, original_filename, file_path, uploaded_at) VALUES (?, ?, ?, ?)",
                       (name, name, file_path, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        return cursor.lastrowid

def get_document_type_by_identifier(conn: sqlite3.Connection, identifier: str):
    """Haalt documenttype metadata op basis van identifier."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM document_types WHERE identifier = ?", (identifier,))
    return cursor.fetchone()

def get_sections_for_document_type(conn: sqlite3.Connection, document_type_id: int):
    """
    Haalt alle gedefinieerde secties op die relevant kunnen zijn voor een documenttype.
    Inclusief de alternative_names geparsed van JSON.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sections ORDER BY order_index ASC, level ASC") 
    
    sections_with_parsed_aliases = []
    for row in cursor.fetchall():
        section = dict(row)
        if section['alternative_names']:
            try:
                section['alternative_names'] = json.loads(section['alternative_names'])
            except json.JSONDecodeError:
                section['alternative_names'] = [] # Val terug op lege lijst bij parseerfout
        else:
            section['alternative_names'] = []
        sections_with_parsed_aliases.append(section)
    return sections_with_parsed_aliases


def get_criteria_for_document_type(conn: sqlite3.Connection, document_type_id: int) -> list[dict]:
    """
    Haalt alle actieve criteria op voor een specifiek documenttype, inclusief hun mappings.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            c.id,
            c.name,
            c.description,
            c.rule_type,
            c.application_scope,
            c.is_enabled,
            c.severity,
            c.error_message,
            c.fixed_feedback_text,
            c.frequency_unit,
            c.max_mentions_per,
            c.expected_value_min,
            c.expected_value_max,
            c.color
        FROM criteria c
        JOIN document_type_criteria_mappings dtcm ON c.id = dtcm.criteria_id
        WHERE dtcm.document_type_id = ? AND c.is_enabled = 1
    """, (document_type_id,))
    
    criteria_rows = cursor.fetchall()
    criteria_list = []

    for row in criteria_rows:
        criterion = dict(row)
        cursor.execute("""
            SELECT
                csm.section_id,
                s.identifier AS section_identifier,
                s.name AS section_name,
                csm.is_excluded,
                csm.weight
            FROM criteria_section_mappings csm
            JOIN sections s ON csm.section_id = s.id
            WHERE csm.criteria_id = ?
        """, (criterion['id'],))
        criterion['section_mappings'] = [dict(mapping_row) for mapping_row in cursor.fetchall()]
        criteria_list.append(criterion)
    
    return criteria_list

def save_feedback_item(conn: sqlite3.Connection, feedback_data: dict, document_id: int):
    """
    Slaat een gegenereerd feedback item op in de database.
    """
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO feedback_items (
            document_id, criteria_id, section_id, status, message, suggestion, location, confidence, generated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        document_id,
        feedback_data['criteria_id'],
        feedback_data.get('section_id'), 
        feedback_data['status'],
        feedback_data['message'],
        feedback_data.get('suggestion'),
        feedback_data.get('location'),
        feedback_data.get('confidence'),
        datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ))
    conn.commit()

def get_criteria_for_document_type_new(db, document_type_id):
    """
    Haal criteria op voor een document type (nieuwe structuur).
    Gebruikt criteria_instances in plaats van de oude mapping.
    """
    cursor = db.cursor()
    cursor.execute('''
        SELECT ci.*, ct.name as template_name
        FROM criteria_instances ci
        LEFT JOIN criteria_templates ct ON ci.template_id = ct.id
        WHERE ci.document_type_id = ? AND ci.is_enabled = 1
        ORDER BY ci.name
    ''', (document_type_id,))
    
    # Haal kolomnamen op
    columns = [description[0] for description in cursor.description]
    
    # Converteer naar dictionaries
    criteria_dicts = []
    for row in cursor.fetchall():
        criteria_dict = dict(zip(columns, row))
        criteria_dicts.append(criteria_dict)
    
    return criteria_dicts

def get_sections_for_document_type_new(db, document_type_id):
    """
    Haal secties op voor een document type (nieuwe structuur).
    Gebruikt document_type_sections in plaats van directe koppeling.
    """
    cursor = db.cursor()
    cursor.execute('''
        SELECT s.*, dts.is_required, dts.order_index
        FROM sections s
        JOIN document_type_sections dts ON s.id = dts.section_id
        WHERE dts.document_type_id = ?
        ORDER BY dts.order_index
    ''', (document_type_id,))
    
    # Haal kolomnamen op
    columns = [description[0] for description in cursor.description]
    
    # Converteer naar dictionaries
    sections_dicts = []
    for row in cursor.fetchall():
        section_dict = dict(zip(columns, row))
        sections_dicts.append(section_dict)
    
    return sections_dicts

def create_criteria_instance_from_template(db, template_id, document_type_id, organization_id, custom_name=None):
    """
    Maak een nieuwe criteria instance aan op basis van een template.
    """
    # Haal template op
    template = db.execute('SELECT * FROM criteria_templates WHERE id = ?', (template_id,)).fetchone()
    if not template:
        return None
    
    # Maak instance aan
    name = custom_name or template['name']
    cursor = db.cursor()
    cursor.execute('''
        INSERT INTO criteria_instances (
            template_id, document_type_id, organization_id, name, description,
            rule_type, application_scope, severity, error_message, 
            fixed_feedback_text, color
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (template_id, document_type_id, organization_id, name, template['description'],
         template['rule_type'], template['application_scope'], template['severity'],
         template['error_message'], template['fixed_feedback_text'], template['color']))
    
    return cursor.lastrowid

def get_organization_document_types(db, organization_id):
    """
    Haal alle document types op voor een organisatie.
    """
    document_types = db.execute('''
        SELECT dt.*, COUNT(d.id) as document_count
        FROM document_types dt
        LEFT JOIN documents d ON dt.id = d.document_type_id
        WHERE dt.organization_id = ? OR dt.organization_id IS NULL
        GROUP BY dt.id
        ORDER BY dt.name
    ''', (organization_id,)).fetchall()
    
    # Converteer SQLite Row objecten naar dictionaries
    doc_types_dicts = []
    for row in document_types:
        # Check of het een Row object is of een tuple
        if hasattr(row, 'keys'):
            doc_type_dict = {key: row[key] for key in row.keys()}
        else:
            # Het is een tuple, gebruik de oude methode
            doc_type_dict = dict(zip([col[0] for col in db.description], row))
        doc_types_dicts.append(doc_type_dict)
    
    return doc_types_dicts

def get_available_criteria_templates(db, organization_id=None):
    """
    Haal beschikbare criteria templates op.
    """
    if organization_id:
        templates = db.execute('''
            SELECT * FROM criteria_templates 
            WHERE is_global = 1 OR organization_id = ?
            ORDER BY name
        ''', (organization_id,)).fetchall()
    else:
        templates = db.execute('SELECT * FROM criteria_templates ORDER BY name').fetchall()
    
    # Converteer SQLite Row objecten naar dictionaries
    templates_dicts = []
    for row in templates:
        template_dict = {key: row[key] for key in row.keys()}
        templates_dicts.append(template_dict)
    
    return templates_dicts

def link_section_to_document_type(db, document_type_id, section_id, is_required=False, order_index=0):
    """
    Koppel een sectie aan een document type.
    """
    try:
        db.execute('''
            INSERT INTO document_type_sections (document_type_id, section_id, is_required, order_index)
            VALUES (?, ?, ?, ?)
        ''', (document_type_id, section_id, is_required, order_index))
        db.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def unlink_section_from_document_type(db, document_type_id, section_id):
    """
    Verwijder koppeling tussen sectie en document type.
    """
    db.execute('''
        DELETE FROM document_type_sections 
        WHERE document_type_id = ? AND section_id = ?
    ''', (document_type_id, section_id))
    db.commit()

def get_criteria_section_mappings(db, criteria_instance_id):
    """
    Haal sectie mappings op voor een criteria instance.
    """
    mappings = db.execute('''
        SELECT s.* FROM sections s
        JOIN criteria_section_mappings csm ON s.id = csm.section_id
        WHERE csm.criteria_instance_id = ?
        ORDER BY s.name
    ''', (criteria_instance_id,)).fetchall()
    
    # Converteer SQLite Row objecten naar dictionaries
    mappings_dicts = []
    for row in mappings:
        mapping_dict = {key: row[key] for key in row.keys()}
        mappings_dicts.append(mapping_dict)
    
    return mappings_dicts

def link_criteria_to_section(db, criteria_instance_id, section_id):
    """
    Koppel een criteria instance aan een sectie.
    """
    try:
        db.execute('''
            INSERT INTO criteria_section_mappings (criteria_instance_id, section_id)
            VALUES (?, ?)
        ''', (criteria_instance_id, section_id))
        db.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def unlink_criteria_from_section(db, criteria_instance_id, section_id):
    """
    Verwijder koppeling tussen criteria instance en sectie.
    """
    db.execute('''
        DELETE FROM criteria_section_mappings 
        WHERE criteria_instance_id = ? AND section_id = ?
    ''', (criteria_instance_id, section_id))
    db.commit()

