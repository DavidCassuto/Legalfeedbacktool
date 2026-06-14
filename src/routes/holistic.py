# src/routes/holistic.py
"""
PROTOTYPE-routes voor de holistische LLM-first analyse.

Flow:
  GET  /holistic            -> uploadformulier (student-.docx + rubric-tekst + producttype)
  POST /holistic            -> analyse uitvoeren, resultaat tonen
  GET  /holistic/download/<naam> -> gecommentarieerd .docx downloaden

Staat los van de bestaande document-pipeline; gebruikt geen secties/criteria/mappings.
"""

import os
import re
import json
import uuid
import traceback
import logging

from flask import (
    render_template, request, send_file, current_app, flash, abort,
)
from werkzeug.utils import secure_filename

from auth import login_required
import holistic_analysis
import rubric_extraction

logger = logging.getLogger('docucheck.holistic')

# Speciale waarde: laat de LLM zelf het beroepsproduct bepalen
AUTO_DETECT = '__auto__'

# Productsoorten uit het beoordelingsformulier van de opleiding
PRODUCT_TYPES = ['PvA', 'Analyse', 'Advies', 'Ontwerp', 'Fabricaat', 'Eindgesprek']


def _holistic_dir() -> str:
    """Submap binnen UPLOAD_FOLDER voor prototype-bestanden."""
    d = os.path.join(current_app.config['UPLOAD_FOLDER'], 'holistic')
    os.makedirs(d, exist_ok=True)
    return d


@login_required
def holistic_form():
    """Toon het uploadformulier."""
    return render_template('holistic.html', product_types=PRODUCT_TYPES,
                           auto_detect=AUTO_DETECT)


@login_required
def holistic_run():
    """Stap 1: bestanden ontvangen, rubric voorbereiden en een KOSTENSCHATTING tonen
    (nog geen API-call). De gebruiker bevestigt daarna in stap 2."""
    file = request.files.get('file')
    rubric_file = request.files.get('rubric_file')
    rubric_text = (request.form.get('rubric_text') or '').strip()
    product_type = (request.form.get('product_type') or AUTO_DETECT).strip()
    include_annexes = bool(request.form.get('include_annexes'))

    def _back():
        form = {'rubric_text': rubric_text, 'product_type': product_type,
                'include_annexes': include_annexes}
        return render_template('holistic.html', product_types=PRODUCT_TYPES,
                               auto_detect=AUTO_DETECT, form=form)

    # Validatie: studentdocument
    if not file or not file.filename:
        flash('Selecteer een Word-document (.docx).', 'danger')
        return _back()
    if not file.filename.lower().endswith('.docx'):
        flash('Alleen .docx-bestanden worden ondersteund in deze prototype.', 'danger')
        return _back()

    work_dir = _holistic_dir()
    token = uuid.uuid4().hex[:12]
    safe_name = secure_filename(file.filename) or 'document.docx'
    in_path = os.path.join(work_dir, f"{token}_{safe_name}")
    file.save(in_path)

    # Rubric-bron: bij voorkeur het geüploade Excel-formulier, anders geplakte tekst
    detect = (product_type == AUTO_DETECT)
    use_pt = '' if detect else product_type
    if rubric_file and rubric_file.filename:
        if not rubric_file.filename.lower().endswith(('.xlsx', '.xlsm')):
            flash('Het beoordelingsformulier moet een Excel-bestand zijn (.xlsx).', 'danger')
            return _back()
        rubric_path = os.path.join(work_dir, f"{token}_rubric_{secure_filename(rubric_file.filename)}")
        rubric_file.save(rubric_path)
        try:
            rubric_text, _available = rubric_extraction.build_rubric_text(rubric_path, use_pt or None)
        except Exception as e:
            logger.error("Rubric-extractie mislukt: %s", e)
            flash(f'Kon de rubric niet uit het Excel-bestand lezen: {e}', 'danger')
            return _back()
        if not rubric_text:
            flash('Geen rubric-tekst gevonden in het Excel-bestand.', 'danger')
            return _back()
    elif not rubric_text:
        flash('Upload het Excel-beoordelingsformulier of plak de rubric als tekst.', 'danger')
        return _back()

    out_path = os.path.join(work_dir, f"{token}_gecommentarieerd_{safe_name}")

    # Kostenschatting (zonder API)
    try:
        estimate = holistic_analysis.estimate_run(
            rubric_text=rubric_text, docx_path=in_path,
            product_type=use_pt, detect_product_type=detect,
            include_annexes=include_annexes,
        )
    except Exception as e:
        logger.error("Kostenschatting mislukt: %s", e)
        traceback.print_exc()
        flash(f'Kon het document niet inlezen: {e}', 'danger')
        return _back()

    # Bewaar de voorbereide opdracht zodat stap 2 hem kan uitvoeren
    job = {
        'in_path': in_path, 'out_path': out_path, 'rubric_text': rubric_text,
        'product_type': use_pt, 'detect': detect, 'include_annexes': include_annexes,
        'safe_name': safe_name, 'model': estimate['model'],
    }
    with open(os.path.join(work_dir, f"{token}_job.json"), 'w', encoding='utf-8') as f:
        json.dump(job, f)

    return render_template(
        'holistic.html', product_types=PRODUCT_TYPES, auto_detect=AUTO_DETECT,
        form={'rubric_text': rubric_text, 'product_type': product_type,
              'include_annexes': include_annexes},
        estimate=estimate, job_token=token, original_name=safe_name,
    )


