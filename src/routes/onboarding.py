# src/routes/onboarding.py
"""Onboarding wizard + uitnodigingssysteem voor nieuwe docenten."""

import os
import uuid
import secrets
import re
from datetime import datetime, timedelta

from flask import (
    render_template, request, redirect, url_for, flash, session, jsonify, current_app,
)
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from database import get_db
from auth import admin_required, login_required
import rubric_library
import holistic_analysis
import languages


# ── Wizard ────────────────────────────────────────────────────────────────────

@admin_required
def onboarding_wizard():
    """Stap-voor-stap wizard voor het opzetten van een nieuwe klant:
    organisatie -> taal & criteria -> rubric -> docent uitnodigen."""
    db = get_db()
    organizations = db.execute('SELECT id, name FROM organizations ORDER BY name').fetchall()
    # Standaardcriteria per taal, zodat stap 2 ze kan voorvullen en bij taalwissel verversen.
    defaults_by_lang = {
        lang: {
            'inhoud': d.get('inhoud', ''), 'toon': d.get('toon', ''),
        }
        for lang, d in holistic_analysis.DEFAULTS_BY_LANG.items()
    }
    return render_template(
        'onboarding_wizard.html',
        organizations=organizations,
        lang_choices=languages.choices(),
        defaults_by_lang=defaults_by_lang,
        default_max=holistic_analysis.DEFAULT_MAX_PER_CATEGORIE,
    )


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
    """Stap 2+3 (samengevoegd): rubric uploaden + feedback-instellingen opslaan
    als rubric, gekoppeld aan de klant. Ontvangt multipart/form-data (Excel-bestand)."""
    org_id = request.form.get('org_id')
    if not org_id:
        return jsonify({'ok': False, 'error': 'Organisatie ontbreekt.'})

    rubric_file = request.files.get('rubric_file')
    if not rubric_file or not rubric_file.filename:
        return jsonify({'ok': False, 'error': 'Selecteer een Excel-beoordelingsformulier (.xlsx).'})
    if not rubric_file.filename.lower().endswith(('.xlsx', '.xlsm')):
        return jsonify({'ok': False, 'error': 'Het beoordelingsformulier moet een Excel-bestand zijn (.xlsx).'})

    # Tekstvelden die in de wizard niet getoond worden blijven leeg -> bij analyse
    # vult _merge_config ze met de standaardcriteria van de gekozen taal.
    feedback_config = {
        'language':           (request.form.get('language') or 'nl').strip(),
        'inhoud_criteria':    (request.form.get('inhoud_criteria') or '').strip(),
        'onderwijs_criteria': '',
        'taal_enabled':       bool(request.form.get('taal_enabled')),
        'taal_instructies':   '',
        'stijl_enabled':      bool(request.form.get('stijl_enabled')),
        'stijl_instructies':  '',
        'ai_enabled':         bool(request.form.get('ai_enabled')),
        'ai_instructies':     '',
        'toon':               (request.form.get('toon') or '').strip(),
        'show_suggestions':   bool(request.form.get('show_suggestions')),
        'max_per_categorie':  int(request.form.get('max_per_categorie') or 0) or None,
        'allow_language_override': bool(request.form.get('allow_language_override')),
    }
    name = (request.form.get('name') or '').strip() or os.path.splitext(rubric_file.filename)[0]

    upload_folder = current_app.config['UPLOAD_FOLDER']
    work = os.path.join(upload_folder, 'holistic')
    os.makedirs(work, exist_ok=True)
    tmp = os.path.join(work, f"tmp_{uuid.uuid4().hex[:8]}_{secure_filename(rubric_file.filename)}")
    rubric_file.save(tmp)
    try:
        rec = rubric_library.save_rubric(
            upload_folder, name, tmp,
            feedback_config=feedback_config, organization_id=org_id)
        return jsonify({'ok': True, 'rubric_id': rec['id'], 'rubric_name': rec['name'],
                        'tab_count': len(rec['tabs'])})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


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
