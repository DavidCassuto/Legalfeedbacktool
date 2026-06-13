# src/routes/misc.py
"""Overige routes: performance stats."""

from flask import render_template

from auth import admin_required
from database_optimizations import performance_monitor


@admin_required
def performance_stats():
    """Toont performance statistieken."""
    stats = performance_monitor.get_performance_summary()
    return render_template('performance.html', stats=stats)
