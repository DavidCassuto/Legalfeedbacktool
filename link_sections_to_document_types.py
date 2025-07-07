#!/usr/bin/env python3
"""
Script om secties te koppelen aan document types in de nieuwe database structuur.
"""

import sqlite3
import os

def link_sections_to_document_types():
    """Koppel secties aan document types."""
    
    db_path = 'instance/documents.db'
    
    if not os.path.exists(db_path):
        print("❌ Database niet gevonden!")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        print("🔧 Koppel secties aan document types...")
        
        # Haal alle document types op
        cursor.execute('SELECT id, name, identifier FROM document_types')
        document_types = cursor.fetchall()
        
        # Haal alle secties op
        cursor.execute('SELECT id, name, identifier FROM sections')
        sections = cursor.fetchall()
        
        print(f"📄 Gevonden document types: {len(document_types)}")
        print(f"📋 Gevonden secties: {len(sections)}")
        
        # Mapping van document types naar secties
        document_type_sections = {
            # Plan van Aanpak
            3: [
                ('inleiding', 1, False),
                ('leeswijzer', 2, False),
                ('probleemanalyse', 3, True),
                ('handelingsprobleem', 4, False),
                ('doelstelling', 5, False),
                ('output', 6, False),
                ('outcome', 7, False),
                ('hoofd_deelvragen', 8, False),
                ('hoofdvraag', 9, False),
                ('deelvragen', 10, False),
                ('theorie_achtergrond', 11, False),
                ('juridische_context', 12, False),
                ('methode', 13, True),
                ('logboek_planning', 14, False),
                ('risicoanalyse', 15, False),
                ('resultaten', 16, False),
                ('discussie', 17, False),
                ('conclusie', 18, True),
                ('aanbevelingen', 19, False),
                ('literatuur', 20, True),
                ('bijlagen', 21, False)
            ],
            # Rapport
            1: [
                ('inleiding', 1, False),
                ('probleemanalyse', 2, False),
                ('methode', 3, False),
                ('resultaten', 4, False),
                ('discussie', 5, False),
                ('conclusie', 6, False),
                ('literatuur', 7, False)
            ],
            # Scriptie
            2: [
                ('inleiding', 1, False),
                ('probleemanalyse', 2, False),
                ('methode', 3, False),
                ('resultaten', 4, False),
                ('discussie', 5, False),
                ('conclusie', 6, False),
                ('literatuur', 7, False)
            ]
        }
        
        # Koppel secties aan document types
        total_links = 0
        for doc_type_id, section_mappings in document_type_sections.items():
            print(f"\n📄 Koppel secties aan document type ID {doc_type_id}...")
            
            for section_identifier, order_index, is_required in section_mappings:
                # Zoek sectie op identifier
                cursor.execute('SELECT id FROM sections WHERE identifier = ?', (section_identifier,))
                section_result = cursor.fetchone()
                
                if section_result:
                    section_id = section_result[0]
                    
                    # Controleer of koppeling al bestaat
                    cursor.execute('''
                        SELECT id FROM document_type_sections 
                        WHERE document_type_id = ? AND section_id = ?
                    ''', (doc_type_id, section_id))
                    
                    if not cursor.fetchone():
                        # Voeg koppeling toe
                        cursor.execute('''
                            INSERT INTO document_type_sections (document_type_id, section_id, is_required, order_index)
                            VALUES (?, ?, ?, ?)
                        ''', (doc_type_id, section_id, is_required, order_index))
                        total_links += 1
                        print(f"   ✅ {section_identifier} (order: {order_index}, required: {is_required})")
                    else:
                        print(f"   ℹ️ {section_identifier} (al gekoppeld)")
                else:
                    print(f"   ❌ Sectie '{section_identifier}' niet gevonden")
        
        # Commit wijzigingen
        conn.commit()
        print(f"\n🎉 {total_links} sectie koppelingen toegevoegd!")
        
        # Controleer resultaat
        cursor.execute('SELECT COUNT(*) FROM document_type_sections')
        total_mappings = cursor.fetchone()[0]
        print(f"📊 Totaal aantal document type sectie koppelingen: {total_mappings}")
        
        # Toon koppelingen per document type
        for doc_type_id in document_type_sections.keys():
            cursor.execute('''
                SELECT s.name, dts.is_required, dts.order_index
                FROM sections s
                JOIN document_type_sections dts ON s.id = dts.section_id
                WHERE dts.document_type_id = ?
                ORDER BY dts.order_index
            ''', (doc_type_id,))
            
            sections = cursor.fetchall()
            print(f"\n📄 Document type ID {doc_type_id} heeft {len(sections)} secties:")
            for section in sections:
                required_text = " (verplicht)" if section[1] else ""
                print(f"   - {section[0]}{required_text}")
        
    except Exception as e:
        print(f"❌ Fout bij koppelen secties: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    print("🚀 Koppel secties aan document types...")
    link_sections_to_document_types()
    print("\n✅ Sectie koppeling voltooid!") 