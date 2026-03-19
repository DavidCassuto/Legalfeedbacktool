#!/usr/bin/env python3
"""
Script om de inhoud van de sections tabel te controleren
"""

import sqlite3
import os

def check_sections_table():
    """Controleer de inhoud van de sections tabel"""
    
    # Pad naar de database
    db_path = os.path.join('instance', 'documents.db')
    
    if not os.path.exists(db_path):
        print(f"Database niet gevonden: {db_path}")
        return
    
    try:
        # Maak verbinding
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Check tabel structuur
        print("=== TABEL STRUCTUUR ===")
        cursor.execute("PRAGMA table_info(sections)")
        columns = cursor.fetchall()
        
        print("Kolommen in sections tabel:")
        for col in columns:
            print(f"  - {col['name']} ({col['type']})")
        
        # Check of content kolom bestaat
        content_exists = any(col['name'] == 'content' for col in columns)
        print(f"\nContent kolom aanwezig: {content_exists}")
        
        # Haal alle secties op
        print("\n=== SECTIES IN DATABASE ===")
        cursor.execute("SELECT * FROM sections LIMIT 5")
        sections = cursor.fetchall()
        
        if sections:
            print(f"Aantal secties gevonden: {len(sections)}")
            print("\nEerste 5 secties:")
            for i, section in enumerate(sections, 1):
                print(f"\nSectie {i}:")
                for col in columns:
                    col_name = col['name']
                    value = section[col_name]
                    if col_name == 'content' and value:
                        # Toon eerste 100 karakters van content
                        preview = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                        print(f"  {col_name}: {preview}")
                    else:
                        print(f"  {col_name}: {value}")
        else:
            print("Geen secties gevonden in database")
        
        # Check documenten
        print("\n=== DOCUMENTEN IN DATABASE ===")
        cursor.execute("SELECT id, filename, file_path FROM documents LIMIT 3")
        documents = cursor.fetchall()
        
        if documents:
            print(f"Aantal documenten gevonden: {len(documents)}")
            for doc in documents:
                print(f"  ID: {doc['id']}, Bestand: {doc['filename']}")
        else:
            print("Geen documenten gevonden")
        
        conn.close()
        
    except Exception as e:
        print(f"Fout bij controleren database: {e}")

if __name__ == "__main__":
    check_sections_table() 