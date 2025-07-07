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
        {'name': 'Juridische context algemeen', 'identifier': 'juridische_context_algemeen', 'is_required': 0, 'parent_id': None, 'parent_name': 'Theorie en Achtergrond', 'alternative_names': ['juridische context', 'de juridische context'], 'order_index': 51, 'level': 2}, # LET OP: Naam en identifier aangepast
        {'name': 'Vereisten voor aansprakelijkheid', 'identifier': 'vereisten_aansprakelijkheid', 'is_required': 0, 'parent_id': None, 'parent_name': 'Juridische context algemeen', 'alternative_names': ['vereisten aansprakelijkheid', 'art. 6:162 BW'], 'order_index': 52, 'level': 3},
        {'name': 'Kwalitatieve aansprakelijkheid', 'identifier': 'kwalitatieve_aansprakelijkheid', 'is_required': 0, 'parent_id': None, 'parent_name': 'Juridische context algemeen', 'alternative_names': ['kwalitatieve aansprakelijkheid van ondergeschikten', 'art. 6:170 BW'], 'order_index': 53, 'level': 3},
        {'name': 'Logboek en Planning', 'identifier': 'logboek_planning', 'is_required': 0, 'parent_id': None, 'parent_name': 'Methode', 'alternative_names': ['logboek', 'planning'], 'order_index': 61, 'level': 2},
        {'name': 'Risicoanalyse', 'identifier': 'risicoanalyse', 'is_required': 0, 'parent_id': None, 'parent_name': 'Methode', 'alternative_names': [], 'order_index': 62, 'level': 2},
        {'name': 'Bijlage 1 Concept Interviewvragen', 'identifier': 'bijlage_1_interviewvragen', 'is_required': 0, 'parent_id': None, 'parent_name': 'Bijlagen', 'alternative_names': ['bijlage 1: concept interviewvragen', 'concept interviewvragen', 'bijlage 1 concept interviewvragen', 'bijlage 1'], 'order_index': 121, 'level': 2},
        {'name': 'Bijlage 2 Beleid Gymlessen', 'identifier': 'bijlage_2_gymlessen', 'is_required': 0, 'parent_id': None, 'parent_name': 'Bijlagen', 'alternative_names': ['bijlage 2: beleid gymlessen obs de esch', 'beleid gymlessen obs de esch', 'bijlage 2 beleid gymlessen', 'bijlage 2'], 'order_index': 122, 'level': 2}
    ]

    # Eerst de top-level secties invoegen
    parent_id_map = {} # Om parent_id's op te zoeken bij subsecties
    for s_data in sections_initial_data:
        current_parent_id = s_data.get('parent_id', None)
        
        if current_parent_id is None and 'parent_name' not in s_data: 
            cursor.execute("""
                INSERT OR IGNORE INTO sections (name, identifier, is_required, parent_id, alternative_names, order_index, level)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (s_data['name'], s_data['identifier'], s_data['is_required'], current_parent_id,
                  json.dumps(s_data['alternative_names']), s_data['order_index'], s_data['level']))
            if cursor.lastrowid:
                parent_id_map[s_data['name']] = cursor.lastrowid
            else:
                existing_id = cursor.execute("SELECT id FROM sections WHERE identifier = ?", (s_data['identifier'],)).fetchone()
                if existing_id:
                    parent_id_map[s_data['name']] = existing_id[0]
                else:
                    print(f"Waarschuwing: Kon ID niet vinden voor bestaande sectie '{s_data['name']}'.")

    # Nu de sub-secties invoegen en hun parent_id instellen
    for s_data in sections_initial_data:
        if 'parent_name' in s_data and s_data['parent_name'] in parent_id_map:
            s_data['parent_id'] = parent_id_map[s_data['parent_name']] 
            cursor.execute("""
                INSERT OR IGNORE INTO sections (name, identifier, is_required, parent_id, alternative_names, order_index, level)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (s_data['name'], s_data['identifier'], s_data['is_required'], s_data['parent_id'],
                  json.dumps(s_data['alternative_names']), s_data['order_index'], s_data['level']))
            if cursor.lastrowid:
                parent_id_map[s_data['name']] = cursor.lastrowid
            else:
                existing_id = cursor.execute("SELECT id FROM sections WHERE identifier = ?", (s_data['identifier'],)).fetchone()
                if existing_id:
                    parent_id_map[s_data['name']] = existing_id[0]
                else:
                    print(f"Waarschuwing: Kon ID niet vinden voor bestaande sub-sectie '{s_data['name']}'.")
        elif 'parent_name' in s_data and s_data['parent_name'] not in parent_id_map:
            print(f"Waarschuwing: Parent sectie '{s_data['parent_name']}' niet gevonden voor '{s_data['name']}'. Zorg dat parent secties eerst worden gedefinieerd en ingevoegd.")


    # Criteria (onveranderd, maar Idempotent)
    criteria_data = [
        (1, 'Woordtelling Inleiding', 'De inleiding moet tussen de 5 en 200 woorden bevatten.', 'structureel', 'specific_sections', 1, 'warning', 'De inleiding is te kort of te lang.', 'Zorg dat de inleiding tussen de 5 en 200 woorden bevat.', 'section', 1, 5, 200, '#FFD700'),
        (2, 'SMART formulering Probleemstelling', 'De probleemstelling moet SMART geformuleerd zijn (Specifiek, Meetbaar, Acceptabel, Realistisch, Tijdgebonden).', 'inhoudelijk', 'specific_sections', 1, 'violation', 'De probleemstelling is niet SMART geformuleerd.', 'Herschrijf de probleemstelling volgens de SMART-principes.', 'section', 1, None, None, '#FF0000'),
        (3, 'Geen persoonlijk taalgebruik', 'Vermijd persoonlijke voornaamwoorden zoals "ik", "wij", "ons".', 'tekstueel', 'all', 1, 'warning', 'Persoonlijk taalgebruik gevonden.', 'Hanteer een zakelijke schrijfstijl zonder persoonlijke voornaamwoorden.', 'section', 3, None, None, '#FFD700'),
        (4, 'Minimaal 2 paragrafen Methode', 'De methode sectie moet minimaal twee paragrafen bevatten voor structuur.', 'structureel', 'specific_sections', 1, 'warning', 'De methode sectie heeft te weinig paragrafen.', 'Splits de methode sectie op in meer paragrafen voor duidelijkheid.', 'section', 1, 2, None, '#FFD700'),
        (5, 'Verplichte sectie aanwezigheid: Probleemstelling', 'De probleemstelling sectie is verplicht voor dit documenttype.', 'structureel', 'document_only', 1, 'violation', 'De sectie "Probleemstelling" is niet gevonden in het document.', 'Zorg ervoor dat de sectie "Probleemstelling" duidelijk aanwezig is.', 'document', 1, None, None, '#FF0000'),
        (6, 'Sectievolgorde: Inleiding voor Methode', 'De inleiding moet voor de methodesectie komen.', 'structureel', 'document_only', 1, 'violation', 'De sectie "Methode" staat vóór de "Inleiding".', 'Controleer de volgorde van de secties. De Inleiding moet voor de Methode-sectie komen.', 'document', 1, None, None, '#FF0000')
    ]
    for crit_id, name, desc, r_type, app_scope, enabled, severity, err_msg, fix_txt, freq_unit, max_mentions, min_val, max_val, color in criteria_data:
        cursor.execute("""
            INSERT OR IGNORE INTO criteria (id, name, description, rule_type, application_scope, is_enabled, severity, error_message, fixed_feedback_text, frequency_unit, max_mentions_per, expected_value_min, expected_value_max, color)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (crit_id, name, desc, r_type, app_scope, enabled, severity, err_msg, fix_txt, freq_unit, max_mentions, min_val, max_val, color))

    # Mappings: DocumentType naar Criteria
    rapport_type_id = cursor.execute("SELECT id FROM document_types WHERE identifier = 'rapport'").fetchone()[0]
    for criteria_id in [1, 2, 3, 4, 5, 6]:
        cursor.execute("INSERT OR IGNORE INTO document_type_criteria_mappings (document_type_id, criteria_id) VALUES (?, ?)", (rapport_type_id, criteria_id))

    # Mappings: Criteria naar Specifieke Secties (IDs ophalen NA invoegen van alle secties)
    # Dit is belangrijk: zorg dat alle secties zijn ingevoegd voordat je mappings maakt.
    inleiding_id = cursor.execute("SELECT id FROM sections WHERE identifier = 'inleiding'").fetchone()[0]
    probleemstelling_id = cursor.execute("SELECT id FROM sections WHERE identifier = 'probleemanalyse'").fetchone()[0] # Koppel aan de top-level 'probleemanalyse'
    methode_id = cursor.execute("SELECT id FROM sections WHERE identifier = 'methode'").fetchone()[0]
    
    cursor.execute("INSERT OR IGNORE INTO criteria_section_mappings (criteria_id, section_id, is_excluded) VALUES (?, ?, ?)", (1, inleiding_id, 0))
    cursor.execute("INSERT OR IGNORE INTO criteria_section_mappings (criteria_id, section_id, is_excluded) VALUES (?, ?, ?)", (2, probleemstelling_id, 0)) 
    cursor.execute("INSERT OR IGNORE INTO criteria_section_mappings (criteria_id, section_id, is_excluded) VALUES (?, ?, ?)", (4, methode_id, 0))

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

# NIEUW: Functies voor sectiebeheer (voor CRUD operaties op sections tabel)
def add_section(conn: sqlite3.Connection, name: str, identifier: str, is_required: bool, parent_id: int, alternative_names_json: str, order_index: int, level: int):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sections (name, identifier, is_required, parent_id, alternative_names, order_index, level)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, identifier, is_required, parent_id, alternative_names_json, order_index, level))
    conn.commit()

def update_section(conn: sqlite3.Connection, section_id: int, name: str, identifier: str, is_required: bool, parent_id: int, alternative_names_json: str, order_index: int, level: int):
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE sections SET name = ?, identifier = ?, is_required = ?, parent_id = ?, alternative_names = ?, order_index = ?, level = ?
        WHERE id = ?
    """, (name, identifier, is_required, parent_id, alternative_names_json, order_index, level, section_id))
    conn.commit()

