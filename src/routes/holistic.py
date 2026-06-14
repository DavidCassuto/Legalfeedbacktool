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
    """Voer de holistische analyse uit en toon het resultaat."""
    file = request.files.get('file')
    rubric_file = request.files.get('rubric_file')
    rubric_text = (request.form.get('rubric_text') or '').strip()
    product_type = (request.form.get('product_type') or AUTO_DETECT).strip()
    include_annexes = bool(request.form.get('include_annexes'))

    def _back(extra=None):
        form = {'rubric_text': rubric_text, 'product_type': product_type,
                'include_annexes': include_annexes}
        if extra:
            form.update(extra)
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
            rubric_text, available = rubric_extraction.build_rubric_text(rubric_path, use_pt or None)
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

    out_name = f"{token}_gecommentarieerd_{safe_name}"
    out_path = os.path.join(work_dir, out_name)

    try:
        result = holistic_analysis.run_holistic_analysis(
            docx_path=in_path,
            rubric_text=rubric_text,
            product_type=use_pt or 'Onbekend',
            output_path=out_path,
            detect_product_type=detect,
            include_annexes=include_annexes,
        )
    except Exception as e:
        logger.error("Holistische analyse mislukt: %s", e)
        traceback.print_exc()
        flash(f'Analyse mislukt: {e}', 'danger')
        return _back()

    download_name = os.path.basename(result['output_path'])
    return render_template(
        'holistic.html',
        product_types=PRODUCT_TYPES,
        auto_detect=AUTO_DETECT,
        form={'rubric_text': rubric_text, 'product_type': product_type,
              'include_annexes': include_annexes},
        result=result,
        download_name=download_name,
        original_name=safe_name,
    )


@login_required
def holistic_download(naam):
    """Serveer een gegenereerd, gecommentarieerd .docx."""
    safe = secure_filename(naam)
    path = os.path.join(_holistic_dir(), safe)
    if not os.path.isfile(path):
        abort(404)
    return send_file(path, as_attachment=True, download_name=safe)