@login_required
def holistic_analyze():
    """Stap 2: de bevestigde opdracht echt uitvoeren (API-call) en resultaat tonen."""
    token = (request.form.get('job_token') or '').strip()
    if not re.fullmatch(r'[0-9a-f]{6,32}', token):
        flash('Ongeldige opdracht. Probeer opnieuw te uploaden.', 'danger')
        return render_template('holistic.html', product_types=PRODUCT_TYPES,
                               auto_detect=AUTO_DETECT)

    work_dir = _holistic_dir()
    job_path = os.path.join(work_dir, f"{token}_job.json")
    if not os.path.isfile(job_path):
        flash('Opdracht verlopen of niet gevonden. Upload opnieuw.', 'danger')
        return render_template('holistic.html', product_types=PRODUCT_TYPES,
                               auto_detect=AUTO_DETECT)
    with open(job_path, encoding='utf-8') as f:
        job = json.load(f)

    try:
        result = holistic_analysis.run_holistic_analysis(
            docx_path=job['in_path'],
            rubric_text=job['rubric_text'],
            product_type=job['product_type'] or 'Onbekend',
            output_path=job['out_path'],
            detect_product_type=job['detect'],
            include_annexes=job['include_annexes'],
            model=job.get('model') or holistic_analysis.DEFAULT_MODEL,
        )
    except Exception as e:
        logger.error("Holistische analyse mislukt: %s", e)
        traceback.print_exc()
        flash(f'Analyse mislukt: {e}', 'danger')
        return render_template('holistic.html', product_types=PRODUCT_TYPES,
                               auto_detect=AUTO_DETECT)
    finally:
        try:
            os.remove(job_path)
        except OSError:
            pass

    return render_template(
        'holistic.html', product_types=PRODUCT_TYPES, auto_detect=AUTO_DETECT,
        result=result, download_name=os.path.basename(result['output_path']),
        original_name=job.get('safe_name', 'document.docx'),
    )


@login_required
def holistic_download(naam):
    """Serveer een gegenereerd, gecommentarieerd .docx."""
    safe = secure_filename(naam)
    path = os.path.join(_holistic_dir(), safe)
    if not os.path.isfile(path):
        abort(404)
    return send_file(path, as_attachment=True, download_name=safe)
