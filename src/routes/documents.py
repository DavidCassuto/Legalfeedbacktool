# src/routes/documents.py
"""Document-routes: upload, overzicht, analyse, export, heranalyse, status-API."""

import os
import re
import json
import sqlite3
import threading
import traceback
import uuid as _uuid

from flask import (
    render_template, request, redirect, url_for, flash,
    session, jsonify, send_file, current_app
)
from werkzeug.utils import secure_filename

from database import get_db
from auth import login_required, admin_required, current_user_id, is_admin
from analysis_runner import (
    _analysis_in_progress, _analysis_lock,
    run_analysis_background, run_partial_reanalysis_background,
)
from analysis.inline_word_comments import add_inline_comments
import db_utils


@login_required
def upload_document():
    """Route voor het uploaden van een nieuw document."""
    db = get_db()
    document_types = db.execute('SELECT id, name FROM document_types').fetchall()

    try:
        organizations = db.execute('SELECT id, name FROM organizations').fetchall()
    except sqlite3.OperationalError:
        organizations = []

    form_data = {}

    if request.method == 'POST':
        form_data = request.form

        file = request.files.get('file')
        document_type_id = request.form.get('document_type_id')
        organization_id  = request.form.get('organization_id')

        if not file or file.filename == '':
            flash('Geen bestand geselecteerd!', 'danger')
        elif not document_type_id:
            flash('Selecteer een documenttype!', 'danger')
        else:
            try:
                original_filename = file.filename
                if original_filename is None:
                    flash('Ongeldige bestandsnaam!', 'danger')
                    return render_template('upload.html',
                                           document_types=document_types,
                                           organizations=organizations,
                                           form_data=form_data)

                filename  = secure_filename(original_filename)
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)

                document_id = db_utils.get_or_create_document(db, original_filename, file_path)

                file_size = os.path.getsize(file_path)
                db.execute(
                    'UPDATE documents SET document_type_id=?, organization_id=?, '
                    'file_size=?, analysis_status=?, uploaded_by=?, '
                    'uploaded_at=CURRENT_TIMESTAMP WHERE id=?',
                    (document_type_id, organization_id, file_size,
                     'pending', current_user_id(), document_id)
                )
                db.commit()

                flash('Document succesvol geupload! Starten met analyse...', 'success')
                return redirect(url_for('document_analysis', document_id=document_id))

            except Exception as e:
                flash(f'Fout bij uploaden: {e}', 'danger')
                traceback.print_exc()

    return render_template('upload.html',
                           document_types=document_types,
                           organizations=organizations,
                           form_data=form_data)


@login_required
def api_upload_document():
    """JSON-endpoint voor de watcher: upload document, geef direct het document_id terug."""
    file = request.files.get('file')
    document_type_id = request.form.get('document_type_id') or request.form.get('document_type')
    organization_id  = request.form.get('organization_id')  or request.form.get('organization')

    if not file or not file.filename:
        return jsonify({'error': 'Geen bestand'}), 400
    if not document_type_id:
        return jsonify({'error': 'document_type_id vereist'}), 400

    try:
        db = get_db()
        original_filename = file.filename
        filename  = secure_filename(original_filename)
        base, ext = os.path.splitext(filename)
        filename  = f"{base}_{_uuid.uuid4().hex[:8]}{ext}"
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        db.execute(
            '''INSERT INTO documents
               (name, original_filename, file_path, file_size,
                document_type_id, organization_id, analysis_status, uploaded_by)
               VALUES (?,?,?,?,?,?,?,?)''',
            (original_filename, original_filename, file_path,
             os.path.getsize(file_path),
             document_type_id, organization_id or None,
             'pending', current_user_id())
        )
        db.commit()
        document_id = db.execute('SELECT last_insert_rowid()').fetchone()[0]

        # Start achtergrond-analyse direct
        flask_app = current_app._get_current_object()
        database  = current_app.config['DATABASE']
        with _analysis_lock:
            if document_id not in _analysis_in_progress:
                _analysis_in_progress.add(document_id)
                db.execute('UPDATE documents SET analysis_status=? WHERE id=?',
                           ('analyzing', document_id))
                db.commit()
                threading.Thread(
                    target=run_analysis_background,
                    args=(document_id, flask_app, database),
                    daemon=True,
                ).start()

        return jsonify({'document_id': document_id}), 201

    except Exception as exc:
        traceback.print_exc()
        return jsonify({'error': str(exc)}), 500


