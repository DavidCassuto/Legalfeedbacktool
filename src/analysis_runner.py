# src/analysis_runner.py
"""Achtergrond-analyserunner: threading state + run_analysis_background()."""

import sqlite3
import threading
import json
import traceback
from datetime import datetime

import db_utils
from analysis import document_parsing, section_recognition, criterion_checking
from database_optimizations import batch_save_section_content

# Bijhouder van lopende analyses (gedeeld met routes)
_analysis_in_progress: set = set()
_analysis_lock = threading.Lock()


def run_analysis_background(document_id: int, flask_app, database: str) -> None:
    """Voert de volledige analyse uit in een achtergrond-thread met eigen DB-verbinding."""
    with flask_app.app_context():
        db = sqlite3.connect(database)
        db.row_factory = sqlite3.Row
        try:
            document = db.execute(
                'SELECT * FROM documents WHERE id=?', (document_id,)
            ).fetchone()
            document_type = db.execute(
                'SELECT * FROM document_types WHERE id=?',
                (document['document_type_id'],)
            ).fetchone()

            print(f"[ACHTERGROND] Start analyse voor document ID: {document_id}")

            # 1. Document parsen
            full_document_text, document_paragraphs, headings_in_document = \
                document_parsing.parse_document(document['file_path'])

            print(
                f"[ACHTERGROND] Paragrafen: {len(document_paragraphs)}, "
                f"headings: {len(headings_in_document)}"
            )

            # 2. Sectieherkenning
            expected_sections_metadata = db.execute(
                '''SELECT DISTINCT s.id, s.name, s.level, s.identifier, s.is_required,
                          s.parent_id, s.alternative_names, s.order_index
                   FROM sections s
                   LEFT JOIN document_type_sections dts ON s.id = dts.section_id
                   WHERE s.document_type_id = :dt_id
                      OR dts.document_type_id = :dt_id
                      OR (s.document_type_id IS NULL
                          AND NOT EXISTS (
                              SELECT 1 FROM document_type_sections dts2
                              WHERE dts2.section_id = s.id
                          ))
                   ORDER BY
                       CASE WHEN s.document_type_id IS NULL THEN 0 ELSE 1 END,
                       s.order_index''',
                {'dt_id': document_type['id']}
            ).fetchall()

            recognized_sects_raw, formatting_warnings = \
                section_recognition.recognize_and_enrich_sections(
                    full_document_text, document_paragraphs,
                    headings_in_document, expected_sections_metadata
                )

            # Voetnoten-blok extraheren uit full_document_text en toevoegen
            # aan de content van elke sectie — zodat de LLM altijd bronnen ziet.
            _voetnoten_blok = ''
            if '[VOETNOTEN/EINDNOTEN]' in full_document_text:
                _start = full_document_text.index('[VOETNOTEN/EINDNOTEN]')
                _voetnoten_blok = full_document_text[_start:].strip()

            if _voetnoten_blok:
                for sec in recognized_sects_raw:
                    if sec.get('found') and sec.get('content'):
                        sec['content'] = sec['content'].rstrip() + \
                            '\n\n' + _voetnoten_blok

            batch_save_section_content(db, recognized_sects_raw)

            all_db_sections = db.execute(
                '''SELECT DISTINCT s.id, s.name, s.level, s.identifier, s.order_index
                   FROM sections s
                   LEFT JOIN document_type_sections dts ON s.id = dts.section_id
                   WHERE s.document_type_id = :dt_id
                      OR dts.document_type_id = :dt_id
                      OR (s.document_type_id IS NULL
                          AND NOT EXISTS (
                              SELECT 1 FROM document_type_sections dts2
                              WHERE dts2.section_id = s.id
                          ))
                   ORDER BY
                       CASE WHEN s.document_type_id IS NULL THEN 0 ELSE 1 END,
                       s.order_index''',
                {'dt_id': document_type['id']}
            ).fetchall()

            display_sections = []
            for db_sec_info in all_db_sections:
                recognized_sec = next(
                    (s for s in recognized_sects_raw if s.get('db_id') == db_sec_info['id']),
                    None
                )
                display_sections.append({
                    'id':           db_sec_info['id'],
                    'name':         db_sec_info['name'],
                    'level':        db_sec_info['level'],
                    'found':        recognized_sec.get('found', False) if recognized_sec else False,
                    'word_count':   recognized_sec.get('word_count', 0) if recognized_sec else 0,
                    'confidence':   recognized_sec.get('confidence', None) if recognized_sec else None,
                    'content':      recognized_sec.get('content', '') if recognized_sec else '',
                    'identifier':   db_sec_info['identifier'],
                    'heading_text': recognized_sec.get('heading_text', '') if recognized_sec else '',
                    # Documentpositie voor sortering — gevonden secties krijgen hun start_char,
                    # niet-gevonden secties komen achteraan op basis van DB order_index.
                    '_doc_pos':     recognized_sec.get('start_char', float('inf')) if recognized_sec and recognized_sec.get('found') else float('inf'),
                    '_order_index': db_sec_info['order_index'] if db_sec_info['order_index'] is not None else 9999,
                })

            # Sorteer: gevonden secties op documentvolgorde, niet-gevonden op DB order_index
            display_sections.sort(key=lambda s: (
                0 if s['_doc_pos'] != float('inf') else 1,  # gevonden eerst
                s['_doc_pos'],                               # dan op positie in document
                s['_order_index'],                           # niet-gevonden: DB volgorde
            ))

            # 3. Feedback genereren (LLM-calls lopen parallel in generate_feedback)
            criteria_for_analysis = db_utils.get_criteria_for_document_type(
                db, document_type['id']
            )
            generated_feedback_items = criterion_checking.generate_feedback(
                full_document_text, recognized_sects_raw,
                criteria_for_analysis, db, document_id, document_type['id']
            )

            # Opmaakwaarschuwingen toevoegen
            for fw in formatting_warnings:
                if fw['type'] == 'misformatted_heading':
                    generated_feedback_items.append({
                        'criteria_id':       None,
                        'criteria_name':     'Documentopmaak',
                        'section_id':        None,
                        'section_name':      'Document',
                        'status':            'warning',
                        'message':           (
                            'Een alinea heeft per ongeluk een koptekststijl '
                            'gekregen in Word. De alinea is niet als '
                            'sectieheading herkend.'
                        ),
                        'suggestion':        (
                            f'Controleer de opmaak van deze alinea en zet '
                            f'de stijl terug naar "Standaard" of "Normal": '
                            f'"{fw["text_preview"]}..."'
                        ),
                        'location':          'Documentopmaak',
                        'offending_snippet': fw['text_preview'],
                        'confidence':        1.0,
                        'color':             '#F9C74F',
                        'check_type':        'formatting',
                    })

            # 4. Hoofdresultaten direct opslaan — VOOR holistische reviews.
            # Zo is de analyse altijd beschikbaar, ook als holistische reviews crashen
            # of worden onderbroken door een Flask-herstart.
            import logging as _log
            _logger = _log.getLogger('docucheck')
            _timestamp = datetime.now().isoformat()
            analysis_summary = {
                'sections': [
                    {
                        'id':         s['id'],
                        'name':       s['name'],
                        'level':      s['level'],
                        'found':      s['found'],
                        'word_count': s['word_count'],
                        'confidence': s['confidence'],
                        'content':    s['content'],
                    } for s in display_sections
                ],
                'feedback':           generated_feedback_items,
                'analysis_timestamp': _timestamp,
            }
            db.execute(
                'UPDATE documents SET analysis_status=?, analysis_data=? WHERE id=?',
                ('completed', json.dumps(analysis_summary), document_id)
            )
            db.commit()
            _logger.info(f"Analyse voltooid (hoofdresultaten) voor document ID: {document_id}")

            # 5. Holistische reviews — optionele tweede pass.
            # Fouten hier breken de analyse NIET; status blijft 'completed'.
            try:
                _show_sugg = bool(document_type['show_suggestions']) \
                    if 'show_suggestions' in document_type.keys() else True
                holistic_items = criterion_checking.run_holistic_section_reviews(
                    recognized_sects_raw,
                    full_document_text,
                    llm_model='claude-haiku-4-5',
                    show_suggestions=_show_sugg,
                )
                if holistic_items:
                    generated_feedback_items.extend(holistic_items)
                    analysis_summary['feedback'] = generated_feedback_items
                    db.execute(
                        'UPDATE documents SET analysis_data=? WHERE id=?',
                        (json.dumps(analysis_summary), document_id)
                    )
                    db.commit()
                    _logger.info(
                        f"Holistische reviews toegevoegd voor document ID: {document_id} "
                        f"({len(holistic_items)} items)"
                    )
            except Exception as hol_exc:
                _logger.warning(
                    f"Holistische reviews mislukt voor document {document_id} "
                    f"(hoofdresultaten zijn al opgeslagen): {hol_exc}"
                )

        except Exception as exc:
            print(f"[ACHTERGROND] Fout tijdens analyse van document {document_id}: {exc}")
            traceback.print_exc()
            try:
                db.execute(
                    'UPDATE documents SET analysis_status=? WHERE id=?',
                    ('failed', document_id)
                )
                db.commit()
            except Exception:
                pass
        finally:
            db.close()
            with _analysis_lock:
                _analysis_in_progress.discard(document_id)


