#!/usr/bin/env python3
"""
Test script om te controleren of sectie-content correct wordt opgeslagen en gebruikt
"""

import sqlite3
import os
import sys

# Voeg src directory toe aan Python path
sys.path.append('src')

def save_section_content(db_connection, recognized_sections):
    """Slaat de content van herkende secties op in de sections tabel"""
    cursor = db_connection.cursor()
    
    for section in recognized_sections:
        if section.get('found', False) and section.get('db_id'):
            section_id = section['db_id']
            content = section.get('content', '')
            
            # Update de content kolom voor deze sectie
            cursor.execute(
                'UPDATE sections SET content = ? WHERE id = ?',
                (content, section_id)
            )
            
            print(f"Content opgeslagen voor sectie '{section['name']}' (ID: {section_id})")
    
    # Commit wijzigingen
    db_connection.commit()
    print(f"✅ Content opgeslagen voor {len([s for s in recognized_sections if s.get('found', False)])} secties")

def get_section_content_from_db(db_connection, section_id):
    """Haalt de content van een sectie op uit de database"""
    if not section_id:
        return ""
    
    cursor = db_connection.cursor()
    cursor.execute('SELECT content FROM sections WHERE id = ?', (section_id,))
    result = cursor.fetchone()
    
    if result and result[0]:
        return result[0]
    return ""

def get_section_content(section, db_connection=None):
    """Haalt de content van een sectie op, eerst uit het geheugen, dan uit de database"""
    # Probeer eerst uit het geheugen
    content = section.get('content', '')
    if content:
        return content
    
    # Als geen content in geheugen en database verbinding beschikbaar, probeer database
    if db_connection and section.get('db_id'):
        return get_section_content_from_db(db_connection, section['db_id'])
    
    return ""

def test_section_content_analysis():
    """Test of sectie-content correct wordt opgeslagen en gebruikt"""
    
    # Pad naar de database
    db_path = os.path.join('instance', 'documents.db')
    
    if not os.path.exists(db_path):
        print(f"Database niet gevonden: {db_path}")
        return
    
    try:
        # Maak verbinding
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Test data met persoonlijk taalgebruik
        test_sections = [
            {
                'db_id': 1,
                'name': 'Inleiding',
                'found': True,
                'content': 'In dit onderzoek ga ik kijken naar het probleem. Wij denken dat dit belangrijk is. Mijn mening is dat dit anders moet.'
            },
            {
                'db_id': 2,
                'name': 'Probleemanalyse',
                'found': True,
                'content': 'Het probleem is dat wij niet weten hoe het moet. Ik denk dat dit een complexe situatie is.'
            },
            {
                'db_id': 3,
                'name': 'Doelstelling',
                'found': True,
                'content': 'Het doel is om een oplossing te vinden. Er wordt gestreefd naar verbetering.'
            }
        ]
        
        print("=== TEST SECTIE CONTENT OPSLAG ===")
        
        # Sla test content op
        save_section_content(conn, test_sections)
        
        # Controleer of content is opgeslagen
        print("\n=== CONTROLE OPGESLAGEN CONTENT ===")
        for section in test_sections:
            content = get_section_content_from_db(conn, section['db_id'])
            print(f"Sectie '{section['name']}': {content[:50]}..." if content else "Geen content")
        
        # Test de get_section_content functie
        print("\n=== TEST GET_SECTION_CONTENT FUNCTIE ===")
        for section in test_sections:
            # Test met content in geheugen
            content_memory = get_section_content(section, conn)
            print(f"Sectie '{section['name']}' (geheugen): {content_memory[:30]}...")
            
            # Test met alleen db_id (geen content in geheugen)
            section_no_content = {'db_id': section['db_id'], 'name': section['name']}
            content_db = get_section_content(section_no_content, conn)
            print(f"Sectie '{section['name']}' (database): {content_db[:30]}...")
        
        # Test persoonlijk taalgebruik detectie
        print("\n=== TEST PERSOONLIJK TAALGEBRUIK DETECTIE ===")
        personal_pronouns = ['ik', 'mij', 'mijn', 'wij', 'ons', 'onze']
        
        for section in test_sections:
            content = get_section_content(section, conn)
            found_pronouns = [p for p in personal_pronouns if p in content.lower()]
            print(f"Sectie '{section['name']}': {found_pronouns}")
        
        conn.close()
        
    except Exception as e:
        print(f"Fout bij testen: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_section_content_analysis() 