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
    redirect, url_for,
)
from werkzeug.utils import secure_filename

from auth import login_required, current_user_org_id, is_admin
from database import get_db
import holistic_analysis
import rubric_extraction
import rubric_library
import languages

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


def _saved_rubrics():
    """Rubrics zichtbaar voor de huidige gebruiker: beheerder ziet alles,
    een docent (consumer) alleen de rubric(s) van de eigen organisatie."""
    uf = current_app.config['UPLOAD_FOLDER']
    if is_admin():
        return rubric_library.list_rubrics(uf)
    return rubric_library.list_rubrics(uf, organization_id=current_user_org_id())


def _organizations():
    """Alle klanten (organisaties) voor de keuzelijst."""
    rows = get_db().execute('SELECT id, name FROM organizations ORDER BY name').fetchall()
    return [{'id': r['id'], 'name': r['name']} for r in rows]


def _org_names():
    """Map organisatie-id -> naam, voor weergave in de lijst."""
    return {o['id']: o['name'] for o in _organizations()}


def _org_id_for_save():
    """Organisatie waaronder een rubric wordt opgeslagen: een beheerder kiest hem
    in het formulier; een docent krijgt automatisch zijn eigen organisatie."""
    if is_admin():
        return request.form.get('organization_id')
    return current_user_org_id()


@login_required
def holistic_form():
    """Toon het uploadformulier."""
    return render_template('holistic.html', product_types=PRODUCT_TYPES,
                           auto_detect=AUTO_DETECT, saved_rubrics=_saved_rubrics(),
                           lang_choices=languages.choices())


@login_required
def holistic_run():
    """Stap 1: bestanden ontvangen, rubric voorbereiden en een KOSTENSCHATTING tonen
    (nog geen API-call). De gebruiker bevestigt daarna in stap 2."""
    file = request.files.get('file')
    rubric_file = request.files.get('rubric_file')
    rubric_text = (request.form.get('rubric_text') or '').strip()
    saved_rubric_id = (request.form.get('saved_rubric_id') or '').strip()
    product_type = (request.form.get('product_type') or AUTO_DETECT).strip()
    include_annexes = bool(request.form.get('include_annexes'))
    taal_enabled = bool(request.form.get('taal_enabled'))
    stijl_enabled = bool(request.form.get('stijl_enabled'))
    ai_enabled = bool(request.form.get('ai_enabled'))
    show_suggestions = bool(request.form.get('show_suggestions'))
    feedback_language = (request.form.get('feedback_language') or '').strip()

    def _form_state():
        return {'rubric_text': rubric_text, 'product_type': product_type,
                'include_annexes': include_annexes, 'saved_rubric_id': saved_rubric_id,
                'taal_enabled': taal_enabled, 'stijl_enabled': stijl_enabled,
                'ai_enabled': ai_enabled, 'show_suggestions': show_suggestions,
                'feedback_language': feedback_language}

    def _back():
        return render_template('holistic.html', product_types=PRODUCT_TYPES,
                               auto_detect=AUTO_DETECT, form=_form_state(),
                               saved_rubrics=_saved_rubrics(),
                               lang_choices=languages.choices())

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

    # Rubric-bron, in volgorde van voorkeur:
    #   1) opgeslagen rubric uit de bibliotheek  2) geüpload Excel  3) geplakte tekst
    detect = (product_type == AUTO_DETECT)
    use_pt = '' if detect else product_type
    saved_cfg = {}
    if saved_rubric_id:
        rubric_text, _available = rubric_library.build_text_from_saved(
            current_app.config['UPLOAD_FOLDER'], saved_rubric_id, use_pt or None)
        if not rubric_text:
            flash('De gekozen opgeslagen rubric kon niet geladen worden.', 'danger')
            return _back()
        # Tekstuele feedback-instellingen (instructies/toon) uit de opgeslagen rubric overnemen
        rec = rubric_library.get_rubric(current_app.config['UPLOAD_FOLDER'], saved_rubric_id)
        if rec:
            saved_cfg = rec.get('feedback_config') or {}
    elif rubric_file and rubric_file.filename:
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

    # Feedback-configuratie: aan/uit + suggesties van dit formulier; instructies/toon
    # uit de opgeslagen rubric (of standaarden).
    # Feedback-taal: standaard de taal van de rubric. Mag de docent wisselen
    # (instelling op de rubric), dan telt de keuze van dit formulier.
    run_language = saved_cfg.get('language', 'nl')
    if saved_cfg.get('allow_language_override') and feedback_language:
        run_language = languages.normalize(feedback_language)

    feedback_config = {
        'taal_enabled':      taal_enabled,
        'stijl_enabled':     stijl_enabled,
        'ai_enabled':        ai_enabled,
        'show_suggestions':  show_suggestions,
        'language':          run_language,
        'allow_language_override': bool(saved_cfg.get('allow_language_override')),
        'inhoud_criteria':   saved_cfg.get('inhoud_criteria', ''),
        'onderwijs_criteria': saved_cfg.get('onderwijs_criteria', ''),
        'taal_instructies':  saved_cfg.get('taal_instructies', ''),
        'stijl_instructies': saved_cfg.get('stijl_instructies', ''),
        'ai_instructies':    saved_cfg.get('ai_instructies', ''),
        'toon':              saved_cfg.get('toon', ''),
        'max_per_categorie': saved_cfg.get('max_per_categorie'),
    }

    # Kostenschatting (zonder API)
    try:
        estimate = holistic_analysis.estimate_run(
            rubric_text=rubric_text, docx_path=in_path,
            product_type=use_pt, detect_product_type=detect,
            include_annexes=include_annexes, feedback_config=feedback_config,
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
        'feedback_config': feedback_config,
        'safe_name': safe_name, 'model': estimate['model'],
    }
    with open(os.path.join(work_dir, f"{token}_job.json"), 'w', encoding='utf-8') as f:
        json.dump(job, f)

    return render_template(
        'holistic.html', product_types=PRODUCT_TYPES, auto_detect=AUTO_DETECT,
        saved_rubrics=_saved_rubrics(), form=_form_state(),
        lang_choices=languages.choices(),
        estimate=estimate, job_token=token, original_name=safe_name,
    )


