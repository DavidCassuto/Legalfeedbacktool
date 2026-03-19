"""
DocuCheck - Automatische database backup naar OneDrive
Kopieert instance/documents.db naar OneDrive met datum-tijdstempel.
Bewaart de laatste 30 backups; oudere worden automatisch verwijderd.

Gebruik:
    python backup_database.py              -- maakt een backup
    python backup_database.py --list       -- toont beschikbare backups
    python backup_database.py --restore    -- herstelt de meest recente backup
"""

import shutil
import sys
import os
from pathlib import Path
from datetime import datetime

# --- Configuratie ---
PROJECT_ROOT  = Path(__file__).parent
DB_SOURCE     = PROJECT_ROOT / "instance" / "documents.db"
BACKUP_DIR    = Path.home() / "OneDrive" / "DocuCheck_Backups"
MAX_BACKUPS   = 30


def maak_backup():
    if not DB_SOURCE.exists():
        print(f"FOUT: database niet gevonden op {DB_SOURCE}")
        sys.exit(1)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp    = datetime.now().strftime("%Y-%m-%d_%H-%M")
    backup_bestand = BACKUP_DIR / f"documents_{timestamp}.db"

    shutil.copy2(DB_SOURCE, backup_bestand)
    grootte_kb = backup_bestand.stat().st_size // 1024
    print(f"Backup aangemaakt: {backup_bestand.name} ({grootte_kb} KB)")

    # Verwijder backups ouder dan MAX_BACKUPS
    alle_backups = sorted(BACKUP_DIR.glob("documents_*.db"))
    te_verwijderen = alle_backups[:-MAX_BACKUPS]
    for oud in te_verwijderen:
        oud.unlink()
        print(f"Oude backup verwijderd: {oud.name}")

    print(f"Totaal backups bewaard: {min(len(alle_backups), MAX_BACKUPS)}")


def toon_backups():
    if not BACKUP_DIR.exists():
        print("Geen backupmap gevonden.")
        return
    backups = sorted(BACKUP_DIR.glob("documents_*.db"), reverse=True)
    if not backups:
        print("Geen backups gevonden.")
        return
    print(f"\nBeschikbare backups in {BACKUP_DIR}:\n")
    for i, b in enumerate(backups):
        grootte_kb = b.stat().st_size // 1024
        print(f"  {i+1:2}. {b.name}  ({grootte_kb} KB)")
    print()


def herstel_backup():
    backups = sorted(BACKUP_DIR.glob("documents_*.db"), reverse=True)
    if not backups:
        print("Geen backups beschikbaar om te herstellen.")
        sys.exit(1)
    meest_recent = backups[0]
    bevestiging = input(
        f"Wil je herstellen vanuit '{meest_recent.name}'?\n"
        f"Dit overschrijft de huidige database. Typ 'ja' om te bevestigen: "
    )
    if bevestiging.strip().lower() != 'ja':
        print("Herstel geannuleerd.")
        return
    # Maak eerst een veiligheidskopie van de huidige database
    if DB_SOURCE.exists():
        veiligheid = DB_SOURCE.with_suffix(".db.voor_herstel")
        shutil.copy2(DB_SOURCE, veiligheid)
        print(f"Huidige database opgeslagen als: {veiligheid.name}")
    shutil.copy2(meest_recent, DB_SOURCE)
    print(f"Database hersteld vanuit: {meest_recent.name}")


if __name__ == "__main__":
    if "--list" in sys.argv:
        toon_backups()
    elif "--restore" in sys.argv:
        herstel_backup()
    else:
        maak_backup()
