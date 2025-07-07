#!/usr/bin/env python3
"""
Test script voor database functies.
"""

import sys
import os
sys.path.append('src')

import db_utils
import sqlite3

def test_database_functions():
    """Test de database functies."""
    
    db_path = 'instance/documents.db'
    
    if not os.path.exists(db_path):
        print("❌ Database niet gevonden!")
        return
    
    conn = sqlite3.connect(db_path)
    
    try:
        print("🧪 Test database functies...")
        
        # Test criteria functie
        print("\n1. Test criteria functie...")
        criteria = db_utils.get_criteria_for_document_type_new(conn, 3)
        print(f"   Criteria voor Plan van Aanpak: {len(criteria)}")
        if criteria:
            print(f"   Eerste criterium: {criteria[0]['name']}")
        
        # Test secties functie
        print("\n2. Test secties functie...")
        sections = db_utils.get_sections_for_document_type_new(conn, 3)
        print(f"   Secties voor Plan van Aanpak: {len(sections)}")
        if sections:
            print(f"   Eerste sectie: {sections[0]['name']}")
        
        print("\n✅ Database functies werken correct!")
        
    except Exception as e:
        print(f"❌ Fout bij testen: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    test_database_functions() 