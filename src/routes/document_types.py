# src/routes/document_types.py
"""Document types management routes."""

import traceback

from flask import render_template, request, redirect, url_for, flash

from database import get_db
from auth import admin_required


@admin_required
def list_document_types():
    """Overzichtspagina van alle document types."""
    db = get_db()
    document_types = db.execute('SELECT * FROM document_types ORDER BY name').fetchall()
    return render_template('document_types_list.html', document_types=document_types)


@admin_required
def add_document_type():
    """Route voor het toevoegen van een nieuw document type."""
    db = get_db()

    if request.method == 'POST':
        name        = request.form['name']
        identifier  = request.form['identifier']
        description = request.form.get('description', '')

        if not name or not identifier:
            flash('Naam en identifier zijn verplicht!', 'danger')
        else:
            try:
                db.execute(
                    'INSERT INTO document_types (name, identifier, description) VALUES (?,?,?)',
                    (name, identifier, description)
                )
                db.commit()
                flash('Document type succesvol toegevoegd!', 'success')
                return redirect(url_for('list_document_types'))
            except Exception as e:
                flash(f'Fout bij toevoegen: {e}', 'danger')
                traceback.print_exc()

    return render_template('add_document_type.html')


@admin_required
def edit_document_type(id):
    """Route voor het bewerken van een document type."""
    db = get_db()
    document_type = db.execute('SELECT * FROM document_types WHERE id=?', (id,)).fetchone()

    if document_type is None:
        flash('Document type niet gevonden.', 'danger')
        return redirect(url_for('list_document_types'))

    if request.method == 'POST':
        name                    = request.form['name']
        identifier              = request.form['identifier']
        default_llm_role_prompt = request.form.get('default_llm_role_prompt', '').strip()
        show_suggestions        = 1 if request.form.get('show_suggestions') else 0

        if not name or not identifier:
            flash('Naam en identifier zijn verplicht!', 'danger')
        else:
            try:
                db.execute(
                    'UPDATE document_types SET name=?, identifier=?, default_llm_role_prompt=?, show_suggestions=? WHERE id=?',
                    (name, identifier, default_llm_role_prompt or None, show_suggestions, id)
                )
                db.commit()
                flash('Document type succesvol bijgewerkt!', 'success')
                return redirect(url_for('list_document_types'))
            except Exception as e:
                flash(f'Fout bij bijwerken: {e}', 'danger')
                traceback.print_exc()

    return render_template('edit_document_type.html', document_type=document_type)


@admin_required
def delete_document_type(id):
    """Route voor het verwijderen van een document type."""
    db = get_db()
    document_type = db.execute('SELECT * FROM document_types WHERE id=?', (id,)).fetchone()

    if document_type is None:
        flash('Document type niet gevonden.', 'danger')
    else:
        try:
            db.execute('DELETE FROM document_types WHERE id=?', (id,))
            db.commit()
            flash('Document type succesvol verwijderd!', 'success')
        except Exception as e:
            flash(f'Fout bij verwijderen: {e}', 'danger')
            traceback.print_exc()

    return redirect(url_for('list_document_types'))


@admin_required
def list_organization_document_types(org_id):
    """Toon document types voor een specifieke organisatie."""
    db = get_db()
    organization = db.execute('SELECT * FROM organizations WHERE id=?', (org_id,)).fetchone()
    if organization is None:
        flash('Organisatie niet gevonden.', 'danger')
        return redirect(url_for('list_organizations'))

    document_types = db.execute('''
        SELECT dt.*, COUNT(DISTINCT d.id) as document_count
        FROM document_types dt
        LEFT JOIN documents d ON dt.id = d.document_type_id
        WHERE dt.organization_id = ?
        GROUP BY dt.id
        ORDER BY dt.name
    ''', (org_id,)).fetchall()

    return render_template('organization_document_types.html',
                           organization=organization,
                           document_types=document_types)


@admin_required
def add_organization_document_type(org_id):
    """Voeg document type toe voor een specifieke organisatie."""
    db = get_db()
    organization = db.execute('SELECT * FROM organizations WHERE id=?', (org_id,)).fetchone()
    if organization is None:
        flash('Organisatie niet gevonden.', 'danger')
        return redirect(url_for('list_organizations'))

    if request.method == 'POST':
        name        = request.form['name']
        identifier  = request.form['identifier']
        description = request.form.get('description', '')

        if not name or not identifier:
            flash('Naam en identifier zijn verplicht!', 'danger')
        else:
            try:
                db.execute(
                    'INSERT INTO document_types (name, identifier, description, organization_id) VALUES (?,?,?,?)',
                    (name, identifier, description, org_id)
                )
                db.commit()
                flash('Document type succesvol toegevoegd!', 'success')
                return redirect(url_for('list_organization_document_types', org_id=org_id))
            except Exception as e:
                flash(f'Fout bij toevoegen: {e}', 'danger')
                traceback.print_exc()

    return render_template('add_organization_document_type.html', organization=organization)


def manage_document_type_sections(doc_type_id):
    """Beheer secties voor een document type."""
    db = get_db()
    document_type = db.execute('SELECT * FROM document_types WHERE id=?', (doc_type_id,)).fetchone()
    if document_type is None:
        flash('Document type niet gevonden.', 'danger')
        return redirect(url_for('list_document_types'))

    sections = db.execute('''
        SELECT s.*, CASE WHEN dts.section_id IS NOT NULL THEN 1 ELSE 0 END as is_assigned
        FROM sections s
        LEFT JOIN document_type_sections dts ON s.id = dts.section_id AND dts.document_type_id = ?
        ORDER BY s.name
    ''', (doc_type_id,)).fetchall()

    return render_template('manage_document_type_sections.html',
                           document_type=document_type,
                           sections=sections)


def add_section_to_document_type(doc_type_id):
    """Voeg sectie toe aan document type."""
    db = get_db()
    section_id = request.form.get('section_id')

    if not section_id:
        flash('Sectie is verplicht!', 'danger')
    else:
        try:
            db.execute(
                'INSERT INTO document_type_sections (document_type_id, section_id) VALUES (?,?)',
                (doc_type_id, section_id)
            )
            db.commit()
            flash('Sectie succesvol toegevoegd aan document type!', 'success')
        except Exception as e:
            flash(f'Fout bij toevoegen: {e}', 'danger')
            traceback.print_exc()

    return redirect(url_for('manage_document_type_sections', doc_type_id=doc_type_id))


def remove_section_from_document_type(doc_type_id, section_id):
    """Verwijder sectie van document type."""
    db = get_db()
    try:
        db.execute(
            'DELETE FROM document_type_sections WHERE document_type_id=? AND section_id=?',
            (doc_type_id, section_id)
        )
        db.commit()
        flash('Sectie succesvol verwijderd van document type!', 'success')
    except Exception as e:
        flash(f'Fout bij verwijderen: {e}', 'danger')
        traceback.print_exc()

    return redirect(url_for('manage_document_type_sections', doc_type_id=doc_type_id))
