"""WSGI entry point voor productie (gunicorn / Railway)."""
import sys
import os

# Voeg src/ toe aan het pad zodat alle imports werken
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from main import app  # noqa: F401 — gunicorn gebruikt de 'app' variabele

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
