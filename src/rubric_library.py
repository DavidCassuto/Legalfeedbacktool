# src/rubric_library.py
"""
Opgeslagen-rubric-bibliotheek (PROTOTYPE).

Een school uploadt het Excel-beoordelingsformulier ÉÉN keer; de geëxtraheerde
rubric-tabs worden hier bewaard zodat volgende analyses de rubric uit de lijst
kunnen kiezen i.p.v. het bestand opnieuw te uploaden.

Bestandsgebaseerd (geen DB-wijziging): elke rubric is één JSON-bestand in
INSTANCE/uploads/holistic_library/. Voor de commerciële versie zou dit een
per-organisatie tabel in de database worden.
"""

import os
import re
import json
import uuid
from datetime import datetime

import rubric_extraction


def _library_dir(upload_folder: str) -> str:
    d = os.path.join(upload_folder, 'holistic_library')
    os.makedirs(d, exist_ok=True)
    return d


def _safe_id(rubric_id: str) -> str | None:
    return rubric_id if re.fullmatch(r'[0-9a-f]{6,32}', rubric_id or '') else None


def save_rubric(upload_folder: str, name: str, xlsx_path: str) -> dict:
    """Extraheer de tabs uit het Excel-bestand en sla ze op onder een naam."""
    tabs = rubric_extraction.extract_rubric_tabs(xlsx_path)
    if not tabs:
        raise ValueError("Geen rubric-tekst gevonden in het Excel-bestand.")
    rubric_id = uuid.uuid4().hex[:12]
    record = {
        'id':         rubric_id,
        'name':       (name or 'Naamloze rubric').strip(),
        'tabs':       tabs,
        'created_at': datetime.now().isoformat(timespec='seconds'),
    }
    path = os.path.join(_library_dir(upload_folder), f"{rubric_id}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False)
    return record


def list_rubrics(upload_folder: str) -> list[dict]:
    """Lijst van opgeslagen rubrics (zonder de volledige tekst), nieuwste eerst."""
    out = []
    d = _library_dir(upload_folder)
    for fn in os.listdir(d):
        if not fn.endswith('.json'):
            continue
        try:
            with open(os.path.join(d, fn), encoding='utf-8') as f:
                rec = json.load(f)
            out.append({
                'id':         rec['id'],
                'name':       rec.get('name', ''),
                'tab_names':  list((rec.get('tabs') or {}).keys()),
                'created_at': rec.get('created_at', ''),
            })
        except (json.JSONDecodeError, KeyError, OSError):
            continue
    out.sort(key=lambda r: r.get('created_at', ''), reverse=True)
    return out


def get_rubric(upload_folder: str, rubric_id: str) -> dict | None:
    rid = _safe_id(rubric_id)
    if not rid:
        return None
    path = os.path.join(_library_dir(upload_folder), f"{rid}.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def delete_rubric(upload_folder: str, rubric_id: str) -> bool:
    rid = _safe_id(rubric_id)
    if not rid:
        return False
    path = os.path.join(_library_dir(upload_folder), f"{rid}.json")
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False


def build_text_from_saved(upload_folder: str, rubric_id: str,
                          product_type: str | None) -> tuple[str, list[str]]:
    """Bouw rubric-tekst uit een opgeslagen rubric (zelfde logica als een upload)."""
    rec = get_rubric(upload_folder, rubric_id)
    if not rec:
        return '', []
    return rubric_extraction.combine_tabs(rec.get('tabs') or {}, product_type)
