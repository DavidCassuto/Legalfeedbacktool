# src/routes/users.py
"""Gebruikersbeheer routes (alleen voor admins)."""

import traceback

from flask import render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash

from database import get_db
from auth import admin_required


@admin_required
def list_users():
    """Overzichtspagina van alle gebruikers."""
    db = get_db()
    users = db.execute('''
        SELECT u.*, o.name AS org_name
        FROM users u
        LEFT JOIN organizations o ON u.organization_id = o.id
        ORDER BY u.role DESC, u.username
    ''').fetchall()
    organizations = db.execute('SELECT id, name FROM organizations ORDER BY name').fetchall()
    return render_template('users.html',
                           users=users,
                           organizations=organizations,
                           show_form=False,
                           edit_user=None,
                           session_user_id=session.get('user_id'))


@admin_required
def add_user():
    """Gebruiker toevoegen."""
    db = get_db()
    organizations = db.execute('SELECT id, name FROM organizations ORDER BY name').fetchall()

    if request.method == 'POST':
        username  = request.form.get('username', '').strip()
        password  = request.form.get('password', '')
        role      = request.form.get('role', 'consumer')
        full_name = request.form.get('full_name', '').strip()
        org_id    = request.form.get('organization_id') or None

        if not username or not password:
            flash('Gebruikersnaam en wachtwoord zijn verplicht.', 'danger')
        else:
            try:
                db.execute(
                    'INSERT INTO users (username, password_hash, role, full_name, organization_id) VALUES (?,?,?,?,?)',
                    (username, generate_password_hash(password), role, full_name or None, org_id)
                )
                db.commit()
                flash(f'Gebruiker "{username}" succesvol aangemaakt.', 'success')
                return redirect(url_for('list_users'))
            except Exception as e:
                flash(f'Fout: {e}', 'danger')

    users = db.execute('''
        SELECT u.*, o.name AS org_name FROM users u
        LEFT JOIN organizations o ON u.organization_id = o.id ORDER BY u.role DESC, u.username
    ''').fetchall()
    return render_template('users.html', users=users, organizations=organizations,
                           show_form=True, edit_user=None,
                           session_user_id=session.get('user_id'))


@admin_required
def edit_user(id):
    """Gebruiker bewerken."""
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (id,)).fetchone()
    if user is None:
        flash('Gebruiker niet gevonden.', 'danger')
        return redirect(url_for('list_users'))

    organizations = db.execute('SELECT id, name FROM organizations ORDER BY name').fetchall()

    if request.method == 'POST':
        username  = request.form.get('username', '').strip()
        password  = request.form.get('password', '')
        role      = request.form.get('role', 'consumer')
        full_name = request.form.get('full_name', '').strip()
        org_id    = request.form.get('organization_id') or None

        if not username:
            flash('Gebruikersnaam is verplicht.', 'danger')
        else:
            try:
                if password:
                    db.execute(
                        'UPDATE users SET username=?, password_hash=?, role=?, full_name=?, organization_id=? WHERE id=?',
                        (username, generate_password_hash(password), role, full_name or None, org_id, id)
                    )
                else:
                    db.execute(
                        'UPDATE users SET username=?, role=?, full_name=?, organization_id=? WHERE id=?',
                        (username, role, full_name or None, org_id, id)
                    )
                db.commit()
                if id == session.get('user_id'):
                    session['username']  = username
                    session['user_role'] = role
                flash(f'Gebruiker "{username}" bijgewerkt.', 'success')
                return redirect(url_for('list_users'))
            except Exception as e:
                flash(f'Fout: {e}', 'danger')

    users = db.execute('''
        SELECT u.*, o.name AS org_name FROM users u
        LEFT JOIN organizations o ON u.organization_id = o.id ORDER BY u.role DESC, u.username
    ''').fetchall()
    return render_template('users.html', users=users, organizations=organizations,
                           show_form=True, edit_user=user,
                           session_user_id=session.get('user_id'))


@admin_required
def delete_user(id):
    """Gebruiker verwijderen."""
    if id == session.get('user_id'):
        flash('Je kunt je eigen account niet verwijderen.', 'danger')
        return redirect(url_for('list_users'))

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (id,)).fetchone()
    if user is None:
        flash('Gebruiker niet gevonden.', 'danger')
    else:
        try:
            db.execute('DELETE FROM users WHERE id=?', (id,))
            db.commit()
            flash(f'Gebruiker "{user["username"]}" verwijderd.', 'success')
        except Exception as e:
            flash(f'Fout bij verwijderen: {e}', 'danger')
            traceback.print_exc()

    return redirect(url_for('list_users'))