@login_required
def holistic_analyze():
    """Stap 2: de bevestigde opdracht echt uitvoeren (API-call) en resultaat tonen."""
    token = (request.form.get('job_token') or '').strip()
    if not re.fullmatch(r'[0-9a-f]{6,32}', token):
        flash('Ongeldige opdracht. Probeer opnieuw te uploaden.', 'danger')
        return render_template('holistic.html', product_types=PRODUCT_TYPES,
                               auto_detect=AUTO_DETECT, saved_rubrics=_saved_rubrics())

    work_dir = _holistic_dir()
    job_path = os.path.join(work_dir, f"{token}_job.json")
    if not os.path.isfile(job_path):
        flash('Opdracht verlopen of niet gevonden. Upload opnieuw.', 'danger')
        return render_template('holistic.html', product_types=PRODUCT_TYPES,
                               auto_detect=AUTO_DETECT, saved_rubrics=_saved_rubrics())
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
            feedback_config=job.get('feedback_config') or {},
            model=job.get('model') or holistic_analysis.DEFAULT_MODEL,
        )
    except Exception as e:
        logger.error("Holistische analyse mislukt: %s", e)
        traceback.print_exc()
        flash(f'Analyse mislukt: {e}', 'danger')
        return render_template('holistic.html', product_types=PRODUCT_TYPES,
                               auto_detect=AUTO_DETECT, saved_rubrics=_saved_rubrics())
    finally:
        try:
            os.remove(job_path)
        except OSError:
            pass

    return render_template(
        'holistic.html', product_types=PRODUCT_TYPES, auto_detect=AUTO_DETECT,
        saved_rubrics=_saved_rubrics(),
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


# ── Rubric-bibliotheek (opgeslagen rubrics) ──────────────────────────────────

@login_required
def holistic_rubrics():
    """Beheerpagina: opgeslagen rubrics tonen + nieuwe toevoegen."""
    return render_template('holistic_rubrics.html', saved_rubrics=_saved_rubrics(),
                           lang_choices=languages.choices(),
                           organizations=_organizations(), org_names=_org_names(),
                           current_org_id=current_user_org_id(), user_is_admin=is_admin(),
                           defaults={
                               'inhoud_criteria':   holistic_analysis.DEFAULT_INHOUD_CRITERIA,
                               'taal_instructies':  holistic_analysis.DEFAULT_TAAL_INSTRUCTIES,
                               'stijl_instructies': holistic_analysis.DEFAULT_STIJL_INSTRUCTIES,
                               'ai_instructies':    holistic_analysis.DEFAULT_AI_INSTRUCTIES,
                               'toon':              holistic_analysis.DEFAULT_TOON,
                               'max_per_categorie': holistic_analysis.DEFAULT_MAX_PER_CATEGORIE,
                           })


@login_required
def holistic_rubric_add():
    """Upload een Excel-formulier en bewaar het als herbruikbare rubric."""
    name = (request.form.get('name') or '').strip()
    feedback_config = {
        'language':          (request.form.get('language') or 'nl').strip(),
        'inhoud_criteria':   (request.form.get('inhoud_criteria') or '').strip(),
        'onderwijs_criteria': (request.form.get('onderwijs_criteria') or '').strip(),
        'taal_enabled':      bool(request.form.get('taal_enabled')),
        'taal_instructies':  (request.form.get('taal_instructies') or '').strip(),
        'stijl_enabled':     bool(request.form.get('stijl_enabled')),
        'stijl_instructies': (request.form.get('stijl_instructies') or '').strip(),
        'ai_enabled':        bool(request.form.get('ai_enabled')),
        'ai_instructies':    (request.form.get('ai_instructies') or '').strip(),
        'toon':              (request.form.get('toon') or '').strip(),
        'show_suggestions':  bool(request.form.get('show_suggestions')),
        'max_per_categorie': int(request.form.get('max_per_categorie') or 0) or None,
        'allow_language_override': bool(request.form.get('allow_language_override')),
    }
    rubric_file = request.files.get('rubric_file')
    if not rubric_file or not rubric_file.filename:
        flash('Selecteer een Excel-bestand (.xlsx).', 'danger')
        return redirect(url_for('holistic_rubrics'))
    if not rubric_file.filename.lower().endswith(('.xlsx', '.xlsm')):
        flash('Het beoordelingsformulier moet een Excel-bestand zijn (.xlsx).', 'danger')
        return redirect(url_for('holistic_rubrics'))

    work_dir = _holistic_dir()
    tmp = os.path.join(work_dir, f"tmp_{uuid.uuid4().hex[:8]}_{secure_filename(rubric_file.filename)}")
    rubric_file.save(tmp)
    try:
        if not name:
            name = os.path.splitext(rubric_file.filename)[0]
        rec = rubric_library.save_rubric(current_app.config['UPLOAD_FOLDER'], name, tmp,
                                         feedback_config=feedback_config,
                                         organization_id=_org_id_for_save())
        flash(f"Rubric '{rec['name']}' opgeslagen ({len(rec['tabs'])} beroepsproducten).", 'success')
    except Exception as e:
        logger.error("Rubric opslaan mislukt: %s", e)
        flash(f'Kon de rubric niet opslaan: {e}', 'danger')
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return redirect(url_for('holistic_rubrics'))


@login_required
def holistic_rubric_edit(rubric_id):
    """Toon een opgeslagen rubric: herkende tekst per tabblad + bewerkbare feedback-config."""
    rec = rubric_library.get_rubric(current_app.config['UPLOAD_FOLDER'], rubric_id)
    if not rec:
        flash('Rubric niet gevonden.', 'danger')
        return redirect(url_for('holistic_rubrics'))
    cfg = holistic_analysis._merge_config(rec.get('feedback_config'))
    return render_template('holistic_rubric_edit.html', rec=rec, cfg=cfg,
                           lang_choices=languages.choices(),
                           organizations=_organizations(),
                           user_is_admin=is_admin())


@login_required
def holistic_rubric_update(rubric_id):
    """Sla bewerkte naam + feedback-config op."""
    feedback_config = {
        'language':          (request.form.get('language') or 'nl').strip(),
        'inhoud_criteria':   (request.form.get('inhoud_criteria') or '').strip(),
        'onderwijs_criteria': (request.form.get('onderwijs_criteria') or '').strip(),
        'taal_enabled':      bool(request.form.get('taal_enabled')),
        'taal_instructies':  (request.form.get('taal_instructies') or '').strip(),
        'stijl_enabled':     bool(request.form.get('stijl_enabled')),
        'stijl_instructies': (request.form.get('stijl_instructies') or '').strip(),
        'ai_enabled':        bool(request.form.get('ai_enabled')),
        'ai_instructies':    (request.form.get('ai_instructies') or '').strip(),
        'toon':              (request.form.get('toon') or '').strip(),
        'show_suggestions':  bool(request.form.get('show_suggestions')),
        'max_per_categorie': int(request.form.get('max_per_categorie') or 0) or None,
        'allow_language_override': bool(request.form.get('allow_language_override')),
    }
    update_kwargs = {'name': request.form.get('name'), 'feedback_config': feedback_config}
    # Alleen een beheerder mag de klant-koppeling wijzigen.
    if is_admin():
        update_kwargs['organization_id'] = request.form.get('organization_id')
    rec = rubric_library.update_rubric(
        current_app.config['UPLOAD_FOLDER'], rubric_id, **update_kwargs)
    if rec:
        flash(f"Rubric '{rec['name']}' bijgewerkt.", 'success')
    else:
        flash('Rubric niet gevonden.', 'danger')
    return redirect(url_for('holistic_rubrics'))


@login_required
def holistic_rubric_distill(rubric_id):
    """Upload/plak onderwijsmateriaal -> AI distilleert inhoudelijke criteria ->
    voeg toe aan het veld 'onderwijs_criteria' van deze rubric en sla op."""
    rec = rubric_library.get_rubric(current_app.config['UPLOAD_FOLDER'], rubric_id)
    if not rec:
        flash('Rubric niet gevonden.', 'danger')
        return redirect(url_for('holistic_rubrics'))

    pasted = (request.form.get('material_text') or '').strip()
    f = request.files.get('material_file')
    material = ''
    if f and f.filename:
        if not f.filename.lower().endswith(('.docx', '.pptx', '.pdf', '.txt')):
            flash('Onderwijsmateriaal moet .docx, .pptx, .pdf of .txt zijn (of plak de tekst).', 'danger')
            return redirect(url_for('holistic_rubric_edit', rubric_id=rubric_id))
        tmp = os.path.join(_holistic_dir(),
                           f"mat_{uuid.uuid4().hex[:8]}_{secure_filename(f.filename)}")
        f.save(tmp)
        try:
            material = holistic_analysis.extract_material_text(tmp)
        except Exception as e:
            logger.error("Materiaal inlezen mislukt: %s", e)
            flash(f'Kon het materiaal niet inlezen: {e}', 'danger')
            return redirect(url_for('holistic_rubric_edit', rubric_id=rubric_id))
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    if pasted:
        material = (material + '\n\n' + pasted).strip() if material else pasted

    if not material.strip():
        flash('Geen materiaal ontvangen (upload een bestand of plak tekst).', 'danger')
        return redirect(url_for('holistic_rubric_edit', rubric_id=rubric_id))

    try:
        distilled = holistic_analysis.distill_onderwijs_criteria(material)
    except Exception as e:
        logger.error("Distilleren mislukt: %s", e)
        traceback.print_exc()
        flash(f'Distilleren mislukt: {e}', 'danger')
        return redirect(url_for('holistic_rubric_edit', rubric_id=rubric_id))

    if not distilled:
        flash('Geen inhoudelijke criteria uit het materiaal gehaald.', 'warning')
        return redirect(url_for('holistic_rubric_edit', rubric_id=rubric_id))

    cfg = rec.get('feedback_config') or {}
    existing = (cfg.get('onderwijs_criteria') or '').strip()
    cfg['onderwijs_criteria'] = (existing + '\n' + distilled).strip() if existing else distilled
    rubric_library.update_rubric(current_app.config['UPLOAD_FOLDER'], rubric_id, feedback_config=cfg)
    flash('Inhoudelijke criteria uit het onderwijsmateriaal toegevoegd — controleer en sla op.', 'success')
    return redirect(url_for('holistic_rubric_edit', rubric_id=rubric_id))


@login_required
def holistic_rubric_delete(rubric_id):
    """Verwijder een opgeslagen rubric."""
    if rubric_library.delete_rubric(current_app.config['UPLOAD_FOLDER'], rubric_id):
        flash('Rubric verwijderd.', 'success')
    else:
        flash('Rubric niet gevonden.', 'danger')
    return redirect(url_for('holistic_rubrics'))
