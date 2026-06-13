# src/routes/criteria.py
"""Criteria management routes: lijst, toevoegen, bewerken, verwijderen, secties mappen."""

import json
import traceback

from flask import render_template, request, redirect, url_for, flash

from database import get_db
from auth import admin_required


@admin_required
def list_criteria():
    """Overzichtspagina van alle criteria."""
    db = get_db()
    criteria = db.execute('''
        SELECT c.*, o.name AS organization_name
        FROM criteria c
        LEFT JOIN organizations o ON c.organization_id = o.id
        ORDER BY c.name
    ''').fetchall()
    return render_template('criteria_list.html', criteria=criteria)


def _build_parameters(check_type, form):
    """Helperfunctie: bouw de parameters-JSON op vanuit het POST-formulier."""
    show_suggestion = bool(form.get('show_suggestion'))
    if check_type in ('keyword_forbidden', 'keyword_required'):
        keywords_raw = form.get('keywords', '').strip()
        kw_list = [k.strip() for k in keywords_raw.split(',') if k.strip()]
        return json.dumps(
            {'keywords': kw_list, 'show_suggestion': show_suggestion},
            ensure_ascii=False
        ) if kw_list else json.dumps({'show_suggestion': show_suggestion})
    elif check_type == 'llm_review':
        return json.dumps({
            'llm_role_prompt':     form.get('llm_role_prompt', '').strip(),
            'llm_criteria_prompt': form.get('llm_criteria_prompt', '').strip(),
            'llm_check_ai_style':  bool(form.get('llm_check_ai_style')),
            'show_suggestion':     show_suggestion,
        }, ensure_ascii=False)
    else:
        return json.dumps({'show_suggestion': show_suggestion})


