"""
Integratietests voor Flask-routes.

Gebruikt de Flask test-client met een in-memory test-DB.
Geen echte bestands-uploads of LLM-calls.

Dekt:
- Login / logout flow
- Redirect van beveiligde pagina's naar login
- Status API response-formaat
- Basis-routing (geen 404/500 op bekende routes)
"""
import sys
import os
import json
import sqlite3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestLogin:

    def test_login_pagina_laadt(self, client):
        """GET /login geeft 200 terug."""
        resp = client.get('/login')
        assert resp.status_code == 200

    def test_login_met_correcte_credentials(self, client):
        """POST /login met goede credentials leidt door naar dashboard."""
        resp = client.post(
            '/login',
            data={'username': 'testuser', 'password': 'test'},
            follow_redirects=False,
        )
        assert resp.status_code in (301, 302), (
            "Succesvolle login moet redirecten."
        )

    def test_login_met_foute_credentials(self, client):
        """POST /login met fout wachtwoord blijft op /login (geen redirect)."""
        resp = client.post(
            '/login',
            data={'username': 'testuser', 'password': 'fout'},
            follow_redirects=False,
        )
        # Geen redirect bij mislukte login
        assert resp.status_code == 200

    def test_logout_redirect(self, logged_in_client):
        """GET /logout leidt door naar /login."""
        resp = logged_in_client.get('/logout', follow_redirects=False)
        assert resp.status_code in (301, 302)


class TestBeveiligdeRoutes:

    def test_documenten_vereist_login(self, client):
        """/documents zonder sessie → redirect naar /login."""
        resp = client.get('/documents', follow_redirects=False)
        assert resp.status_code in (301, 302)
        assert b'login' in resp.headers.get('Location', '').lower().encode()

    def test_upload_vereist_login(self, client):
        """/upload zonder sessie → redirect naar /login."""
        resp = client.get('/upload', follow_redirects=False)
        assert resp.status_code in (301, 302)

    def test_documenten_toegankelijk_na_login(self, logged_in_client):
        """/documents na login → 200."""
        resp = logged_in_client.get('/documents')
        assert resp.status_code == 200


class TestStatusApi:

    def _maak_document_in_db(self, db_path, status='pending'):
        """Voegt een testdocument in en geeft het ID terug."""
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "INSERT INTO documents (filename, original_filename, analysis_status) "
            "VALUES (?,?,?)",
            ('test.docx', 'Test.docx', status)
        )
        doc_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return doc_id

    def test_status_api_geeft_json(self, logged_in_client, flask_app):
        """GET /api/analysis/<id>/status geeft JSON terug met 'status' veld."""
        doc_id = self._maak_document_in_db(flask_app.config['DATABASE'], 'pending')
        resp = logged_in_client.get(f'/api/analysis/{doc_id}/status')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'status' in data, "Response JSON moet 'status' bevatten."

    def test_status_api_geeft_juiste_status(self, logged_in_client, flask_app):
        """Status API geeft de status terug zoals die in de DB staat."""
        doc_id = self._maak_document_in_db(flask_app.config['DATABASE'], 'completed')
        resp = logged_in_client.get(f'/api/analysis/{doc_id}/status')
        data = json.loads(resp.data)
        assert data['status'] == 'completed'

    def test_status_api_onbekend_document(self, logged_in_client):
        """Niet-bestaand document-ID geeft 404."""
        resp = logged_in_client.get('/api/analysis/99999/status')
        assert resp.status_code == 404

    def test_status_api_vereist_login(self, client, flask_app):
        """Status API zonder login → redirect of 401/403."""
        doc_id = self._maak_document_in_db(flask_app.config['DATABASE'], 'pending')
        resp = client.get(f'/api/analysis/{doc_id}/status', follow_redirects=False)
        assert resp.status_code in (301, 302, 401, 403)


class TestBasisRoutes:

    def test_index_redirect_naar_login_of_dashboard(self, client):
        """GET / zonder login → redirect."""
        resp = client.get('/', follow_redirects=False)
        assert resp.status_code in (200, 301, 302)

    def test_criteria_toegankelijk(self, logged_in_client):
        """/criteria na login → 200."""
        resp = logged_in_client.get('/criteria')
        assert resp.status_code == 200

    def test_secties_toegankelijk(self, logged_in_client):
        """/sections na login → 200."""
        resp = logged_in_client.get('/sections')
        assert resp.status_code == 200

    def test_onbekende_route_geeft_404(self, logged_in_client):
        """Niet-bestaande URL → 404."""
        resp = logged_in_client.get('/bestaat/niet/echt')
        assert resp.status_code == 404
