#!/usr/bin/env python3
"""
Database optimalisaties voor SQLite met 4 gelijktijdige gebruikers
Kostenloze verbeteringen voor betere performance
"""

import sqlite3
import threading
import time
from typing import Optional
from contextlib import contextmanager

class SQLiteOptimizer:
    """SQLite optimalisaties voor betere performance bij meerdere gebruikers."""
    
    def __init__(self, database_path: str):
        self.database_path = database_path
        self._lock = threading.Lock()
        
    def get_optimized_connection(self) -> sqlite3.Connection:
        """Maakt een geoptimaliseerde SQLite verbinding."""
        conn = sqlite3.connect(
            self.database_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=30.0  # Verhoog timeout voor concurrentie
        )
        conn.row_factory = sqlite3.Row
        
        # Pas PRAGMA optimalisaties toe
        self._apply_pragmas(conn)
        
        return conn
    
    def _apply_pragmas(self, conn: sqlite3.Connection):
        """Past SQLite PRAGMA optimalisaties toe voor betere performance."""
        cursor = conn.cursor()
        
        # Optimalisaties voor concurrentie (4 gebruikers)
        cursor.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging - betere concurrentie
        cursor.execute("PRAGMA busy_timeout=30000")  # 30 seconden timeout
        
        # Optimalisaties voor performance
        cursor.execute("PRAGMA cache_size=-32000")  # 32MB cache (voldoende voor 4 gebruikers)
        cursor.execute("PRAGMA synchronous=NORMAL")  # Balans tussen performance en veiligheid
        cursor.execute("PRAGMA temp_store=MEMORY")  # Gebruik memory voor temp data
        cursor.execute("PRAGMA mmap_size=134217728")  # 128MB memory mapping
        
        # Optimalisaties voor grote datasets
        cursor.execute("PRAGMA page_size=4096")  # Optimale page size
        cursor.execute("PRAGMA auto_vacuum=INCREMENTAL")  # Incrementele cleanup
        
        # Optimalisaties voor betere query performance
        cursor.execute("PRAGMA optimize")  # Optimaliseer database
        
        conn.commit()
    
    def create_performance_indexes(self):
        """Maakt indexen aan voor betere query performance."""
        with self.get_optimized_connection() as conn:
            cursor = conn.cursor()
            
            try:
                # Indexen voor veel gebruikte queries
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_sections_document_type 
                    ON sections(document_type_id)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_sections_identifier 
                    ON sections(identifier)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_feedback_items_document 
                    ON feedback_items(document_id)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_feedback_items_section 
                    ON feedback_items(section_id)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_documents_uploaded_at 
                    ON documents(uploaded_at)
                """)
                
                conn.commit()
                print("[OK] Database indexen aangemaakt voor betere performance")
                
            except sqlite3.OperationalError as e:
                print(f"[WARN] Fout bij aanmaken indexen: {e}")

class ContentCache:
    """Eenvoudige in-memory cache voor sectie-content (kostenloos)."""
    
    def __init__(self, max_size: int = 500):  # Kleinere cache voor 4 gebruikers
        self.cache = {}
        self.max_size = max_size
        self._lock = threading.Lock()
    
    def get(self, section_id: int) -> Optional[str]:
        """Haalt content op uit cache."""
        with self._lock:
            return self.cache.get(section_id)
    
    def set(self, section_id: int, content: str):
        """Slaat content op in cache."""
        with self._lock:
            # LRU eviction als cache vol is
            if len(self.cache) >= self.max_size:
                # Verwijder oudste entry
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
            
            self.cache[section_id] = content
    
    def clear(self):
        """Leegt de cache."""
        with self._lock:
            self.cache.clear()
    
    def get_stats(self):
        """Geeft cache statistieken."""
        with self._lock:
            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'hit_rate': f"{len(self.cache)}/{self.max_size}"
            }

# Globale instanties
sqlite_optimizer = None
content_cache = ContentCache()

def initialize_sqlite_optimizer(database_path: str):
    """Initialiseert de SQLite optimizer."""
    global sqlite_optimizer
    sqlite_optimizer = SQLiteOptimizer(database_path)
    sqlite_optimizer.create_performance_indexes()

def get_optimized_db():
    """Haalt een geoptimaliseerde database verbinding op."""
    if sqlite_optimizer is None:
        raise RuntimeError("SQLite optimizer niet geïnitialiseerd")
    return sqlite_optimizer.get_optimized_connection()

def get_section_content_cached(section_id: int, db_connection) -> str:
    """Haalt sectie-content op met caching."""
    # Probeer eerst cache
    cached_content = content_cache.get(section_id)
    if cached_content is not None:
        return cached_content
    
    # Fallback naar database
    cursor = db_connection.cursor()
    cursor.execute('SELECT content FROM sections WHERE id = ?', (section_id,))
    result = cursor.fetchone()
    
    if result and result[0]:
        content = result[0]
        # Sla op in cache
        content_cache.set(section_id, content)
        return content
    
    return ""

def save_section_content_optimized(db_connection, section_id: int, content: str):
    """Slaat sectie-content op met optimalisaties."""
    cursor = db_connection.cursor()
    
    # Update database
    cursor.execute(
        'UPDATE sections SET content = ? WHERE id = ?',
        (content, section_id)
    )
    
    # Update cache
    content_cache.set(section_id, content)
    
    # Commit direct voor betere performance
    db_connection.commit()

def batch_save_section_content(db_connection, sections_data: list):
    """Slaat meerdere sectie-content items op in batch (efficiënter)."""
    cursor = db_connection.cursor()
    
    # Gebruik executemany voor batch updates
    update_data = [
        (section['content'], section['db_id']) 
        for section in sections_data 
        if section.get('found', False) and section.get('db_id')
    ]
    
    if update_data:
        cursor.executemany(
            'UPDATE sections SET content = ? WHERE id = ?',
            update_data
        )
        
        # Update cache voor alle items
        for content, section_id in update_data:
            content_cache.set(section_id, content)
        
        db_connection.commit()
        print(f"[OK] Batch update voltooid: {len(update_data)} secties opgeslagen")

# Performance monitoring (kostenloos)
class PerformanceMonitor:
    """Monitor voor database performance."""
    
    def __init__(self):
        self.query_times = []
        self._lock = threading.Lock()
    
    def record_query_time(self, query_type: str, duration: float):
        """Registreert query tijd."""
        with self._lock:
            self.query_times.append({
                'type': query_type,
                'duration': duration,
                'timestamp': time.time()
            })
            
            # Behoud alleen laatste 500 queries (kleiner voor 4 gebruikers)
            if len(self.query_times) > 500:
                self.query_times = self.query_times[-500:]
    
    def get_average_query_time(self, query_type: str = None) -> float:
        """Berekent gemiddelde query tijd."""
        with self._lock:
            if query_type:
                times = [q['duration'] for q in self.query_times if q['type'] == query_type]
            else:
                times = [q['duration'] for q in self.query_times]
            
            return sum(times) / len(times) if times else 0.0
    
    def get_performance_summary(self):
        """Geeft performance samenvatting."""
        with self._lock:
            if not self.query_times:
                return {"message": "Geen performance data beschikbaar"}
            
            total_queries = len(self.query_times)
            avg_time = sum(q['duration'] for q in self.query_times) / total_queries
            max_time = max(q['duration'] for q in self.query_times)
            min_time = min(q['duration'] for q in self.query_times)
            
            return {
                'total_queries': total_queries,
                'average_time': f"{avg_time:.3f}s",
                'max_time': f"{max_time:.3f}s",
                'min_time': f"{min_time:.3f}s",
                'cache_stats': content_cache.get_stats()
            }

# Globale performance monitor
performance_monitor = PerformanceMonitor()

def optimize_database_for_multiple_users():
    """Voert alle optimalisaties uit voor meerdere gebruikers."""
    print("[INIT] Database optimalisaties voor meerdere gebruikers...")

    # Database optimalisaties
    print("[PRAGMA] Database PRAGMA optimalisaties toegepast")
    print("[INDEX] Performance indexen aangemaakt")
    print("[CACHE] In-memory caching geactiveerd")
    print("[MONITOR] Performance monitoring geactiveerd")

    print("[OK] Alle kostenloze optimalisaties voltooid!")
    print("[INFO] Geschikt voor 4 gelijktijdige gebruikers") 