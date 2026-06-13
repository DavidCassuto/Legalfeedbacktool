# src/routes/onboarding.py
"""Onboarding wizard + uitnodigingssysteem voor nieuwe docenten."""

import secrets
import re
from datetime import datetime, timedelta

from flask import render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash

from database import get_db
from auth import admin_required, login_required


# ── Wizard ────────────────────────────────────────────────────────────────────

@admin_required
def onboarding_wizard():
    """Stap-voor-stap wizard voor het aanmaken van een nieuwe klant."""
    db = get_db()
    sections = db.execute(
        'SELECT id, name, identifier, level FROM sections ORDER BY order_index, name'
    ).fetchall()
    organizations = db.execute('SELECT id, name FROM organizations ORDER BY name').fetchall()
    return render_template('onboarding_wizard.html', sections=sections, organizations=organizations)


@admin_required
def onboarding_step1():
    """Stap 1: Organisatie aanmaken of kiezen."""
    data = request.get_json()
    db = get_db()

    mode = data.get('mode', 'new')  # 'new' of 'existing'

    if mode == 'existing':
        org_id = data.get('org_id')
        if not org_id:
            return jsonify({'ok': False, 'error': 'Geen organisatie geselecteerd.'})
        org = db.execute('SELECT id, name FROM organizations WHERE id=?', (org_id,)).fetchone()
        if not org:
            return jsonify({'ok': False, 'error': 'Organisatie niet gevonden.'})
        return jsonify({'ok': True, 'org_id': org['id'], 'org_name': org['name']})

    name = (data.get('name') or '').strip()
    description = (data.get('description') or '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'Naam is verplicht.'})

    try:
        cursor = db.execute(
            'INSERT INTO organizations (name, description) VALUES (?, ?)',
            (name, description or None)
        )
        db.commit()
        return jsonify({'ok': True, 'org_id': cursor.lastrowid, 'org_name': name})
    except Exception as e:
        if 'UNIQUE' in str(e):
            # Org bestaat al, geef het bestaande id terug
            org = db.execute('SELECT id, name FROM organizations WHERE name=?', (name,)).fetchone()
            return jsonify({'ok': True, 'org_id': org['id'], 'org_name': org['name'], 'existing': True})
        return jsonify({'ok': False, 'error': str(e)})


@admin_required
def onboarding_step2():
    """Stap 2: Documenttype aanmaken."""
    data = request.get_json()
    name = (data.get('name') or '').strip()
    description = (data.get('description') or '').strip()
    org_id = data.get('org_id')

    if not name:
        return jsonify({'ok': False, 'error': 'Naam is verplicht.'})

    # Genereer identifier uit naam
    identifier = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')

    db = get_db()
    try:
        cursor = db.execute(
            'INSERT INTO document_types (name, identifier, description, organization_id) VALUES (?, ?, ?, ?)',
            (name, identifier, description or None, org_id or None)
        )
        db.commit()
        return jsonify({'ok': True, 'doc_type_id': cursor.lastrowid, 'doc_type_name': name})
    except Exception as e:
        if 'UNIQUE' in str(e):
            dt = db.execute('SELECT id, name FROM document_types WHERE name=?', (name,)).fetchone()
            # Zorg dat organization_id ook bijgewerkt wordt als het documenttype al bestond
            if org_id:
                db.execute('UPDATE document_types SET organization_id=? WHERE id=?', (org_id, dt['id']))
                db.commit()
            return jsonify({'ok': True, 'doc_type_id': dt['id'], 'doc_type_name': dt['name'], 'existing': True})
        return jsonify({'ok': False, 'error': str(e)})


@admin_required
def onboarding_step3():
    """Stap 3: Secties koppelen aan documenttype."""
    data = request.get_json()
    doc_type_id = data.get('doc_type_id')
    section_ids = data.get('section_ids', [])

    if not doc_type_id:
        return jsonify({'ok': False, 'error': 'Documenttype ontbreekt.'})

    db = get_db()
    # Verwijder bestaande koppelingen voor dit documenttype
    db.execute('DELETE FROM document_type_sections WHERE document_type_id=?', (doc_type_id,))

    for idx, sec_id in enumerate(section_ids):
        db.execute(
            'INSERT OR IGNORE INTO document_type_sections (document_type_id, section_id, order_index) VALUES (?,?,?)',
            (doc_type_id, sec_id, idx)
        )
    db.commit()
    return jsonify({'ok': True, 'count': len(section_ids)})


@admin_required
def onboarding_step4():
    """Stap 4: Uitnodigingslink genereren voor docent."""
    data = request.get_json()
    full_name = (data.get('full_name') or '').strip()
    org_id = data.get('org_id')

    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=7)

    db = get_db()
    db.execute(
        'INSERT INTO invitation_tokens (token, full_name, role, organization_id, created_by, expires_at) VALUES (?,?,?,?,?,?)',
        (token, full_name or None, 'consumer', org_id or None, session['user_id'], expires_at.isoformat())
    )
    db.commit()

    invite_url = url_for('invite_accept', token=token, _external=True)
    return jsonify({'ok': True, 'invite_url': invite_url, 'expires': '7 dagen'})


