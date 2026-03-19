#!/usr/bin/env python3
"""
Debug script om feedback generatie te testen.
"""

import sqlite3
import json
import sys
import os

# Voeg src directory toe aan path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from analysis import criterion_checking
from analysis import document_parsing
from analysis import section_recognition

def debug_feedback_generation():
    """Test feedback generatie met een bestaand document."""
    
    # Verbind met database
    conn = sqlite3.connect('feedback_tool.db')
    conn.row_factory = sqlite3.Row
    
    try:
        # Haal een document op dat al geanalyseerd is
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.*, dt.name as document_type_name 
            FROM documents d 
            JOIN document_types dt ON d.document_type_id = dt.id 
            WHERE d.analysis_status = 'completed' 
            LIMIT 1
        """)
        
        document = cursor.fetchone()
        
        if not document:
            print("❌ Geen geanalyseerde documenten gevonden!")
            return
        
        print(f"📄 Test document: {document['original_filename']}")
        print(f"📊 Document type: {document['document_type_name']}")
        
        # Haal analysis data op
        if not document['analysis_data']:
            print("❌ Geen analysis data gevonden!")
            return
        
        analysis_data = json.loads(document['analysis_data'])
        print(f"📈 Analysis data keys: {list(analysis_data.keys())}")
        
        # Check feedback
        feedback_items = analysis_data.get('feedback', [])
        print(f"🔍 Aantal feedback items: {len(feedback_items)}")
        
        if feedback_items:
            print("\n📋 Feedback items:")
            for i, item in enumerate(feedback_items[:5]):  # Toon eerste 5
                print(f"  {i+1}. {item.get('criteria_name', 'Onbekend')} - {item.get('status', 'unknown')}")
                print(f"     Sectie: {item.get('section_name', 'Onbekend')}")
                print(f"     Bericht: {item.get('message', 'Geen bericht')[:100]}...")
        else:
            print("❌ Geen feedback items gevonden!")
            
            # Test feedback generatie
            print("\n🧪 Test feedback generatie...")
            
            # Haal criteria op
            cursor.execute("SELECT * FROM criteria WHERE is_enabled = 1")
            criteria = [dict(row) for row in cursor.fetchall()]
            print(f"📋 Aantal actieve criteria: {len(criteria)}")
            
            # Parse document opnieuw
            if os.path.exists(document['file_path']):
                print("📖 Document parsen...")
                full_text, paragraphs, headings = document_parsing.parse_document(document['file_path'])
                print(f"   Tekst lengte: {len(full_text)} karakters")
                print(f"   Aantal paragrafen: {len(paragraphs)}")
                print(f"   Aantal headings: {len(headings)}")
                
                # Haal secties op
                cursor.execute("""
                    SELECT id, name, level, identifier, is_required, parent_id, alternative_names, order_index 
                    FROM sections 
                    WHERE document_type_id = ? 
                    ORDER BY order_index
                """, (document['document_type_id'],))
                expected_sections = [dict(row) for row in cursor.fetchall()]
                print(f"📋 Aantal verwachte secties: {len(expected_sections)}")
                
                # Herken secties
                print("🔍 Sectie herkenning...")
                recognized_sections = section_recognition.recognize_and_enrich_sections(
                    full_text, paragraphs, headings, expected_sections
                )
                print(f"   Aantal herkende secties: {len(recognized_sections)}")
                
                # Genereer feedback
                print("🎯 Feedback generatie...")
                feedback = criterion_checking.generate_feedback(
                    full_text, recognized_sections, criteria, conn, 
                    document['id'], document['document_type_id']
                )
                print(f"   Aantal gegenereerde feedback items: {len(feedback)}")
                
                if feedback:
                    print("\n✅ Feedback gegenereerd!")
                    for i, item in enumerate(feedback[:3]):
                        print(f"  {i+1}. {item.get('criteria_name', 'Onbekend')} - {item.get('status', 'unknown')}")
                else:
                    print("❌ Geen feedback gegenereerd!")
            else:
                print(f"❌ Document bestand niet gevonden: {document['file_path']}")
        
    except Exception as e:
        print(f"❌ Fout: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        conn.close()

if __name__ == "__main__":
    debug_feedback_generation() 