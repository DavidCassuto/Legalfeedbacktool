# src/database.py
"""Gedeelde database-helpers: get_db() en close_db() voor Flask-request-context."""

import time
from flask import g

import db_utils
from database_optimizations import get_optimized_db, performance_monitor


def get_db():
    """Geeft een geoptimaliseerde SQLite-verbinding voor de huidige request."""
    if 'db' not in g:
        start_time = time.time()
        g.db = get_optimized_db()
        duration = time.time() - start_time
        performance_monitor.record_query_time('connection', duration)

        cursor = g.db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sections'")
        if cursor.fetchone() is None:
            print("DEBUG: Database bestaat nog niet, initialiseren...")
            db_utils.initialize_db(g.db)
        else:
            cursor.execute("SELECT COUNT(*) FROM sections")
            section_count = cursor.fetchone()[0]
            if section_count == 0:
                db_utils.initialize_db(g.db)

        # Altijd migraties uitvoeren (idempotent)
        db_utils.migrate_db(g.db)

    return g.db


def close_db(e=None):
    """Sluit de database-verbinding aan het einde van de request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()
        print("Databaseverbinding gesloten (via close_db).")
