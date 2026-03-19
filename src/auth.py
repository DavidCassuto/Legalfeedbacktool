"""
auth.py — Authenticatie hulpfuncties voor DocuCheck.

Rollen:
  admin    → volledige toegang (beheerder / instelling)
  consumer → alleen upload + eigen documenten (student / eindgebruiker)
"""
from functools import wraps
from flask import session, redirect, url_for, flash


def login_required(f):
    """Vereist dat de gebruiker is ingelogd."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Log in om verder te gaan.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Vereist dat de gebruiker is ingelogd én de rol 'admin' heeft."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Log in om verder te gaan.', 'warning')
            return redirect(url_for('login'))
        if session.get('user_role') != 'admin':
            flash('Geen toegang. Alleen beheerders kunnen dit bekijken.', 'danger')
            return redirect(url_for('upload_document'))
        return f(*args, **kwargs)
    return decorated


def current_user_id():
    """Geeft het ID van de ingelogde gebruiker, of None."""
    return session.get('user_id')


def current_user_role():
    """Geeft de rol van de ingelogde gebruiker ('admin' / 'consumer'), of None."""
    return session.get('user_role')


def is_admin():
    """True als de ingelogde gebruiker een admin is."""
    return session.get('user_role') == 'admin'
