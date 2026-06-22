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
            return redirect(url_for('holistic_form'))
        return f(*args, **kwargs)
    return decorated


def current_user_id():
    """Geeft het ID van de ingelogde gebruiker, of None."""
    return session.get('user_id')


def current_user_role():
    """Geeft de rol van de ingelogde gebruiker ('admin' / 'consumer'), of None."""
    return session.get('user_role')


def current_user_org_id():
    """Geeft het organisatie-id (klant) van de ingelogde gebruiker, of None.

    Wordt bij login in de sessie gezet; voor bestaande sessies (van vóór deze
    wijziging) wordt het eenmalig uit de database bijgehaald en gecachet.
    """
    if 'user_id' not in session:
        return None
    if 'organization_id' in session:
        return session['organization_id']
    # Lazy-backfill voor sessies die nog geen organization_id hebben.
    from database import get_db
    row = get_db().execute(
        'SELECT organization_id FROM users WHERE id=?', (session['user_id'],)
    ).fetchone()
    org_id = row['organization_id'] if row else None
    session['organization_id'] = org_id
    return org_id


def is_admin():
    """True als de ingelogde gebruiker een admin is."""
    return session.get('user_role') == 'admin'
