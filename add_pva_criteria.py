#!/usr/bin/env python3
"""
Script om criteria toe te voegen voor Plan van Aanpak documenten.
"""

import sqlite3
import os

def add_pva_criteria():
    """Voeg criteria toe voor Plan van Aanpak documenten."""
    
    # Database pad
    db_path = 'instance/documents.db'
    
    if not os.path.exists(db_path):
        print("❌ Database niet gevonden!")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Haal document type ID op voor Plan van Aanpak
        cursor.execute('SELECT id FROM document_types WHERE identifier = ?', ('plan_van_aanpak',))
        result = cursor.fetchone()
        
        if not result:
            print("❌ Document type 'Plan van Aanpak' niet gevonden!")
            return
        
        pva_doc_type_id = result[0]
        print(f"✅ Plan van Aanpak document type ID: {pva_doc_type_id}")
        
        # Criteria voor Plan van Aanpak
        pva_criteria = [
            {
                'name': 'Verplichte sectie: Probleemanalyse',
                'description': 'Controleert of de probleemanalyse sectie aanwezig is',
                'rule_type': 'section_presence',
                'application_scope': 'document',
                'severity': 'error',
                'error_message': 'Probleemanalyse sectie is verplicht in een Plan van Aanpak',
                'fixed_feedback_text': 'Voeg een duidelijke probleemanalyse toe',
                'color': '#F94144'
            },
            {
                'name': 'Verplichte sectie: Methode',
                'description': 'Controleert of de methode sectie aanwezig is',
                'rule_type': 'section_presence',
                'application_scope': 'document',
                'severity': 'error',
                'error_message': 'Methode sectie is verplicht in een Plan van Aanpak',
                'fixed_feedback_text': 'Voeg een duidelijke methode sectie toe',
                'color': '#F94144'
            },
            {
                'name': 'Verplichte sectie: Conclusie',
                'description': 'Controleert of de conclusie sectie aanwezig is',
                'rule_type': 'section_presence',
                'application_scope': 'document',
                'severity': 'error',
                'error_message': 'Conclusie sectie is verplicht in een Plan van Aanpak',
                'fixed_feedback_text': 'Voeg een duidelijke conclusie toe',
                'color': '#F94144'
            },
            {
                'name': 'Verplichte sectie: Literatuurlijst',
                'description': 'Controleert of de literatuurlijst sectie aanwezig is',
                'rule_type': 'section_presence',
                'application_scope': 'document',
                'severity': 'error',
                'error_message': 'Literatuurlijst sectie is verplicht in een Plan van Aanpak',
                'fixed_feedback_text': 'Voeg een literatuurlijst toe',
                'color': '#F94144'
            },
            {
                'name': 'Minimaal 100 woorden in Inleiding',
                'description': 'Controleert of de inleiding minimaal 100 woorden heeft',
                'rule_type': 'word_count',
                'application_scope': 'section',
                'severity': 'warning',
                'error_message': 'Inleiding is te kort (minder dan 100 woorden)',
                'fixed_feedback_text': 'Breid de inleiding uit met meer context en achtergrond',
                'color': '#F9C74F'
            },
            {
                'name': 'Minimaal 200 woorden in Probleemanalyse',
                'description': 'Controleert of de probleemanalyse minimaal 200 woorden heeft',
                'rule_type': 'word_count',
                'application_scope': 'section',
                'severity': 'warning',
                'error_message': 'Probleemanalyse is te kort (minder dan 200 woorden)',
                'fixed_feedback_text': 'Breid de probleemanalyse uit met meer detail en context',
                'color': '#F9C74F'
            },
            {
                'name': 'Minimaal 150 woorden in Methode',
                'description': 'Controleert of de methode minimaal 150 woorden heeft',
                'rule_type': 'word_count',
                'application_scope': 'section',
                'severity': 'warning',
                'error_message': 'Methode sectie is te kort (minder dan 150 woorden)',
                'fixed_feedback_text': 'Beschrijf de methode in meer detail',
                'color': '#F9C74F'
            },
            {
                'name': 'Geen persoonlijk taalgebruik',
                'description': 'Controleert op persoonlijk taalgebruik (ik, wij, etc.)',
                'rule_type': 'text_analysis',
                'application_scope': 'document',
                'severity': 'warning',
                'error_message': 'Persoonlijk taalgebruik gevonden in het document',
                'fixed_feedback_text': 'Vervang persoonlijk taalgebruik door objectieve formuleringen',
                'color': '#F9C74F'
            },
            {
                'name': 'SMART doelstellingen',
                'description': 'Controleert of doelstellingen SMART geformuleerd zijn',
                'rule_type': 'text_analysis',
                'application_scope': 'section',
                'severity': 'info',
                'error_message': 'Doelstellingen zijn mogelijk niet SMART geformuleerd',
                'fixed_feedback_text': 'Zorg dat doelstellingen Specifiek, Meetbaar, Acceptabel, Realistisch en Tijdsgebonden zijn',
                'color': '#84A98C'
            }
        ]
        
        # Voeg criteria toe
        added_criteria = []
        for criterion in pva_criteria:
            cursor.execute('''
                INSERT INTO criteria (
                    name, description, rule_type, application_scope, is_enabled, 
                    severity, error_message, fixed_feedback_text, color
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                criterion['name'], criterion['description'], criterion['rule_type'],
                criterion['application_scope'], 1, criterion['severity'],
                criterion['error_message'], criterion['fixed_feedback_text'], criterion['color']
            ))
            
            criterion_id = cursor.lastrowid
            
            # Koppel aan Plan van Aanpak document type
            cursor.execute('''
                INSERT INTO document_type_criteria_mappings (document_type_id, criteria_id)
                VALUES (?, ?)
            ''', (pva_doc_type_id, criterion_id))
            
            added_criteria.append(criterion['name'])
            print(f"✅ Criterium toegevoegd: {criterion['name']}")
        
        # Commit wijzigingen
        conn.commit()
        
        print(f"\n🎉 {len(added_criteria)} criteria toegevoegd voor Plan van Aanpak!")
        print("\nToegevoegde criteria:")
        for i, name in enumerate(added_criteria, 1):
            print(f"{i}. {name}")
        
        # Controleer totaal aantal criteria voor Plan van Aanpak
        cursor.execute('''
            SELECT COUNT(*) FROM criteria c
            JOIN document_type_criteria_mappings dtcm ON c.id = dtcm.criteria_id
            WHERE dtcm.document_type_id = ?
        ''', (pva_doc_type_id,))
        
        total_criteria = cursor.fetchone()[0]
        print(f"\n📊 Totaal aantal criteria voor Plan van Aanpak: {total_criteria}")
        
    except Exception as e:
        print(f"❌ Fout bij toevoegen criteria: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    print("🚀 Voeg criteria toe voor Plan van Aanpak...")
    add_pva_criteria()
    print("\n✅ Script voltooid!") 