def run_partial_reanalysis_background(
    document_id: int,
    section_names: list,
    include_doc_wide: bool,
    flask_app,
    database: str,
) -> None:
    """
    Heranalyseer uitsluitend de opgegeven secties en vervang alleen hun feedback
    in de bestaande analysis_data. Feedback voor niet-geselecteerde secties blijft intact.

    section_names  : lijst van sectienamen die hergeanalyseerd moeten worden
    include_doc_wide: als True, ook document-brede criteria (taalcheck e.d.) opnieuw draaien
    """
    import logging as _log
    _logger = _log.getLogger('docucheck')

    with flask_app.app_context():
        db = sqlite3.connect(database)
        db.row_factory = sqlite3.Row
        try:
            document = db.execute(
                'SELECT * FROM documents WHERE id=?', (document_id,)
            ).fetchone()
            document_type = db.execute(
                'SELECT * FROM document_types WHERE id=?',
                (document['document_type_id'],)
            ).fetchone()

            _logger.info(
                f"[HERANALYSE] Start gedeeltelijke heranalyse document {document_id} | "
                f"secties: {section_names} | doc-breed: {include_doc_wide}"
            )

            # 1. Document opnieuw parsen (nodig voor full_doc_text en sectieherkenning)
            full_doc_text, doc_paragraphs, headings = \
                document_parsing.parse_document(document['file_path'])

            # 2. Sectieherkenning
            expected_sections_metadata = db.execute(
                '''SELECT DISTINCT s.id, s.name, s.level, s.identifier, s.is_required,
                          s.parent_id, s.alternative_names, s.order_index
                   FROM sections s
                   LEFT JOIN document_type_sections dts ON s.id = dts.section_id
                   WHERE s.document_type_id = :dt_id
                      OR dts.document_type_id = :dt_id
                      OR (s.document_type_id IS NULL
                          AND NOT EXISTS (
                              SELECT 1 FROM document_type_sections dts2
                              WHERE dts2.section_id = s.id
                          ))
                   ORDER BY
                       CASE WHEN s.document_type_id IS NULL THEN 0 ELSE 1 END,
                       s.order_index''',
                {'dt_id': document_type['id']}
            ).fetchall()

            recognized_sects_raw, _ = section_recognition.recognize_and_enrich_sections(
                full_doc_text, doc_paragraphs, headings, expected_sections_metadata
            )

            # Voetnoten toevoegen aan sectie-content
            _voetnoten_blok = ''
            if '[VOETNOTEN/EINDNOTEN]' in full_doc_text:
                _start = full_doc_text.index('[VOETNOTEN/EINDNOTEN]')
                _voetnoten_blok = full_doc_text[_start:].strip()
            if _voetnoten_blok:
                for sec in recognized_sects_raw:
                    if sec.get('found') and sec.get('content'):
                        sec['content'] = sec['content'].rstrip() + '\n\n' + _voetnoten_blok

            # 3. Bestaande analysis_data laden
            existing_data = json.loads(document['analysis_data'] or '{}')
            old_feedback  = existing_data.get('feedback', [])

            # Verwijder oude feedback voor de geselecteerde secties
            section_names_set = set(section_names)
            def _should_remove(fi):
                sn = fi.get('section_name') or ''
                if sn in section_names_set:
                    return True
                # Document-brede items hebben section_name='' of 'Hele Document'
                if include_doc_wide and sn in ('', 'Hele Document'):
                    return True
                return False

            kept_feedback = [fi for fi in old_feedback if not _should_remove(fi)]

            # 4. Nieuwe criteria-feedback genereren voor alleen de geselecteerde secties
            criteria_for_analysis = db_utils.get_criteria_for_document_type(
                db, document_type['id']
            )
            new_feedback = criterion_checking.generate_feedback(
                full_doc_text,
                recognized_sects_raw,
                criteria_for_analysis,
                db,
                document_id,
                document_type['id'],
                only_section_names  = section_names_set,
                include_doc_wide    = include_doc_wide,
            )

            # 5. Holistische reviews voor de geselecteerde secties
            _show_sugg = bool(document_type['show_suggestions']) \
                if 'show_suggestions' in document_type.keys() else True
            filtered_for_holistic = [
                s for s in recognized_sects_raw if s.get('name') in section_names_set
            ]
            holistic_items = []
            try:
                holistic_items = criterion_checking.run_holistic_section_reviews(
                    filtered_for_holistic,
                    full_doc_text,
                    llm_model    = 'claude-haiku-4-5',
                    show_suggestions = _show_sugg,
                )
            except Exception as hol_exc:
                _logger.warning(f"[HERANALYSE] Holistische reviews mislukt: {hol_exc}")

            # 6. Alles samenvoegen en opslaan
            all_new_feedback = new_feedback + holistic_items
            combined_feedback = kept_feedback + all_new_feedback

            existing_data['feedback'] = combined_feedback
            existing_data['partial_reanalysis_timestamp'] = datetime.now().isoformat()
            existing_data['partial_reanalysis_sections']  = section_names

            db.execute(
                'UPDATE documents SET analysis_status=?, analysis_data=? WHERE id=?',
                ('completed', json.dumps(existing_data), document_id)
            )
            db.commit()
            _logger.info(
                f"[HERANALYSE] Voltooid voor document {document_id} | "
                f"nieuw: {len(all_new_feedback)} items | behouden: {len(kept_feedback)} items"
            )

        except Exception as exc:
            _logger.error(f"[HERANALYSE] Fout document {document_id}: {exc}")
            traceback.print_exc()
            try:
                db.execute(
                    'UPDATE documents SET analysis_status=? WHERE id=?',
                    ('completed', document_id)   # terug naar completed, niet naar failed
                )
                db.commit()
            except Exception:
                pass
        finally:
            db.close()
            with _analysis_lock:
                _analysis_in_progress.discard(document_id)
