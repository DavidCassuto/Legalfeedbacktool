"""
DocuCheck Folder Watcher
========================
Bewaakt een map op nieuwe .docx bestanden.
Zodra een bestand verschijnt:
  1. Upload het naar de DocuCheck webapplicatie
  2. Wacht tot de analyse klaar is
  3. Download het Word-bestand met feedback
  4. Sla het op in dezelfde map als <bestandsnaam>_feedback.docx

Gebruik:
    python docucheck_watcher.py [MAP]

Standaard map: huidige werkmap (.)
Configuratie onderaan dit bestand of via omgevingsvariabelen.
"""

import os
import sys
import time
import logging
import shutil
import requests
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ---------------------------------------------------------------------------
# Configuratie — pas hier aan of stel in als omgevingsvariabele
# ---------------------------------------------------------------------------
BASE_URL        = os.environ.get('DOCUCHECK_URL',      'http://127.0.0.1:5000')
USERNAME        = os.environ.get('DOCUCHECK_USER',     'watcher')
PASSWORD        = os.environ.get('DOCUCHECK_PASSWORD', 'watcher123')
DOCUMENT_TYPE   = os.environ.get('DOCUCHECK_DOCTYPE',  '3')    # ID van documenttype
ORGANIZATION    = os.environ.get('DOCUCHECK_ORG',      '1')    # ID van organisatie
POLL_INTERVAL   = 3     # seconden tussen statuschecks
MAX_WAIT        = 300   # maximaal 5 minuten wachten op analyse
FEEDBACK_SUFFIX = '_feedback'  # toegevoegd aan bestandsnaam

# ---------------------------------------------------------------------------
# Logging — naar console EN naar instance/watcher.log
# ---------------------------------------------------------------------------
_log_path = Path(__file__).parent / 'instance' / 'watcher.log'
_log_path.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [WATCHER] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_log_path, encoding='utf-8'),
    ],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DocuCheck API-client
