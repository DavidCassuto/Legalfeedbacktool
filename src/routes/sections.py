# src/routes/sections.py
"""Secties management routes: lijst, toevoegen, bewerken, verwijderen."""

import json
import traceback

from flask import render_template, request, redirect, url_for, flash

from database import get_db
from auth import admin_required


@admin_required
def list_sections():
    """Overzichtspagina van alle secties."""
    db = get_db()
    sections = db.execute('''
        SELECT s.*, p.name AS parent_name
        FROM sections s
        LEFT JOIN sections p ON s.parent_id = p.id
        ORDER BY s.order_index, s.level, s.name
    ''').fetchall()
    return render_template('sections_list.html', sections=sections)


@admin_required
def add_section():
    """Route voor het toevoegen van een nieuwe sectie."""
    db = get_db()

    if request.method == 'POST':
        name             = request.form['name']
        identifier       = request.form['identifier']
        level            = request.form.get('level', 1)
        order_index      = request.form.get('order_index', 0)
        document_type_id = request.form.get('document_type_id')
        alt_names_raw    = request.form.get('alternative_names', '').strip()
        alt_names_list   = [n.strip() for n in alt_names_raw.split(',') if n.strip()]
        alternative_names_json = json.dumps(alt_names_list)

        if not name or not identifier:
            flash('Naam en identifier zijn verplicht!', 'danger')
        else:
            try:
                db.execute(
                    'INSERT INTO sections (name, identifier, level, order_index, document_type_id, alternative_names) VALUES (?,?,?,?,?,?)',
                    (name, identifier, level, order_index, document_type_id, alternative_names_json)
                )
                db.commit()
                flash('Sectie succesvol toegevoegd!', 'success')
                return redirect(url_for('list_sections'))
            except Exception as e:
                flash(f'Fout bij toevoegen: {e}', 'danger')
                traceback.print_exc()

    document_types = db.execute('SELECT id, name FROM document_types').fetchall()
    form_data = request.form if request.method == 'POST' else {}
    return render_template('add_section.html', document_types=document_types, form_data=form_data)


@admin_required
def edit_section(id):
    """Route voor het bewerken van een sectie."""
    db = get_db()
    section = db.execute('SELECT * FROM sections WHERE id=?', (id,)).fetchone()

    if section is None:
        flash('Sectie niet gevonden.', 'danger')
        return redirect(url_for('list_sections'))

    if request.method == 'POST':
        name             = request.form['name']
        identifier       = request.form['identifier']
        level            = request.form.get('level', 1)
        order_index      = request.form.get('order_index', 0)
        document_type_id = request.form.get('document_type_id')
        alt_names_raw    = request.form.get('alternative_names', '').strip()
        alt_names_list   = [n.strip() for n in alt_names_raw.split(',') if n.strip()]
        alternative_names_json = json.dumps(alt_names_list)

        if not name or not identifier:
            flash('Naam en identifier zijn verplicht!', 'danger')
        else:
            try:
                db.execute(
                    'UPDATE sections SET name=?, identifier=?, level=?, order_index=?, document_type_id=?, alternative_names=? WHERE id=?',
                    (name, identifier, level, order_index, document_type_id, alternative_names_json, id)
                )
                db.commit()
                flash('Sectie succesvol bijgewerkt!', 'success')
                return redirect(url_for('list_sections'))
            except Exception as e:
                flash(f'Fout bij bijwerken: {e}', 'danger')
                traceback.print_exc()

    document_types = db.execute('SELECT id, name FROM document_types').fetchall()
    form_data = request.form if request.method == 'POST' else {}
    try:
        existing_alt   = json.loads(section['alternative_names'] or '[]')
        alt_names_display = ', '.join(existing_alt)
    except (json.JSONDecodeError, TypeError):
        alt_names_display = ''

    return render_template('edit_section.html',
                           section=section,
                           document_types=document_types,
                           form_data=form_data,
                           alt_names_display=alt_names_display)


@admin_required
def delete_section(id):
    """Route voor het verwijderen van een sectie."""
    db = get_db()
    section = db.execute('SELECT * FROM sections WHERE id=?', (id,)).fetchone()

    if section is None:
        flash('Sectie niet gevonden.', 'danger')
    else:
        try:
            db.execute('DELETE FROM sections WHERE id=?', (id,))
            db.commit()
            flash('Sectie succesvol verwijderd!', 'success')
        except Exception as e:
            flash(f'Fout bij verwijderen: {e}', 'danger')
            traceback.print_exc()

    return redirect(url_for('list_sections'))