@admin_required
def add_criterion():
    """Route voor het toevoegen van een nieuw criterium."""
    db = get_db()

    if request.method == 'POST':
        name               = request.form['name']
        description        = request.form.get('description', '')
        organization_id    = request.form.get('organization_id')
        rule_type          = request.form.get('rule_type', 'content_check')
        application_scope  = request.form.get('application_scope', 'document')
        severity           = request.form.get('severity', 'warning')
        is_enabled         = 1 if request.form.get('is_enabled') else 0
        color              = request.form.get('color', '#3B82F6')
        error_message      = request.form.get('error_message', '').strip()
        fixed_feedback_text = request.form.get('fixed_feedback_text', '').strip()
        frequency_unit     = request.form.get('frequency_unit', 'document')
        max_mentions_per   = int(request.form.get('max_mentions_per') or 0)
        expected_value_min_raw = request.form.get('expected_value_min', '').strip()
        expected_value_max_raw = request.form.get('expected_value_max', '').strip()
        expected_value_min = float(expected_value_min_raw) if expected_value_min_raw else None
        expected_value_max = float(expected_value_max_raw) if expected_value_max_raw else None
        check_type = request.form.get('check_type', 'none')
        if check_type == 'llm_review':
            max_mentions_per = 0
        parameters = _build_parameters(check_type, request.form)

        if not name:
            flash('Naam is verplicht!', 'danger')
        else:
            try:
                db.execute(
                    '''INSERT INTO criteria
                       (name, description, rule_type, application_scope, severity, is_enabled,
                        organization_id, color, error_message, fixed_feedback_text,
                        frequency_unit, max_mentions_per, expected_value_min, expected_value_max,
                        check_type, parameters)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (name, description, rule_type, application_scope, severity, is_enabled,
                     organization_id, color, error_message or None, fixed_feedback_text or None,
                     frequency_unit, max_mentions_per, expected_value_min, expected_value_max,
                     check_type, parameters)
                )
                db.commit()
                flash('Criterium succesvol toegevoegd!', 'success')
                return redirect(url_for('list_criteria'))
            except Exception as e:
                flash(f'Fout bij toevoegen: {e}', 'danger')
                traceback.print_exc()

    organizations = db.execute('SELECT id, name FROM organizations').fetchall()
    return render_template('add_criterion.html', organizations=organizations)


@admin_required
def edit_criterion(id):
    """Route voor het bewerken van een criterium."""
    db = get_db()
    criterion = db.execute('SELECT * FROM criteria WHERE id=?', (id,)).fetchone()

    if criterion is None:
        flash('Criterium niet gevonden.', 'danger')
        return redirect(url_for('list_criteria'))

    if request.method == 'POST':
        name               = request.form['name']
        description        = request.form.get('description', '')
        organization_id    = request.form.get('organization_id')
        rule_type          = request.form.get('rule_type', 'mention')
        application_scope  = request.form.get('application_scope', 'document_only')
        severity           = request.form.get('severity', 'warning')
        is_enabled         = 1 if request.form.get('is_enabled') else 0
        color              = request.form.get('color', '#3B82F6')
        error_message      = request.form.get('error_message', '').strip()
        fixed_feedback_text = request.form.get('fixed_feedback_text', '').strip()
        frequency_unit     = request.form.get('frequency_unit', 'document')
        max_mentions_per   = int(request.form.get('max_mentions_per') or 0)
        expected_value_min_raw = request.form.get('expected_value_min', '').strip()
        expected_value_max_raw = request.form.get('expected_value_max', '').strip()
        expected_value_min = float(expected_value_min_raw) if expected_value_min_raw else None
        expected_value_max = float(expected_value_max_raw) if expected_value_max_raw else None
        check_type = request.form.get('check_type', 'none')
        if check_type == 'llm_review':
            max_mentions_per = 0
        parameters = _build_parameters(check_type, request.form)

        if not name:
            flash('Naam is verplicht!', 'danger')
        else:
            try:
                db.execute(
                    '''UPDATE criteria
                       SET name=?, description=?, organization_id=?,
                           rule_type=?, application_scope=?, severity=?, is_enabled=?,
                           color=?, error_message=?, fixed_feedback_text=?,
                           frequency_unit=?, max_mentions_per=?,
                           expected_value_min=?, expected_value_max=?,
                           check_type=?, parameters=?
                       WHERE id=?''',
                    (name, description, organization_id, rule_type,
                     application_scope, severity, is_enabled, color,
                     error_message or None, fixed_feedback_text or None,
                     frequency_unit, max_mentions_per,
                     expected_value_min, expected_value_max,
                     check_type, parameters, id)
                )
                db.commit()
                flash('Criterium succesvol bijgewerkt!', 'success')
                return redirect(url_for('list_criteria'))
            except Exception as e:
                flash(f'Fout bij bijwerken: {e}', 'danger')
                traceback.print_exc()

    organizations = db.execute('SELECT id, name FROM organizations').fetchall()

    criterion_keywords  = ''
    llm_role_prompt     = ''
    llm_criteria_prompt = ''
    llm_check_ai_style  = False
    show_suggestion     = True
    try:
        params = json.loads(dict(criterion).get('parameters') or '{}')
        criterion_keywords  = ', '.join(params.get('keywords', []))
        llm_role_prompt     = params.get('llm_role_prompt', '')
        llm_criteria_prompt = params.get('llm_criteria_prompt', '')
        llm_check_ai_style  = bool(params.get('llm_check_ai_style', False))
        show_suggestion     = params.get('show_suggestion', True)
    except (json.JSONDecodeError, TypeError, KeyError):
        pass

    return render_template('edit_criterion.html',
                           criterion=criterion,
                           organizations=organizations,
                           criterion_keywords=criterion_keywords,
                           llm_role_prompt=llm_role_prompt,
                           llm_criteria_prompt=llm_criteria_prompt,
                           llm_check_ai_style=llm_check_ai_style,
                           show_suggestion=show_suggestion,
                           current_doc_type_id=None)


@admin_required
def delete_criterion(id):
    """Route voor het verwijderen van een criterium."""
    db = get_db()
    criterion = db.execute('SELECT * FROM criteria WHERE id=?', (id,)).fetchone()

    if criterion is None:
        flash('Criterium niet gevonden.', 'danger')
    else:
        try:
            db.execute('DELETE FROM criteria WHERE id=?', (id,))
            db.commit()
            flash('Criterium succesvol verwijderd!', 'success')
        except Exception as e:
            flash(f'Fout bij verwijderen: {e}', 'danger')
            traceback.print_exc()

    return redirect(url_for('list_criteria'))


@admin_required
def map_criteria_to_sections(id):
    """Route voor het mappen van criteria naar secties."""
    db = get_db()
    criterion = db.execute('SELECT * FROM criteria WHERE id=?', (id,)).fetchone()

    if criterion is None:
        flash('Criterium niet gevonden.', 'danger')
        return redirect(url_for('list_criteria'))

    if request.method == 'POST':
        selected_sections = request.form.getlist('selected_sections')
        excluded_sections = request.form.getlist('excluded_sections')
        new_scope         = request.form.get('application_scope')

        try:
            if new_scope:
                db.execute(
                    'UPDATE criteria SET application_scope=? WHERE id=?', (new_scope, id)
                )
            db.execute('DELETE FROM criteria_section_mappings WHERE criteria_id=?', (id,))
            for section_id in selected_sections:
                db.execute(
                    'INSERT INTO criteria_section_mappings (criteria_id, section_id, is_excluded) VALUES (?,?,0)',
                    (id, section_id)
                )
            for section_id in excluded_sections:
                if section_id not in selected_sections:
                    db.execute(
                        'INSERT INTO criteria_section_mappings (criteria_id, section_id, is_excluded) VALUES (?,?,1)',
                        (id, section_id)
                    )
            db.commit()
            flash('Sectie mappings en toepassingsgebied succesvol bijgewerkt!', 'success')
            return redirect(url_for('list_criteria'))
        except Exception as e:
            flash(f'Fout bij mappen: {e}', 'danger')
            traceback.print_exc()

    all_sections = db.execute('''
        SELECT s.*, p.name AS parent_name
        FROM sections s
        LEFT JOIN sections p ON s.parent_id = p.id
        ORDER BY s.order_index, s.level, s.name
    ''').fetchall()

    current_mappings = db.execute(
        'SELECT section_id, is_excluded FROM criteria_section_mappings WHERE criteria_id=?',
        (id,)
    ).fetchall()

    mapped_sections = {m['section_id']: {'is_excluded': bool(m['is_excluded'])}
                       for m in current_mappings}

    return render_template('criteria_section_mapping.html',
                           criterion=criterion,
                           all_sections=all_sections,
                           mapped_sections=mapped_sections)


@admin_required
def list_criteria_templates():
    """Overzichtspagina van criteria templates."""
    db = get_db()
    templates = db.execute('SELECT * FROM criteria_templates ORDER BY name').fetchall()
    return render_template('criteria_templates_list.html', templates=templates)


@admin_required
def add_criteria_template():
    """Route voor het toevoegen van een criteria template."""
    db = get_db()

    if request.method == 'POST':
        name        = request.form['name']
        description = request.form.get('description', '')

        if not name:
            flash('Naam is verplicht!', 'danger')
        else:
            try:
                cursor = db.cursor()
                cursor.execute(
                    'INSERT INTO criteria_templates (name, description) VALUES (?,?)',
                    (name, description)
                )
                template_id = cursor.lastrowid
                for criterion_id in request.form.getlist('criteria_ids'):
                    db.execute(
                        'INSERT INTO criteria_template_items (template_id, criterion_id) VALUES (?,?)',
                        (template_id, criterion_id)
                    )
                db.commit()
                flash('Criteria template succesvol toegevoegd!', 'success')
                return redirect(url_for('list_criteria_templates'))
            except Exception as e:
                flash(f'Fout bij toevoegen: {e}', 'danger')
                traceback.print_exc()

    criteria = db.execute('SELECT * FROM criteria ORDER BY name').fetchall()
    return render_template('add_criteria_template.html', criteria=criteria)


@admin_required
def list_document_type_criteria(doc_type_id):
    """Toon criteria voor een specifiek document type."""
    db = get_db()
    document_type = db.execute('SELECT * FROM document_types WHERE id=?', (doc_type_id,)).fetchone()
    if document_type is None:
        flash('Document type niet gevonden.', 'danger')
        return redirect(url_for('list_document_types'))

    criteria_instances = db.execute('''
        SELECT ci.*, c.name, c.description
        FROM criteria_instances ci
        JOIN criteria c ON ci.criterion_id = c.id
        WHERE ci.document_type_id = ?
        ORDER BY ci.order_index
    ''', (doc_type_id,)).fetchall()

    return render_template('document_type_criteria.html',
                           document_type=document_type,
                           criteria_instances=criteria_instances)


@admin_required
def add_criteria_to_document_type(doc_type_id):
    """Voeg criteria toe aan document type."""
    db = get_db()
    document_type = db.execute('SELECT * FROM document_types WHERE id=?', (doc_type_id,)).fetchone()
    if document_type is None:
        flash('Document type niet gevonden.', 'danger')
        return redirect(url_for('list_document_types'))

    if request.method == 'POST':
        criterion_id = request.form.get('criterion_id')
        weight       = request.form.get('weight', 1.0)
        order_index  = request.form.get('order_index', 0)

        if not criterion_id:
            flash('Criterium is verplicht!', 'danger')
        else:
            try:
                db.execute(
                    'INSERT INTO criteria_instances (criterion_id, document_type_id, weight, order_index) VALUES (?,?,?,?)',
                    (criterion_id, doc_type_id, weight, order_index)
                )
                db.commit()
                flash('Criterium succesvol toegevoegd aan document type!', 'success')
                return redirect(url_for('list_document_type_criteria', doc_type_id=doc_type_id))
            except Exception as e:
                flash(f'Fout bij toevoegen: {e}', 'danger')
                traceback.print_exc()

    criteria = db.execute('SELECT * FROM criteria ORDER BY name').fetchall()
    return render_template('add_criteria_to_document_type.html',
                           document_type=document_type,
                           criteria=criteria)


@admin_required
def edit_criteria_instance(instance_id):
    """Bewerk criteria instance."""
    db = get_db()
    instance = db.execute('''
        SELECT ci.*, c.name, c.description, dt.name as document_type_name
        FROM criteria_instances ci
        JOIN criteria c ON ci.criterion_id = c.id
        JOIN document_types dt ON ci.document_type_id = dt.id
        WHERE ci.id = ?
    ''', (instance_id,)).fetchone()

    if instance is None:
        flash('Criteria instance niet gevonden.', 'danger')
        return redirect(url_for('list_document_types'))

    if request.method == 'POST':
        weight      = request.form.get('weight', 1.0)
        order_index = request.form.get('order_index', 0)
        try:
            db.execute(
                'UPDATE criteria_instances SET weight=?, order_index=? WHERE id=?',
                (weight, order_index, instance_id)
            )
            db.commit()
            flash('Criteria instance succesvol bijgewerkt!', 'success')
            return redirect(url_for('list_document_type_criteria',
                                    doc_type_id=instance['document_type_id']))
        except Exception as e:
            flash(f'Fout bij bijwerken: {e}', 'danger')
            traceback.print_exc()

    return render_template('edit_criteria_instance.html', instance=instance)


@admin_required
def delete_criteria_instance(instance_id):
    """Verwijder criteria instance."""
    db = get_db()
    instance = db.execute('SELECT * FROM criteria_instances WHERE id=?', (instance_id,)).fetchone()

    if instance is None:
        flash('Criteria instance niet gevonden.', 'danger')
    else:
        try:
            document_type_id = instance['document_type_id']
            db.execute('DELETE FROM criteria_instances WHERE id=?', (instance_id,))
            db.commit()
            flash('Criteria instance succesvol verwijderd!', 'success')
            return redirect(url_for('list_document_type_criteria', doc_type_id=document_type_id))
        except Exception as e:
            flash(f'Fout bij verwijderen: {e}', 'danger')
            traceback.print_exc()

    return redirect(url_for('list_document_types'))
