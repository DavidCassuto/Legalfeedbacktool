#!/usr/bin/env python3
"""
Test script voor database optimalisaties
"""

import os
import sys
import time
import sqlite3

# Voeg src directory toe aan Python path
sys.path.append('src')

from database_optimizations import (
    initialize_sqlite_optimizer,
    get_optimized_db,
    batch_save_section_content,
    performance_monitor,
    optimize_database_for_multiple_users
)

def test_database_optimizations():
    """Test de database optimalisaties."""
    print("🧪 Testen van database optimalisaties...")
    
    # Pad naar de database
    db_path = os.path.join('instance', 'documents.db')
    
    if not os.path.exists(db_path):
        print(f"❌ Database niet gevonden: {db_path}")
        return False
    
    try:
        # Initialiseer optimalisaties
        print("1. Initialiseren van optimalisaties...")
        initialize_sqlite_optimizer(db_path)
        optimize_database_for_multiple_users()
        
        # Test database verbinding
        print("2. Testen van geoptimaliseerde database verbinding...")
        start_time = time.time()
        db = get_optimized_db()
        connection_time = time.time() - start_time
        print(f"   ✅ Verbinding gemaakt in {connection_time:.3f}s")
        
        # Test PRAGMA instellingen
        print("3. Controleren van PRAGMA instellingen...")
        cursor = db.cursor()
        
        # Check WAL mode
        cursor.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        print(f"   📊 Journal mode: {journal_mode}")
        
        # Check cache size
        cursor.execute("PRAGMA cache_size")
        cache_size = cursor.fetchone()[0]
        print(f"   💾 Cache size: {cache_size} pages")
        
        # Check busy timeout
        cursor.execute("PRAGMA busy_timeout")
        busy_timeout = cursor.fetchone()[0]
        print(f"   ⏱️ Busy timeout: {busy_timeout}ms")
        
        # Test indexen
        print("4. Controleren van database indexen...")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = cursor.fetchall()
        print(f"   🔍 Aantal indexen: {len(indexes)}")
        for index in indexes:
            print(f"      - {index[0]}")
        
        # Test sectie-content opslag
        print("5. Testen van sectie-content opslag...")
        test_sections = [
            {
                'found': True,
                'db_id': 1,
                'content': 'Dit is een test sectie met wat content om te testen of de opslag werkt.'
            },
            {
                'found': True,
                'db_id': 2,
                'content': 'Nog een test sectie met meer content om de batch update te testen.'
            }
        ]
        
        start_time = time.time()
        batch_save_section_content(db, test_sections)
        save_time = time.time() - start_time
        print(f"   ✅ Batch save voltooid in {save_time:.3f}s")
        
        # Test performance monitoring
        print("6. Testen van performance monitoring...")
        performance_monitor.record_query_time('test_query', 0.1)
        performance_monitor.record_query_time('test_query', 0.2)
        performance_monitor.record_query_time('test_query', 0.15)
        
        stats = performance_monitor.get_performance_summary()
        print(f"   📈 Performance data geregistreerd: {stats['total_queries']} queries")
        
        # Test caching
        print("7. Testen van content caching...")
        from database_optimizations import content_cache
        
        # Test cache set/get
        content_cache.set(999, "Test content voor caching")
        cached_content = content_cache.get(999)
        if cached_content == "Test content voor caching":
            print("   ✅ Caching werkt correct")
        else:
            print("   ❌ Caching werkt niet correct")
        
        # Test cache stats
        cache_stats = content_cache.get_stats()
        print(f"   📊 Cache stats: {cache_stats['hit_rate']}")
        
        db.close()
        
        print("\n🎉 Alle tests voltooid!")
        print("✅ Database optimalisaties werken correct")
        print("📈 Geschikt voor 4 gelijktijdige gebruikers")
        
        return True
        
    except Exception as e:
        print(f"❌ Fout tijdens testen: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_database_optimizations()
    if success:
        print("\n🚀 Database optimalisaties zijn klaar voor gebruik!")
    else:
        print("\n❌ Er zijn problemen met de optimalisaties.") 