@login_required
def list_documents():
    """Overzichtspagina van geuploadde documenten.
    Admins zien alle documenten; consumenten zien alleen hun eigen documenten."""
    db = get_db()
    if is_admin():
        documents = db.execute('''
            SELECT d.*, dt.name AS document_type_name, o.name AS organization_name,
                   u.username AS uploader_name
            FROM documents d
            JOIN document_types dt ON d.document_type_id = dt.id
            LEFT JOIN organizations o ON d.organization_id = o.id
            LEFT JOIN users u ON d.uploaded_by = u.id
            ORDER BY d.uploaded_at DESC
        ''').fetchall()
    else:
        documents = db.execute('''
            SELECT d.*, dt.name AS document_type_name, o.name AS organization_name,
                   u.username AS uploader_name
            FROM documents d
            JOIN document_types dt ON d.document_type_id = dt.id
            LEFT JOIN organizations o ON d.organization_id = o.id
            LEFT JOIN users u ON d.uploaded_by = u.id
            WHERE d.uploaded_by = ?
            ORDER BY d.uploaded_at DESC
        ''', (current_user_id(),)).fetchall()
    return render_template('documents.html', documents=documents)


@login_required
def analysis_status_api(document_id):
    """JSON-endpoint: geeft de huidige analysestatus terug (voor polling)."""
    db = get_db()
    row = db.execute(
        'SELECT analysis_status FROM documents WHERE id=?', (document_id,)
    ).fetchone()
    if not row:
        return jsonify({'status': 'not_found'}), 404
    return jsonify({'status': row['analysis_status']})


@login_required
def document_analysis(document_id):
    """Gedetailleerde analyseweergave voor een specifiek document."""
    db = get_db()

    document = db.execute('SELECT * FROM documents WHERE id=?', (document_id,)).fetchone()
    if document is None:
        flash('Document niet gevonden.', 'danger')
        return redirect(url_for('list_documents'))

    document_type = db.execute(
        'SELECT * FROM document_types WHERE id=?', (document['document_type_id'],)
    ).fetchone()
    if document_type is None:
        flash('Documenttype niet gevonden voor dit document.', 'danger')
        return redirect(url_for('list_documents'))

    organization = db.execute(
        'SELECT * FROM organizations WHERE id=?', (document['organization_id'],)
    ).fetchone()

    if not os.path.exists(document['file_path']):
        flash(f"Bestand '{document['original_filename']}' niet gevonden op server.", 'danger')
        db.execute('UPDATE documents SET analysis_status=? WHERE id=?', ('failed', document_id))
        db.commit()
        return redirect(url_for('list_documents'))

    needs_analysis = (
        document['analysis_status'] in ('pending', 'failed')
        or bool(request.args.get('reanalyze'))
    )

    if needs_analysis:
        flask_app = current_app._get_current_object()
        database  = current_app.config['DATABASE']
        with _analysis_lock:
            if document_id not in _analysis_in_progress:
                _analysis_in_progress.add(document_id)
                db.execute('UPDATE documents SET analysis_status=? WHERE id=?',
                           ('analyzing', document_id))
                db.commit()
                t = threading.Thread(
                    target=run_analysis_background,
                    args=(document_id, flask_app, database),
                    daemon=True,
                )
                t.start()
                print(f"[ASYNC] Achtergrond-thread gestart voor document {document_id}")

    # Laadpagina zolang analyse bezig is
    if document['analysis_status'] in ('analyzing', 'pending') or document_id in _analysis_in_progress:
        return render_template('analysis_loading.html',
                               document=document,
                               document_type=document_type,
                               organization=organization)

    # Analyse mislukt
    if document['analysis_status'] == 'failed':
        flash('De analyse is mislukt. Probeer het opnieuw.', 'danger')
        return render_template('analysis_loading.html',
                               document=document,
                               document_type=document_type,
                               organization=organization,
                               failed=True)

    # Resultaten laden
    try:
        analysis_data = json.loads(document['analysis_data'] or '{}')
        display_sections       = analysis_data.get('sections', [])
        generated_feedback_items = analysis_data.get('feedback', [])
    except (json.JSONDecodeError, TypeError):
        display_sections         = []
        generated_feedback_items = []

    feedback_stats = {
        'violations': len([f for f in generated_feedback_items if f.get('status') in ('violation', 'error')]),
        'warnings':   len([f for f in generated_feedback_items if f.get('status') == 'warning']),
        'info':       len([f for f in generated_feedback_items if f.get('status') == 'info']),
        'passed':     len([f for f in generated_feedback_items if f.get('status') == 'ok']),
    }

    def split_into_paragraphs_for_display(content):
        content = content.replace('\r\n', '\n').replace('\r', '\n')

        def is_heading_like(line):
            words = re.findall(r'\b\w+\b', line)
            return len(words) <= 10 and not re.search(r'[.!?]$', line.strip())

        paragraphs = []
        current = []
        for line in content.split('\n'):
            s = line.strip()
            if not s:
                if current:
                    paragraphs.append(' '.join(current))
                    current = []
            elif is_heading_like(s):
                if current:
                    paragraphs.append(' '.join(current))
                    current = []
            else:
                current.append(s)
        if current:
            paragraphs.append(' '.join(current))
        return paragraphs

    for section in display_sections:
        section['paragraphs'] = split_into_paragraphs_for_display(section.get('content', ''))

    feedback_by_section  = {}
    non_section_feedback = []
    for fb in generated_feedback_items:
        sname = fb.get('section_name')
        if sname:
            feedback_by_section.setdefault(sname, []).append(fb)
        else:
            non_section_feedback.append(fb)

    return render_template('analysis.html',
                           document=document,
                           document_type=document_type,
                           organization=organization,
                           sections=display_sections,
                           feedback_items=generated_feedback_items,
                           feedback_by_section=feedback_by_section,
                           non_section_feedback=non_section_feedback,
                           feedback_stats=feedback_stats)


