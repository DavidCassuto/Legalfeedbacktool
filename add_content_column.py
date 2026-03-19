#!/usr/bin/env python3
"""
Script om de content kolom toe te voegen aan de sections tabel
"""

import sqlite3
import os

def add_content_column():
    """Voeg content kolom toe aan sections tabel"""
    
    # Pad naar de database
    db_path = os.path.join('instance', 'documents.db')
    
    if not os.path.exists(db_path):
        print(f"Database niet gevonden: {db_path}")
        return
    
    try:
        # Maak verbinding
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check of content kolom al bestaat
        cursor.execute("PRAGMA table_info(sections)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        if 'content' in column_names:
            print("Content kolom bestaat al in sections tabel")
            return
        
        # Voeg content kolom toe
        print("Voeg content kolom toe aan sections tabel...")
        cursor.execute("ALTER TABLE sections ADD COLUMN content TEXT")
        
        # Commit wijzigingen
        conn.commit()
        print("✅ Content kolom succesvol toegevoegd aan sections tabel")
        
        # Controleer resultaat
        cursor.execute("PRAGMA table_info(sections)")
        columns = cursor.fetchall()
        print("\nNieuwe tabel structuur:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
        
        conn.close()
        
    except Exception as e:
        print(f"Fout bij toevoegen content kolom: {e}")

if __name__ == "__main__":
    add_content_column() 