# src/routes/auth.py
"""Authenticatie-routes: login, logout."""

from flask import render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash

from database import get_db
from auth import login_required, is_admin


def login():
    """Login pagina."""
    if 'user_id' in session:
        return redirect(url_for('holistic_form'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        db = get_db()
        user = db.execute(
            'SELECT * FROM users WHERE username = ?', (username,)
        ).fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id']   = user['id']
            session['username']  = user['username']
            session['user_role'] = user['role']
            session['organization_id'] = user['organization_id']
            role = user['role']
            if role == 'admin':
                return redirect(url_for('index'))
            if role == 'organisatie' and user['first_login']:
                # Eerste login organisatie/docent → configuratiescherm
                return redirect(url_for('organisatie_config'))
            if role == 'consumer' and user['first_login']:
                # Oude consumer-rol: generiek welkomstscherm
                return redirect(url_for('welcome'))
            return redirect(url_for('holistic_form'))
        else:
            flash('Ongeldige gebruikersnaam of wachtwoord.', 'danger')

    return render_template('login.html')


def logout():
    """Uitloggen en sessie wissen."""
    session.clear()
    flash('Je bent uitgelogd.', 'info')
    return redirect(url_for('login'))


@login_required
def index():
    """Welkomstpagina van de applicatie."""
    if not is_admin():
        return redirect(url_for('holistic_form'))
    return render_template('index.html')


def demo_loader():
    """Demo pagina voor de laadanimatie."""
    return render_template('demo_loader.html')