@login_required
def export_document(document_id):
    """Exporteer feedback naar Word document."""
    db = get_db()

    document = db.execute('SELECT * FROM documents WHERE id=?', (document_id,)).fetchone()
    if document is None:
        flash('Document niet gevonden.', 'danger')
        return redirect(url_for('list_documents'))

    try:
        if not document['analysis_data']:
            flash('Geen analyse data beschikbaar voor export.', 'danger')
            return redirect(url_for('document_analysis', document_id=document_id))

        analysis_data  = json.loads(document['analysis_data'])
        feedback_items = analysis_data.get('feedback', [])
        saved_sections = analysis_data.get('sections', [])

        if not os.path.exists(document['file_path']):
            flash('Origineel bestand niet gevonden op de server.', 'danger')
            return redirect(url_for('document_analysis', document_id=document_id))

        base_name       = os.path.splitext(document['original_filename'])[0]
        export_filename = f"{base_name}_gecommentarieerd.docx"
        export_path     = os.path.join(current_app.config['UPLOAD_FOLDER'], export_filename)

        add_inline_comments(
            original_docx_path  = document['file_path'],
            feedback_items      = feedback_items,
            recognized_sections = saved_sections,
            output_path         = export_path,
        )

        return send_file(export_path, as_attachment=True, download_name=export_filename)

    except Exception as e:
        flash(f'Fout bij export: {e}', 'danger')
        traceback.print_exc()
        return redirect(url_for('document_analysis', document_id=document_id))