def delete_section(conn: sqlite3.Connection, section_id: int):
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sections WHERE id = ?", (section_id,))
    conn.commit()

def get_section_by_id(conn: sqlite3.Connection, section_id: int):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sections WHERE id = ?", (section_id,))
    return cursor.fetchone()

# NIEUW: Functies voor criteriumbeheer (voor CRUD operaties op criteria tabel)
def get_all_criteria(conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM criteria")
    return cursor.fetchall()

def add_criterion(conn: sqlite3.Connection, name: str, description: str, rule_type: str, application_scope: str, is_enabled: bool, severity: str, error_message: str, fixed_feedback_text: str, frequency_unit: str, max_mentions_per: int, expected_value_min: float, expected_value_max: float, color: str):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO criteria (name, description, rule_type, application_scope, is_enabled, severity, error_message, fixed_feedback_text, frequency_unit, max_mentions_per, expected_value_min, expected_value_max, color)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, description, rule_type, application_scope, is_enabled, severity, error_message, fixed_feedback_text, frequency_unit, max_mentions_per, expected_value_min, expected_value_max, color))
    conn.commit()

def update_criterion(conn: sqlite3.Connection, criteria_id: int, name: str, description: str, rule_type: str, application_scope: str, is_enabled: bool, severity: str, error_message: str, fixed_feedback_text: str, frequency_unit: str, max_mentions_per: int, expected_value_min: float, expected_value_max: float, color: str):
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE criteria SET name = ?, description = ?, rule_type = ?, application_scope = ?, is_enabled = ?, severity = ?, error_message = ?, fixed_feedback_text = ?, frequency_unit = ?, max_mentions_per = ?, expected_value_min = ?, expected_value_max = ?, color = ?
        WHERE id = ?
    """, (name, description, rule_type, application_scope, is_enabled, severity, error_message, fixed_feedback_text, frequency_unit, max_mentions_per, expected_value_min, expected_value_max, color, criteria_id))
    conn.commit()

def delete_criterion(conn: sqlite3.Connection, criteria_id: int):
    cursor = conn.cursor()
    cursor.execute("DELETE FROM criteria WHERE id = ?", (criteria_id,))
    conn.commit()

def get_criterion_by_id(conn: sqlite3.Connection, criteria_id: int):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM criteria WHERE id = ?", (criteria_id,))
    return cursor.fetchone()

# NIEUW: Functies voor document_types en organizations
def get_document_types(conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM document_types")
    return cursor.fetchall()

def get_organizations(conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM organizations")
    return cursor.fetchall()

def add_document(conn: sqlite3.Connection, name: str, original_filename: str, file_path: str, document_type_id: int = None, organization_id: int = None):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO documents (name, original_filename, file_path, document_type_id, organization_id, uploaded_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, original_filename, file_path, document_type_id, organization_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    return cursor.lastrowid

def get_document_by_id(conn: sqlite3.Connection, doc_id: int):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
    return cursor.fetchone()

def update_document_analysis_status(conn: sqlite3.Connection, doc_id: int, status: str, analysis_data: str = None):
    cursor = conn.cursor()
    if analysis_data:
        cursor.execute("UPDATE documents SET analysis_status = ?, analysis_data = ? WHERE id = ?", (status, analysis_data, doc_id))
    else:
        cursor.execute("UPDATE documents SET analysis_status = ? WHERE id = ?", (status, doc_id))
    conn.commit()

def get_feedback_for_document(conn: sqlite3.Connection, document_id: int):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            fi.*, 
            c.name AS criteria_name, 
            s.name AS section_name,
            c.severity AS criteria_severity,
            c.fixed_feedback_text AS criteria_fixed_feedback_text
        FROM feedback_items fi
        JOIN criteria c ON fi.criteria_id = c.id
        LEFT JOIN sections s ON fi.section_id = s.id
        WHERE fi.document_id = ?
        ORDER BY fi.generated_at DESC
    """, (document_id,))
    return cursor.fetchall()

# NIEUW: Functies voor criteria_section_mappings
def get_criterion_section_mappings(conn: sqlite3.Connection, criteria_id: int):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM criteria_section_mappings
        WHERE criteria_id = ?
    """, (criteria_id,))
    return cursor.fetchall()

def add_criterion_section_mapping(conn: sqlite3.Connection, criteria_id: int, section_id: int, is_excluded: bool, weight: float = 1.0):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO criteria_section_mappings (criteria_id, section_id, is_excluded, weight)
        VALUES (?, ?, ?, ?)
    """, (criteria_id, section_id, is_excluded, weight))
    conn.commit()

def delete_all_section_mappings_for_criterion(conn: sqlite3.Connection, criteria_id: int):
    cursor = conn.cursor()
    cursor.execute("DELETE FROM criteria_section_mappings WHERE criteria_id = ?", (criteria_id,))
    conn.commit()

def update_criterion_application_scope(conn: sqlite3.Connection, criteria_id: int, application_scope: str):
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE criteria SET application_scope = ? WHERE id = ?
    """, (application_scope, criteria_id))
    conn.commit()
