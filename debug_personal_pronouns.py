#!/usr/bin/env python3
"""
Debug script voor persoonlijk taalgebruik probleem
"""

import re
import sqlite3
import os

def debug_personal_pronouns():
    """Debug persoonlijk taalgebruik detectie"""
    
    # Verbind met database
    db_path = os.path.join('instance', 'documents.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    try:
        # Haal document content op
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.name as section_name, s.content as section_content
            FROM sections s
            WHERE s.document_id = 1
            ORDER BY s.name
        """)
        
        results = cursor.fetchall()
        
        print("=== DEBUG PERSOONLIJK TAALGEBRUIK ===\n")
        
        personal_pronouns = ['ik', 'mij', 'mijn', 'wij', 'ons', 'onze']
        
        for row in results:
            section_name = row['section_name']
            section_content = row['section_content']
            
            print(f"Sectie: {section_name}")
            print(f"Content lengte: {len(str(section_content))}")
            
            # Converteer content naar lowercase
            if isinstance(section_content, str):
                content_lower = section_content.lower()
            else:
                content_lower = str(section_content).lower()
            
            # Zoek persoonlijke voornaamwoorden
            found_pronouns = []
            for pronoun in personal_pronouns:
                # Gebruik regex voor hele woorden
                pattern = r'\b' + re.escape(pronoun) + r'\b'
                matches = re.findall(pattern, content_lower)
                if matches:
                    found_pronouns.extend(matches)
            
            if found_pronouns:
                print(f"  ❌ Persoonlijk taalgebruik gevonden: {', '.join(set(found_pronouns))}")
                # Toon context
                for pronoun in set(found_pronouns):
                    pattern = r'\b' + re.escape(pronoun) + r'\b'
                    for match in re.finditer(pattern, content_lower):
                        start = max(0, match.start() - 20)
                        end = min(len(content_lower), match.end() + 20)
                        context = content_lower[start:end]
                        print(f"    Context: ...{context}...")
            else:
                print(f"  ✅ Geen persoonlijk taalgebruik gevonden")
            
            print()
        
        # Haal criteria op
        cursor.execute("""
            SELECT id, name, description, rule_type
            FROM criteria
            WHERE name LIKE '%persoonlijk%' OR description LIKE '%persoonlijk%'
        """)
        
        criteria = cursor.fetchall()
        print("=== PERSOONLIJK TAALGEBRUIK CRITERIA ===")
        for criterion in criteria:
            print(f"ID: {criterion['id']}")
            print(f"Naam: {criterion['name']}")
            print(f"Beschrijving: {criterion['description']}")
            print(f"Type: {criterion['rule_type']}")
            print()
        
    finally:
        conn.close()

if __name__ == "__main__":
    debug_personal_pronouns() 