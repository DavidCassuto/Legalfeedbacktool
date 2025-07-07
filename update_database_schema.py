#!/usr/bin/env python3
"""
Script om de database schema bij te werken voor betere multi-tenant ondersteuning.
"""

import sqlite3
import os

def update_database_schema():
    """Update de database schema voor betere organisatie en criteria mapping."""
    
    db_path = 'instance/documents.db'
    
    if not os.path.exists(db_path):
        print("❌ Database niet gevonden!")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        print("🔧 Database schema bijwerken...")
        
        # 1. Voeg organisatie_id toe aan document_types
        print("1. Voeg organisatie_id toe aan document_types...")
        try:
            cursor.execute('ALTER TABLE document_types ADD COLUMN organization_id INTEGER REFERENCES organizations(id)')
            print("   ✅ Kolom toegevoegd")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print("   ℹ️ Kolom bestaat al")
            else:
                raise
        
        # 2. Voeg organisatie_id toe aan criteria (voor organisatie-specifieke criteria)
        print("2. Voeg organisatie_id toe aan criteria...")
        try:
            cursor.execute('ALTER TABLE criteria ADD COLUMN organization_id INTEGER REFERENCES organizations(id)')
            print("   ✅ Kolom toegevoegd")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print("   ℹ️ Kolom bestaat al")
            else:
                raise
        
        # 3. Voeg organisatie_id toe aan sections
        print("3. Voeg organisatie_id toe aan sections...")
        try:
            cursor.execute('ALTER TABLE sections ADD COLUMN organization_id INTEGER REFERENCES organizations(id)')
            print("   ✅ Kolom toegevoegd")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print("   ℹ️ Kolom bestaat al")
            else:
                raise
        
        # 4. Maak nieuwe tabel voor criteria templates (herbruikbare criteria)
        print("4. Maak criteria_templates tabel...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS criteria_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                rule_type TEXT NOT NULL,
                application_scope TEXT NOT NULL,
                severity TEXT NOT NULL,
                error_message TEXT,
                fixed_feedback_text TEXT,
                color TEXT,
                is_global BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("   ✅ Tabel aangemaakt")
        
        # 5. Maak nieuwe tabel voor document_type_sections (koppeling document types aan secties)
        print("5. Maak document_type_sections tabel...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS document_type_sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_type_id INTEGER NOT NULL,
                section_id INTEGER NOT NULL,
                is_required BOOLEAN DEFAULT 0,
                order_index INTEGER DEFAULT 0,
                FOREIGN KEY (document_type_id) REFERENCES document_types (id),
                FOREIGN KEY (section_id) REFERENCES sections (id),
                UNIQUE(document_type_id, section_id)
            )
        ''')
        print("   ✅ Tabel aangemaakt")
        
        # 6. Maak nieuwe tabel voor criteria_instances (instanties van criteria templates)
        print("6. Maak criteria_instances tabel...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS criteria_instances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id INTEGER,
                document_type_id INTEGER NOT NULL,
                organization_id INTEGER,
                name TEXT NOT NULL,
                description TEXT,
                rule_type TEXT NOT NULL,
                application_scope TEXT NOT NULL,
                severity TEXT NOT NULL,
                error_message TEXT,
                fixed_feedback_text TEXT,
                color TEXT,
                is_enabled BOOLEAN DEFAULT 1,
                custom_parameters TEXT, -- JSON voor aangepaste parameters
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (template_id) REFERENCES criteria_templates (id),
                FOREIGN KEY (document_type_id) REFERENCES document_types (id),
                FOREIGN KEY (organization_id) REFERENCES organizations (id)
            )
        ''')
        print("   ✅ Tabel aangemaakt")
        
        # 7. Maak nieuwe tabel voor criteria_section_mappings (koppeling criteria aan secties)
        print("7. Maak criteria_section_mappings tabel...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS criteria_section_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                criteria_instance_id INTEGER NOT NULL,
                section_id INTEGER NOT NULL,
                FOREIGN KEY (criteria_instance_id) REFERENCES criteria_instances (id),
                FOREIGN KEY (section_id) REFERENCES sections (id),
                UNIQUE(criteria_instance_id, section_id)
            )
        ''')
        print("   ✅ Tabel aangemaakt")
        
        # 8. Migreer bestaande data
        print("8. Migreer bestaande data...")
        
        # Migreer bestaande criteria naar criteria_templates
        cursor.execute('SELECT COUNT(*) FROM criteria_templates')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO criteria_templates (name, description, rule_type, application_scope, severity, error_message, fixed_feedback_text, color)
                SELECT DISTINCT name, description, rule_type, application_scope, severity, error_message, fixed_feedback_text, color
                FROM criteria
            ''')
            print("   ✅ Bestaande criteria gemigreerd naar templates")
        
        # Migreer bestaande document_type_criteria_mappings naar criteria_instances
        cursor.execute('SELECT COUNT(*) FROM criteria_instances')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO criteria_instances (template_id, document_type_id, name, description, rule_type, application_scope, severity, error_message, fixed_feedback_text, color, is_enabled)
                SELECT 
                    ct.id as template_id,
                    dtcm.document_type_id,
                    c.name,
                    c.description,
                    c.rule_type,
                    c.application_scope,
                    c.severity,
                    c.error_message,
                    c.fixed_feedback_text,
                    c.color,
                    c.is_enabled
                FROM criteria c
                JOIN document_type_criteria_mappings dtcm ON c.id = dtcm.criteria_id
                JOIN criteria_templates ct ON ct.name = c.name AND ct.rule_type = c.rule_type
            ''')
            print("   ✅ Bestaande criteria mappings gemigreerd")
        
        # Commit wijzigingen
        conn.commit()
        print("\n🎉 Database schema succesvol bijgewerkt!")
        
        # Toon nieuwe structuur
        print("\n📊 Nieuwe database structuur:")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = cursor.fetchall()
        for table in tables:
            print(f"  - {table[0]}")
        
    except Exception as e:
        print(f"❌ Fout bij bijwerken schema: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    print("🚀 Database schema bijwerken voor betere multi-tenant ondersteuning...")
    update_database_schema()
    print("\n✅ Schema update voltooid!") 