# ---------------------------------------------------------------------------
class DocuCheckClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.session  = requests.Session()
        self._login(username, password)

    def _login(self, username: str, password: str):
        resp = self.session.post(
            f'{self.base_url}/login',
            data={'username': username, 'password': password},
            allow_redirects=True,
            timeout=10,
        )
        # Login is geslaagd als:
        # - de sessie-cookie aanwezig is (Flask stuurt 'session' cookie)
        # - OF we niet meer op de login-pagina staan
        # - OF de response "Uitloggen" bevat
        has_session_cookie = any(
            c.name == 'session' for c in self.session.cookies
        )
        still_on_login = (
            'login' in resp.url.lower()
            and 'Ongeldige' in resp.text
        )
        if still_on_login or not has_session_cookie:
            raise RuntimeError(
                f'Inloggen mislukt voor gebruiker "{username}". '
                f'Controleer DOCUCHECK_USER en DOCUCHECK_PASSWORD in de watcher-configuratie.'
            )
        log.info('Ingelogd als %s', username)

    def upload(self, file_path: Path, document_type_id: str, organization_id: str) -> int:
        """Upload een .docx bestand via de JSON API. Geeft het document_id terug."""
        with open(file_path, 'rb') as f:
            resp = self.session.post(
                f'{self.base_url}/api/upload',
                data={
                    'document_type_id': document_type_id,
                    'organization_id':  organization_id,
                },
                files={'file': (file_path.name, f,
                                'application/vnd.openxmlformats-officedocument'
                                '.wordprocessingml.document')},
                timeout=30,
            )

        if resp.status_code == 201:
            doc_id = resp.json()['document_id']
            log.info('Document geupload: id=%d', doc_id)
            return doc_id

        raise RuntimeError(
            f'Upload mislukt (HTTP {resp.status_code}): {resp.text[:200]}'
        )

    def wait_for_analysis(self, document_id: int,
                          poll_interval: int = POLL_INTERVAL,
                          max_wait: int = MAX_WAIT) -> bool:
        """Wacht tot de analyse klaar is. Geeft True terug bij succes."""
        url = f'{self.base_url}/api/analysis/{document_id}/status'
        elapsed = 0
        while elapsed < max_wait:
            try:
                resp = self.session.get(url, timeout=10)
                status = resp.json().get('status', '')
            except Exception as exc:
                log.warning('Statuscheck mislukt: %s', exc)
                status = 'unknown'

            if status == 'completed':
                log.info('Analyse voltooid (document %d)', document_id)
                return True
            elif status == 'failed':
                log.error('Analyse mislukt (document %d)', document_id)
                return False
            else:
                log.info('Analyse bezig... (%ds)', elapsed)
                time.sleep(poll_interval)
                elapsed += poll_interval

        log.error('Timeout na %ds (document %d)', max_wait, document_id)
        return False

    def download_feedback(self, document_id: int, output_path: Path) -> bool:
        """Download het feedback Word-document."""
        resp = self.session.get(
            f'{self.base_url}/documents/{document_id}/export',
            timeout=30,
            stream=True,
        )
        if resp.status_code != 200:
            log.error('Download mislukt: HTTP %d', resp.status_code)
            return False

        with open(output_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        log.info('Feedback opgeslagen: %s', output_path)
        return True


# ---------------------------------------------------------------------------
# Bestandssysteem-watcher
# ---------------------------------------------------------------------------
class DocxHandler(FileSystemEventHandler):
    def __init__(self, client: DocuCheckClient, watch_dir: Path):
        self.client    = client
        self.watch_dir = watch_dir
        self._seen: set = set()  # bijhouden welke bestanden al verwerkt zijn

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        self._process(path)

    def on_moved(self, event):
        """Vangt ook bestanden op die in de map worden gesleept (move = create)."""
        if event.is_directory:
            return
        path = Path(event.dest_path)
        self._process(path)

    def _process(self, path: Path):
        # Alleen .docx, geen feedback-bestanden, niet dubbel verwerken
        if path.suffix.lower() != '.docx':
            return
        if FEEDBACK_SUFFIX in path.stem:
            return
        if path in self._seen:
            return
        self._seen.add(path)

        log.info('Nieuw bestand gevonden: %s', path.name)

        # Even wachten tot het bestand volledig geschreven is
        time.sleep(2)
        if not path.exists():
            log.warning('Bestand verdwenen voor verwerking: %s', path.name)
            return

        output_path = path.parent / f'{path.stem}{FEEDBACK_SUFFIX}.docx'

        try:
            doc_id = self.client.upload(path, DOCUMENT_TYPE, ORGANIZATION)
            success = self.client.wait_for_analysis(doc_id)
            if success:
                self.client.download_feedback(doc_id, output_path)
                log.info('Klaar: %s', output_path.name)
            else:
                log.error('Analyse mislukt voor %s', path.name)
        except Exception as exc:
            log.error('Fout bij verwerken van %s: %s', path.name, exc)


# ---------------------------------------------------------------------------
# Hoofdprogramma
# ---------------------------------------------------------------------------
def main():
    watch_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('.')
    watch_dir = watch_dir.resolve()

    if not watch_dir.is_dir():
        log.error('Map bestaat niet: %s', watch_dir)
        sys.exit(1)

    log.info('DocuCheck Watcher gestart')
    log.info('Bewaking: %s', watch_dir)
    log.info('Server:   %s', BASE_URL)
    log.info('Druk op Ctrl+C om te stoppen')

    # Controleer of de server bereikbaar is voordat we starten
    try:
        requests.get(BASE_URL, timeout=5)
    except requests.exceptions.ConnectionError:
        log.error(
            'Kan de DocuCheck server niet bereiken op %s\n'
            '  Zorg dat de server draait: venv_lokaal\\Scripts\\python src\\main.py',
            BASE_URL
        )
        sys.exit(1)

    try:
        client = DocuCheckClient(BASE_URL, USERNAME, PASSWORD)
    except RuntimeError as exc:
        log.error('Inloggen mislukt: %s', exc)
        sys.exit(1)

    handler  = DocxHandler(client, watch_dir)
    observer = Observer()
    observer.schedule(handler, str(watch_dir), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        log.info('Watcher gestopt')

    observer.join()


if __name__ == '__main__':
    main()
