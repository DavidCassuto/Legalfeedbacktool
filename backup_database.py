"""
DocuCheck - Automatische database backup naar OneDrive en Google Drive
Kopieert instance/documents.db naar beide cloudlocaties met datum-tijdstempel.
Bewaart de laatste 30 backups per locatie; oudere worden automatisch verwijderd.

Gebruik:
    python backup_database.py              -- maakt een backup naar alle locaties
    python backup_database.py --list       -- toont beschikbare backups
    python backup_database.py --restore    -- herstelt de meest recente backup
"""

import shutil
import sys
from pathlib import Path
from datetime import datetime

# --- Configuratie ---
PROJECT_ROOT = Path(__file__).parent
DB_SOURCE    = PROJECT_ROOT / "instance" / "documents.db"
MAX_BACKUPS  = 30

BACKUP_LOCATIES = {
    "OneDrive":     Path.home() / "OneDrive" / "DocuCheck_Backups",
    "Google Drive": Path("G:/My Drive/DocuCheck_Backups"),
}


def kopieer_naar_locatie(naam: str, doelmap: Path, timestamp: str) -> bool:
    """Kopieert de database naar een opgegeven locatie. Geeft True terug bij succes."""
    try:
        doelmap.mkdir(parents=True, exist_ok=True)
        doelbestand = doelmap / f"documents_{timestamp}.db"
        shutil.copy2(DB_SOURCE, doelbestand)
        grootte_kb = doelbestand.stat().st_size // 1024
        print(f"  {naam}: {doelbestand.name} ({grootte_kb} KB)")

        # Verwijder backups ouder dan MAX_BACKUPS
        alle_backups = sorted(doelmap.glob("documents_*.db"))
        te_verwijderen = alle_backups[:-MAX_BACKUPS]
        for oud in te_verwijderen:
            oud.unlink()
            print(f"  {naam}: oude backup verwijderd: {oud.name}")

        return True
    except Exception as fout:
        print(f"  {naam}: MISLUKT — {fout}")
        return False


def maak_backup():
    if not DB_SOURCE.exists():
        print(f"FOUT: database niet gevonden op {DB_SOURCE}")
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    print(f"Backup aanmaken ({timestamp})...")

    resultaten = {}
    for naam, pad in BACKUP_LOCATIES.items():
        resultaten[naam] = kopieer_naar_locatie(naam, pad, timestamp)

    geslaagd = sum(resultaten.values())
    print(f"\nBackup klaar: {geslaagd}/{len(BACKUP_LOCATIES)} locaties succesvol.")
    if geslaagd == 0:
        print("WAARSCHUWING: geen enkele backup geslaagd.")
        sys.exit(1)


def toon_backups():
    for naam, pad in BACKUP_LOCATIES.items():
        print(f"\n{naam} ({pad}):")
        if not pad.exists():
            print("  Geen backupmap gevonden.")
            continue
        backups = sorted(pad.glob("documents_*.db"), reverse=True)
        if not backups:
            print("  Geen backups gevonden.")
            continue
        for i, b in enumerate(backups):
            grootte_kb = b.stat().st_size // 1024
            print(f"  {i+1:2}. {b.name}  ({grootte_kb} KB)")
    print()


def herstel_backup():
    # Zoek meest recente backup over alle locaties heen
    kandidaten = []
    for naam, pad in BACKUP_LOCATIES.items():
        if pad.exists():
            for b in pad.glob("documents_*.db"):
                kandidaten.append((b.name, b, naam))

    if not kandidaten:
        print("Geen backups beschikbaar om te herstellen.")
        sys.exit(1)

    kandidaten.sort(reverse=True)
    bestandsnaam, pad, locatie = kandidaten[0]

    bevestiging = input(
        f"Meest recente backup: '{bestandsnaam}' ({locatie})\n"
        f"Dit overschrijft de huidige database. Typ 'ja' om te bevestigen: "
    )
    if bevestiging.strip().lower() != 'ja':
        print("Herstel geannuleerd.")
        return

    if DB_SOURCE.exists():
        veiligheid = DB_SOURCE.with_suffix(".db.voor_herstel")
        shutil.copy2(DB_SOURCE, veiligheid)
        print(f"Huidige database opgeslagen als: {veiligheid.name}")

    shutil.copy2(pad, DB_SOURCE)
    print(f"Database hersteld vanuit: {bestandsnaam} ({locatie})")


if __name__ == "__main__":
    if "--list" in sys.argv:
        toon_backups()
    elif "--restore" in sys.argv:
        herstel_backup()
    else:
        maak_backup()