# ── Uitnodiging accepteren ────────────────────────────────────────────────────

def invite_accept(token):
    """Pagina waar docent zijn account aanmaakt via uitnodigingslink."""
    db = get_db()
    invite = db.execute(
        'SELECT * FROM invitation_tokens WHERE token=?', (token,)
    ).fetchone()

    if not invite:
        flash('Ongeldige uitnodigingslink.', 'danger')
        return redirect(url_for('login'))

    if invite['used_at']:
        flash('Deze uitnodigingslink is al gebruikt.', 'warning')
        return redirect(url_for('login'))

    if datetime.utcnow() > datetime.fromisoformat(invite['expires_at']):
        flash('Deze uitnodigingslink is verlopen (geldig 7 dagen).', 'warning')
        return redirect(url_for('login'))

    org = None
    if invite['organization_id']:
        org = db.execute('SELECT name FROM organizations WHERE id=?', (invite['organization_id'],)).fetchone()

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')
        full_name = request.form.get('full_name', '').strip() or invite['full_name']

        errors = []
        if not username:
            errors.append('Gebruikersnaam is verplicht.')
        if len(password) < 6:
            errors.append('Wachtwoord moet minimaal 6 tekens zijn.')
        if password != password2:
            errors.append('Wachtwoorden komen niet overeen.')

        if not errors:
            # Controleer of gebruikersnaam al bestaat
            existing = db.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
            if existing:
                errors.append('Gebruikersnaam is al in gebruik. Kies een andere.')

        if errors:
            for e in errors:
                flash(e, 'danger')
        else:
            try:
                cursor = db.execute(
                    'INSERT INTO users (username, password_hash, role, full_name, organization_id, first_login) VALUES (?,?,?,?,?,1)',
                    (username, generate_password_hash(password), invite['role'],
                     full_name or None, invite['organization_id'])
                )
                db.execute(
                    'UPDATE invitation_tokens SET used_at=? WHERE token=?',
                    (datetime.utcnow().isoformat(), token)
                )
                db.commit()
                flash('Account aangemaakt! Je kunt nu inloggen.', 'success')
                return redirect(url_for('login'))
            except Exception as e:
                flash(f'Fout bij aanmaken account: {e}', 'danger')

    return render_template('invite_accept.html', invite=invite, org=org, token=token)


# ── Welkomstscherm na eerste login ────────────────────────────────────────────

@login_required
def welcome():
    """Welkomstscherm voor nieuwe gebruikers (eerste login)."""
    db = get_db()
    # Reset first_login vlag
    db.execute('UPDATE users SET first_login=0 WHERE id=?', (session['user_id'],))
    db.commit()
    return render_template('welcome.html')