@login_required
def export_select(document_id):
    """
    GET  → pagina met aanvinkbare secties.
    POST → genereer Word-export alleen voor de geselecteerde secties.
    """
    db = get_db()
    document = db.execute('SELECT * FROM documents WHERE id=?', (document_id,)).fetchone()
    if document is None:
        flash('Document niet gevonden.', 'danger')
        return redirect(url_for('list_documents'))

    if not document['analysis_data']:
        flash('Dit document heeft nog geen analyse. Analyseer het document eerst.', 'warning')
        return redirect(url_for('document_analysis', document_id=document_id))

    analysis_data  = json.loads(document['analysis_data'])
    feedback_items = analysis_data.get('feedback', [])
    saved_sections = analysis_data.get('sections', [])

    # Bouw een overzicht: gevonden secties + aantal feedback-items per sectie
    found_sections = [s for s in saved_sections if s.get('found')]
    counts = {}
    for fi in feedback_items:
        sn = fi.get('section_name', '')
        if sn:
            counts[sn] = counts.get(sn, 0) + (1 if fi.get('status') not in ('ok',) else 0)

    # Voeg document-brede feedback samen onder een aparte sleutel
    doc_wide = [fi for fi in feedback_items if not fi.get('section_name')]
    doc_wide_count = sum(1 for fi in doc_wide if fi.get('status') not in ('ok',))

    if request.method == 'POST':
        selected = request.form.getlist('sections')
        include_doc_wide = 'doc_wide' in request.form

        if not selected and not include_doc_wide:
            flash('Selecteer minimaal één sectie of de document-brede feedback.', 'warning')
            return redirect(url_for('export_select', document_id=document_id))

        # Filter feedback op geselecteerde secties
        filtered = []
        if include_doc_wide:
            filtered += doc_wide
        for fi in feedback_items:
            if fi.get('section_name') in selected:
                filtered.append(fi)

        try:
            if not os.path.exists(document['file_path']):
                flash('Origineel bestand niet gevonden op de server.', 'danger')
                return redirect(url_for('export_select', document_id=document_id))

            base_name       = os.path.splitext(document['original_filename'])[0]
            sections_label  = '_'.join(s[:12].replace(' ', '') for s in selected[:3])
            if len(selected) > 3:
                sections_label += f'_plus{len(selected)-3}'
            export_filename = f"{base_name}_comments_{sections_label or 'doc'}.docx"
            export_path     = os.path.join(current_app.config['UPLOAD_FOLDER'], export_filename)

            add_inline_comments(
                original_docx_path  = document['file_path'],
                feedback_items      = filtered,
                recognized_sections = saved_sections,
                output_path         = export_path,
            )
            return send_file(export_path, as_attachment=True, download_name=export_filename)

        except Exception as e:
            flash(f'Fout bij export: {e}', 'danger')
            traceback.print_exc()
            return redirect(url_for('export_select', document_id=document_id))

    return render_template(
        'export_select.html',
        document        = document,
        found_sections  = found_sections,
        counts          = counts,
        doc_wide_count  = doc_wide_count,
    )


@login_required
def reanalyze_partial(document_id):
    """
    Start een gedeeltelijke heranalyse: alleen de aangevinkte secties worden
    opnieuw beoordeeld. Bestaande feedback voor andere secties blijft intact.
    """
    db = get_db()
    document = db.execute('SELECT * FROM documents WHERE id=?', (document_id,)).fetchone()
    if document is None:
        flash('Document niet gevonden.', 'danger')
        return redirect(url_for('list_documents'))

    if not document['analysis_data']:
        flash('Dit document heeft nog geen analyse. Analyseer het document eerst volledig.', 'warning')
        return redirect(url_for('document_analysis', document_id=document_id))

    selected      = request.form.getlist('sections')
    include_doc_wide = 'doc_wide' in request.form

    if not selected and not include_doc_wide:
        flash('Selecteer minimaal één sectie of de document-brede feedback.', 'warning')
        return redirect(url_for('export_select', document_id=document_id))

    with _analysis_lock:
        if document_id in _analysis_in_progress:
            flash('Er loopt al een analyse voor dit document. Wacht tot die klaar is.', 'warning')
            return redirect(url_for('document_analysis', document_id=document_id))
        _analysis_in_progress.add(document_id)

    db.execute(
        'UPDATE documents SET analysis_status=? WHERE id=?',
        ('analyzing', document_id)
    )
    db.commit()

    flask_app = current_app._get_current_object()
    database  = current_app.config['DATABASE']
    t = threading.Thread(
        target=run_partial_reanalysis_background,
        args=(document_id, selected, include_doc_wide, flask_app, database),
        daemon=True,
    )
    t.start()
    flash(
        f'Heranalyse gestart voor {len(selected)} sectie(s)'
        + (' + document-brede checks' if include_doc_wide else '')
        + '. De pagina ververst automatisch.',
        'info',
    )
    return redirect(url_for('document_analysis', document_id=document_id))


@login_required
def reanalyze_document(document_id):
    """Forceer heranalyse van een document."""
    return redirect(url_for('document_analysis', document_id=document_id, reanalyze=True))
