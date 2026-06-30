# src/routes/organizations.py
"""Organisaties management routes."""

import traceback

from flask import render_template, request, redirect, url_for, flash

from database import get_db
from auth import admin_required


@admin_required
def list_organizations():
    """Overzichtspagina van alle organisaties."""
    db = get_db()
    organizations = db.execute('SELECT * FROM organizations ORDER BY name').fetchall()
    return render_template('organizations_list.html', organizations=organizations)


@admin_required
def add_organization():
    """Route voor het toevoegen van een nieuwe organisatie."""
    db = get_db()

    if request.method == 'POST':
        name            = request.form['name']
        description     = request.form.get('description', '')
        preferred_model = request.form.get('preferred_model', 'claude-haiku-4-5')

        if not name:
            flash('Naam is verplicht!', 'danger')
        else:
            try:
                db.execute(
                    'INSERT INTO organizations (name, description, preferred_model) VALUES (?,?,?)',
                    (name, description, preferred_model)
                )
                db.commit()
                flash('Organisatie succesvol toegevoegd!', 'success')
                return redirect(url_for('list_organizations'))
            except Exception as e:
                flash(f'Fout bij toevoegen: {e}', 'danger')
                traceback.print_exc()

    return render_template('add_organization.html')


@admin_required
def edit_organization(id):
    """Route voor het bewerken van een organisatie."""
    db = get_db()
    organization = db.execute('SELECT * FROM organizations WHERE id=?', (id,)).fetchone()

    if organization is None:
        flash('Organisatie niet gevonden.', 'danger')
        return redirect(url_for('list_organizations'))

    if request.method == 'POST':
        name            = request.form['name']
        description     = request.form.get('description', '')
        preferred_model = request.form.get('preferred_model', 'claude-haiku-4-5')

        if not name:
            flash('Naam is verplicht!', 'danger')
        else:
            try:
                db.execute(
                    'UPDATE organizations SET name=?, description=?, preferred_model=? WHERE id=?',
                    (name, description, preferred_model, id)
                )
                db.commit()
                flash('Organisatie succesvol bijgewerkt!', 'success')
                return redirect(url_for('list_organizations'))
            except Exception as e:
                flash(f'Fout bij bijwerken: {e}', 'danger')
                traceback.print_exc()

    return render_template('edit_organization.html', organization=organization)


@admin_required
def delete_organization(id):
    """Route voor het verwijderen van een organisatie."""
    db = get_db()
    organization = db.execute('SELECT * FROM organizations WHERE id=?', (id,)).fetchone()

    if organization is None:
        flash('Organisatie niet gevonden.', 'danger')
    else:
        try:
            db.execute('DELETE FROM organizations WHERE id=?', (id,))
            db.commit()
            flash('Organisatie succesvol verwijderd!', 'success')
        except Exception as e:
            flash(f'Fout bij verwijderen: {e}', 'danger')
            traceback.print_exc()

    return redirect(url_for('list_organizations'))
