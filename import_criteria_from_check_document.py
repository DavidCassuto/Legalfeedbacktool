#!/usr/bin/env python3
"""
Script om criteria uit check_document.py te importeren in de huidige database.
"""

import sqlite3
import os
from datetime import datetime

def import_criteria_from_check_document():
    """Importeer criteria uit check_document.py naar de huidige database."""
    
    # Database pad
    db_path = "instance/documents.db"
    
    if not os.path.exists(db_path):
        print(f"Database niet gevonden: {db_path}")
        return
    
    # Criteria uit check_document.py geëxtraheerd
    criteria_data = [
        {
            'name': 'Titel regel',
            'description': 'Controleert of de titel specifiek en informatief is, en of het lettertype groot genoeg is (minimaal 18pt).',
            'rule_type': 'structureel',
            'application_scope': 'document_only',
            'severity': 'warning',
            'error_message': 'De titel is te algemeen of heeft een te klein lettertype.',
            'fixed_feedback_text': 'Gebruik een specifieke en informatieve titel met minimaal 18pt lettertype.',
            'frequency_unit': 'document',
            'max_mentions_per': 1,
            'expected_value_min': None,
            'expected_value_max': None,
            'color': '#FFD700'
        },
        {
            'name': 'Wettekst niet letterlijk citeren',
            'description': 'Controleert of wetteksten letterlijk worden geciteerd (artikel verwijzingen).',
            'rule_type': 'tekstueel',
            'application_scope': 'all',
            'severity': 'warning',
            'error_message': 'Wettekst niet letterlijk citeren.',
            'fixed_feedback_text': 'Parafraseer wetteksten in plaats van ze letterlijk te citeren.',
            'frequency_unit': 'section',
            'max_mentions_per': 3,
            'expected_value_min': None,
            'expected_value_max': None,
            'color': '#FFA500'
        },
        {
            'name': 'Geen persoonlijk taalgebruik',
            'description': 'Controleert op gebruik van persoonlijke voornaamwoorden (ik, mij, me).',
            'rule_type': 'tekstueel',
            'application_scope': 'all',
            'severity': 'warning',
            'error_message': 'Schrijf dit hele document in een zakelijke stijl. Dat betekent geen ik of mij of me.',
            'fixed_feedback_text': 'Hanteer een zakelijke schrijfstijl zonder persoonlijke voornaamwoorden.',
            'frequency_unit': 'document',
            'max_mentions_per': 1,
            'expected_value_min': None,
            'expected_value_max': None,
            'color': '#FFD700'
        },
        {
            'name': 'Deelvragen structuur',
            'description': 'Controleert of deelvragen niet uit twee aparte hoofdzinnen bestaan.',
            'rule_type': 'structureel',
            'application_scope': 'specific_sections',
            'severity': 'warning',
            'error_message': 'Een deelvraag mag niet uit twee aparte hoofdzinnen bestaan.',
            'fixed_feedback_text': 'Houd elke deelvraag als één enkele hoofdzin.',
            'frequency_unit': 'section',
            'max_mentions_per': 5,
            'expected_value_min': None,
            'expected_value_max': None,
            'color': '#FFD700'
        },
        {
            'name': 'Inleidende zinnen in 1.3',
            'description': 'Controleert of er inleidende zinnen zijn voor de eerste vraag in sectie 1.3.',
            'rule_type': 'structureel',
            'application_scope': 'specific_sections',
            'severity': 'info',
            'error_message': 'Geen inleidende zinnen gevonden voor de eerste vraag in sectie 1.3.',
            'fixed_feedback_text': 'Voeg inleidende zinnen toe voor de eerste vraag in sectie 1.3.',
            'frequency_unit': 'section',
            'max_mentions_per': 1,
            'expected_value_min': None,
            'expected_value_max': None,
            'color': '#87CEEB'
        },
        {
            'name': 'Doelstelling, Output, Outcome in 1.4',
            'description': 'Controleert of sectie 1.4 de elementen Doelstelling, Output en Outcome bevat.',
            'rule_type': 'structureel',
            'application_scope': 'specific_sections',
            'severity': 'warning',
            'error_message': 'Doelstelling, Output of Outcome ontbreekt in sectie 1.4.',
            'fixed_feedback_text': 'Zorg dat sectie 1.4 Doelstelling, Output en Outcome bevat.',
            'frequency_unit': 'section',
            'max_mentions_per': 3,
            'expected_value_min': None,
            'expected_value_max': None,
            'color': '#FFD700'
        },
        {
            'name': 'Paragraaf lengte',
            'description': 'Controleert of paragrafen niet te kort (150-350 tekens) of te lang (>1200 tekens) zijn.',
            'rule_type': 'structureel',
            'application_scope': 'all',
            'severity': 'warning',
            'error_message': 'Paragraaf is te kort of te lang.',
            'fixed_feedback_text': 'Houd paragrafen tussen 350 en 1200 tekens voor optimale leesbaarheid.',
            'frequency_unit': 'paragraph',
            'max_mentions_per': 10,
            'expected_value_min': 350,
            'expected_value_max': 1200,
            'color': '#FFD700'
        },
        {
            'name': 'Alinea scheiding',
            'description': 'Controleert of er exact één witregel tussen paragrafen staat.',
            'rule_type': 'structureel',
            'application_scope': 'all',
            'severity': 'warning',
            'error_message': 'Onjuiste alineascheiding: gebruik exact één witregel.',
            'fixed_feedback_text': 'Zorg voor exact één witregel tussen paragrafen.',
            'frequency_unit': 'document',
            'max_mentions_per': 5,
            'expected_value_min': None,
            'expected_value_max': None,
            'color': '#FFD700'
        },
        {
            'name': 'AI analyse 1.1 en 1.2',
            'description': 'AI-gebaseerde analyse van de juridische probleembeschrijving en relevantie.',
            'rule_type': 'inhoudelijk',
            'application_scope': 'specific_sections',
            'severity': 'info',
            'error_message': 'AI analyse voor sectie 1.1 en 1.2.',
            'fixed_feedback_text': 'Verbeter de juridische probleembeschrijving en relevantie.',
            'frequency_unit': 'section',
            'max_mentions_per': 1,
            'expected_value_min': None,
            'expected_value_max': None,
            'color': '#87CEEB'
        },
        {
            'name': 'AI analyse 1.3 vragen',
            'description': 'AI-gebaseerde analyse van de onderzoeksvragen in sectie 1.3.',
            'rule_type': 'inhoudelijk',
            'application_scope': 'specific_sections',
            'severity': 'info',
            'error_message': 'AI analyse voor sectie 1.3 vragen.',
            'fixed_feedback_text': 'Verbeter de formulering van de onderzoeksvragen.',
            'frequency_unit': 'section',
            'max_mentions_per': 1,
            'expected_value_min': None,
            'expected_value_max': None,
            'color': '#87CEEB'
        },
        {
            'name': 'AI analyse hoofdstuk 2',
            'description': 'AI-gebaseerde analyse van de juridische context in hoofdstuk 2.',
            'rule_type': 'inhoudelijk',
            'application_scope': 'specific_sections',
            'severity': 'info',
            'error_message': 'AI analyse voor hoofdstuk 2 juridische context.',
            'fixed_feedback_text': 'Verbeter de juridische context beschrijving.',
            'frequency_unit': 'section',
            'max_mentions_per': 1,
            'expected_value_min': None,
            'expected_value_max': None,
            'color': '#87CEEB'
        }
    ]
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Haal document type ID op voor "Plan van Aanpak"
        cursor.execute("SELECT id FROM document_types WHERE identifier = 'plan_van_aanpak' OR name LIKE '%Plan van Aanpak%'")
        result = cursor.fetchone()
        
        if not result:
            print("Document type 'Plan van Aanpak' niet gevonden. Maak eerst het document type aan.")
            return
        
        document_type_id = result[0]
        print(f"Document type ID: {document_type_id}")
        
        # Controleer welke criteria al bestaan
        existing_criteria = cursor.execute("SELECT name FROM criteria").fetchall()
        existing_names = {row[0] for row in existing_criteria}
        
        imported_count = 0
        
        for criterion in criteria_data:
            if criterion['name'] in existing_names:
                print(f"Skipping existing criterion: {criterion['name']}")
                continue
            
            # Voeg criterium toe
            cursor.execute("""
                INSERT INTO criteria (
                    name, description, rule_type, application_scope, is_enabled, severity,
                    error_message, fixed_feedback_text, frequency_unit, max_mentions_per,
                    expected_value_min, expected_value_max, color
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                criterion['name'], criterion['description'], criterion['rule_type'], 
                criterion['application_scope'], 1, criterion['severity'],
                criterion['error_message'], criterion['fixed_feedback_text'], 
                criterion['frequency_unit'], criterion['max_mentions_per'],
                criterion['expected_value_min'], criterion['expected_value_max'], 
                criterion['color']
            ))
            
            criterion_id = cursor.lastrowid
            
            # Voeg mapping toe aan document type
            cursor.execute(
                'INSERT INTO document_type_criteria_mappings (document_type_id, criteria_id) VALUES (?, ?)',
                (document_type_id, criterion_id)
            )
            
            imported_count += 1
            print(f"Imported: {criterion['name']}")
        
        conn.commit()
        print(f"\n✅ Succesvol {imported_count} criteria geïmporteerd!")
        
        # Toon alle criteria
        cursor.execute("""
            SELECT c.name, c.rule_type, c.severity, dt.name as document_type
            FROM criteria c
            JOIN document_type_criteria_mappings dtcm ON c.id = dtcm.criteria_id
            JOIN document_types dt ON dtcm.document_type_id = dt.id
            ORDER BY c.name
        """)
        
        print("\n📋 Alle criteria in database:")
        for row in cursor.fetchall():
            print(f"  - {row[0]} ({row[1]}, {row[2]}) -> {row[3]}")
        
    except Exception as e:
        print(f"❌ Fout bij importeren: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    print("🚀 Importeren van criteria uit check_document.py...")
    import_criteria_from_check_document() 