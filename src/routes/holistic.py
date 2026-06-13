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

logger = logging.getLogger('docucheck.holistic')

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
    return render_template('holistic.html', product_types=PRODUCT_TYPES)


@login_required
def holistic_run():
    """Voer de holistische analyse uit en toon het resultaat."""
    file = request.files.get('file')
    rubric_text = (request.form.get('rubric_text') or '').strip()
    product_type = (request.form.get('product_type') or 'Onbekend').strip()

    # Validatie
    if not file or not file.filename:
        flash('Selecteer een Word-document (.docx).', 'danger')
        return render_template('holistic.html', product_types=PRODUCT_TYPES,
                               form={'rubric_text': rubric_text, 'product_type': product_type})
    if not file.filename.lower().endswith('.docx'):
        flash('Alleen .docx-bestanden worden ondersteund in deze prototype.', 'danger')
        return render_template('holistic.html', product_types=PRODUCT_TYPES,
                               form={'rubric_text': rubric_text, 'product_type': product_type})
    if not rubric_text:
        flash('Plak de beoordelingsrubric in het tekstvak.', 'danger')
        return render_template('holistic.html', product_types=PRODUCT_TYPES,
                               form={'rubric_text': rubric_text, 'product_type': product_type})

    work_dir = _holistic_dir()
    token = uuid.uuid4().hex[:12]
    safe_name = secure_filename(file.filename) or 'document.docx'
    in_path = os.path.join(work_dir, f"{token}_{safe_name}")
    file.save(in_path)

    out_name = f"{token}_gecommentarieerd_{safe_name}"
    out_path = os.path.join(work_dir, out_name)

    try:
        result = holistic_analysis.run_holistic_analysis(
            docx_path=in_path,
            rubric_text=rubric_text,
            product_type=product_type,
            output_path=out_path,
        )
    except Exception as e:
        logger.error("Holistische analyse mislukt: %s", e)
        traceback.print_exc()
        flash(f'Analyse mislukt: {e}', 'danger')
        return render_template('holistic.html', product_types=PRODUCT_TYPES,
                               form={'rubric_text': rubric_text, 'product_type': product_type})

    download_name = os.path.basename(result['output_path'])
    return render_template(
        'holistic.html',
        product_types=PRODUCT_TYPES,
        form={'rubric_text': rubric_text, 'product_type': product_type},
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
