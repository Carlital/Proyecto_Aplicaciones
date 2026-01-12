# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
from odoo.exceptions import AccessError
from odoo.http import Response
import json as pyjson
import json
import logging
import traceback
import time

# ==============================
# RATE LIMITING
# ==============================

REQUEST_LOG = {}     # {ip: [timestamps]}
BLOCKED_IPS = {}     # {ip: unblock_timestamp}

MAX_REQUESTS = 10    # solicitudes permitidas
WINDOW_TIME = 60     # segundos
BLOCK_TIME = 300     # 5 minutos de bloqueo


_logger = logging.getLogger(__name__)


def json_response(payload, status=200):
    return request.make_response(
        json.dumps(payload),
        headers=[('Content-Type', 'application/json')],
        status=status
    )

class CVCallbackController(http.Controller):

    @http.route('/cv/callback', type='http', auth='none', methods=['POST'], csrf=False)
    def cv_callback(self, **kw):
        """Endpoint para recibir resultados procesados desde N8N"""
        try:
            ICP = request.env['ir.config_parameter'].sudo()
            expected_token = ICP.get_param('cv_importer.callback_token') or ''
            auth_header = request.httprequest.headers.get('Authorization') or ''
            token_header = request.httprequest.headers.get('X-Callback-Token') or ''

            # Primero identificamos la IP para poder loguearla en cualquier validación
            xff = request.httprequest.headers.get('X-Forwarded-For') or ''
            if xff:
                remote_ip = xff.split(',')[0].strip()
            else:
                remote_ip = request.httprequest.remote_addr or 'unknown'

            received_token = ''
            if auth_header.startswith('Bearer '):
                received_token = auth_header[7:].strip()
            elif token_header:
                received_token = token_header.strip()

            if expected_token and (not received_token or received_token != expected_token):
                _logger.warning(
                    "Callback CV rechazado por token inválido o ausente "
                    f"(IP={remote_ip})"
                )
                return json_response({'status': 'error', 'message': 'Unauthorized'}, status=401)


            allowed_ips_raw = ICP.get_param('cv_importer.callback_allowed_ips') or ''
            allowed_ips = [ip.strip() for ip in allowed_ips_raw.split(',') if ip.strip()]

            _logger.info(f"Callback recibido de N8N desde IP={remote_ip}")

            if allowed_ips and remote_ip not in allowed_ips:
                _logger.warning(
                    "Callback CV rechazado por IP no autorizada "
                    f"(IP={remote_ip}, allowed={allowed_ips})"
                )
                return json_response({'status': 'error', 'message': 'Forbidden'}, status=403)



            now = time.time()

            # Verificar si la IP está bloqueada
            if remote_ip in BLOCKED_IPS:
                if now < BLOCKED_IPS[remote_ip]:
                    _logger.warning(
                        "IP bloqueada temporalmente por abuso "
                        f"(IP={remote_ip})"
                    )
                    return json_response({"status": "error", "message": "IP temporarily blocked due to abuse"}, status=403)


                else:
                    del BLOCKED_IPS[remote_ip]

            # Rate Limiting
            requests = REQUEST_LOG.get(remote_ip, [])
            requests = [t for t in requests if now - t < WINDOW_TIME]

            if len(requests) >= MAX_REQUESTS:
                # Bloquear IP automáticamente
                BLOCKED_IPS[remote_ip] = now + BLOCK_TIME

                _logger.warning(
                    "Rate limit excedido, IP bloqueada automáticamente "
                    f"(IP={remote_ip})"
                )

                return json_response({"status": "error", "message": "IP temporarily blocked due to abuse"}, status=429)



            requests.append(now)
            REQUEST_LOG[remote_ip] = requests


            raw = request.httprequest.data or b'{}'
            try:
                data = pyjson.loads(raw.decode('utf-8'))
            except Exception:
                data = {}


            _logger.info("Callback recibido de N8N (payload básico cargado)")

            if not data:
                _logger.error("No se recibieron datos en el callback")
                return json_response({'status': 'error', 'message': 'No data received'}, status=400)


            # Estado/headers
            status_raw = (str((data or {}).get('status') or '') or
                          str(request.httprequest.headers.get('X-Job-Status') or '')).strip().lower()

            batch_token_hdr = (request.httprequest.headers.get('X-Job-Batch') or '').strip()
            try:
                batch_order_hdr = int(request.httprequest.headers.get('X-Job-Order', '0'))
            except Exception:
                batch_order_hdr = 0

            n8n_job_id = (str(data.get('job_id') or '') or
                          str(request.httprequest.headers.get('X-Job-Id') or '')).strip()

            # Si viene {result: true/false} sin 'status'
            result_bool = data.get('result')
            if isinstance(result_bool, bool) and not status_raw:
                status_raw = 'success' if result_bool else 'failed'

            # Conjuntos de mapeo
            success_statuses = {'ok', 'done', 'success', 'processed'}
            error_statuses   = {'fail', 'failed', 'error'}

            # 1) Inicializar siempre
            mapped_state = 'processing'
            # 2) Ajustar por status_raw
            if status_raw in success_statuses:
                mapped_state = 'processed'
            elif status_raw in error_statuses:
                mapped_state = 'error'

            # Extraer información básica
            cedula = data.get('cedula')
            employee_name = data.get('employee_name')

            if not cedula:
                _logger.error("Falta cédula en el callback")
                return json_response({'status': 'error', 'message': 'Missing cedula'}, status=400)

            _logger.info(f"Procesando callback para: {employee_name} (Cédula: {cedula})")

            cv_document = request.env['cv.document'].sudo().search(
                [('cedula', '=', cedula)],
                order='create_date desc', limit=1
            )
            if not cv_document:
                _logger.error(f"No se encontró documento CV para cédula: {cedula}")
                return json_response({'status': 'error', 'message': f'No se encontró documento CV para cédula: {cedula}'}, status=404)


            previous_state = cv_document.state or 'draft'


            import_user = cv_document.write_uid or cv_document.create_uid

            # Idempotencia: ya estaba processed y llega processed de nuevo
            if previous_state == 'processed' and mapped_state == 'processed':
                _logger.info(f"Callback duplicado ignorado (ya fue procesado). Doc {cv_document.id}")
                return request.make_response(
                    json.dumps({
                        'status': 'success',
                        'message': 'Callback duplicado proceso ignorado',
                        'cedula': cedula,
                        'employee_name': employee_name,
                        'odoo_state': previous_state,
                        'next_dispatched': False,
                        'duplicate': True,
                    }),
                    headers=[('Content-Type', 'application/json')],
                    status=200
                )

            write_vals = {
                'state': mapped_state,
                'n8n_status': status_raw or mapped_state,
                'n8n_last_callback': fields.Datetime.now(),
                'batch_token': cv_document.batch_token or (data.get('batch_token') or batch_token_hdr or False),
                'batch_order': cv_document.batch_order or int(data.get('batch_order') or batch_order_hdr or 0),
            }
            if n8n_job_id:
                write_vals['n8n_job_id'] = n8n_job_id

            full_response_json = json.dumps(data, ensure_ascii=False, indent=2)
            write_vals['extraction_response'] = full_response_json
            
            cv_document.write(write_vals)
            request.env.cr.commit()

            try:
                raw_data = data.get("raw_extracted_data") or {}

                typo_model = request.env["cv.typo.catalog"].sudo()

                # Extraer candidatos a typo desde campos manuales
                candidates = typo_model.extract_candidates(raw_data)

                for word in candidates:
                    typo_model.upsert_typo(
                        typo=word,
                        cedula=cedula,
                        sample=word
                    )

                _logger.info(
                    "Typos staging actualizado | cedula=%s | candidatos=%s",
                    cedula, len(candidates)
                )

            except Exception as e:
                _logger.warning(
                    "No se pudo actualizar catálogo de typos (staging): %s", str(e)
                )

            normalized_applied = False
            normalized_error = None

            if mapped_state == 'processed' and cv_document.extraction_response:
                try:
                    cv_document._invalidate_cache(['extraction_response'])
                    cv_document.action_apply_parsed_data()
                    normalized_applied = True
                except Exception as e:
                    normalized_error = str(e)
                    # Si falló al aplicar datos normalizados, marcar el documento como error.
                    mapped_state = 'error'
                    cv_document.write({
                        'state': mapped_state,
                        'status_message': normalized_error,
                    })

            # Métricas de tiempo y tamaño (cv.metrics)
            try:
                import time as _time
                metrics = request.env['cv.metrics'].sudo()

                start_ts = getattr(cv_document, 'start_time_espoch', 0.0) or 0.0
                if not start_ts and data.get('start_time_espoch'):
                    try:
                        start_ts = float(data.get('start_time_espoch'))
                    except Exception:
                        start_ts = 0.0
                if not start_ts:
                    start_ts = _time.time()

                duration_seconds = max(_time.time() - start_ts, 0.0)
                success_flag = (mapped_state == 'processed')

                employee_id = cv_document.employee_id.id if cv_document.employee_id else None
                user_id = cv_document.create_uid.id

                # PERFILADO (pre/post) desde N8N
                profiling_pre = data.get('profiling_pre') or {}
                profiling_post = data.get('profiling_post') or {}

                # Valores útiles (si quieres guardarlos como campos directos)
                pdf_pages = None
                pdf_text_length = None
                completeness_ratio = None

                if isinstance(profiling_pre, dict):
                    pdf_pages = profiling_pre.get('pdf_pages')
                    pdf_text_length = profiling_pre.get('pdf_text_length')
                    completeness_ratio = profiling_pre.get('completeness_ratio')

                try:
                    completeness_ratio = round(float(completeness_ratio), 2) if completeness_ratio is not None else None
                except Exception:
                    completeness_ratio = None

                created = None
                if hasattr(metrics, 'record_import_metric'):
                    created = metrics.record_import_metric(
                        duration_seconds=duration_seconds,
                        success=success_flag,
                        error_msg=None,
                        employee_id=employee_id,
                        user_id=user_id,
                        operation_type='import',
                    
                        profiling_pre=profiling_pre,
                        profiling_post=profiling_post,
                        pdf_pages=pdf_pages,
                        pdf_text_length=pdf_text_length,
                        completeness_ratio=completeness_ratio,
                    )

                if created:
                    _logger.info(f"cv.metrics creado id={created.id} para cedula={cedula}")
                else:
                    _logger.warning(f"cv.metrics no se pudo crear para cedula={cedula}")

            except Exception:
                _logger.exception("No se pudo grabar métrica de importación desde callback (detallado)")

            fields_updated = 0
            fields_applied = 0  

            next_dispatched = False
            try:
                if (mapped_state == 'processed'
                        and previous_state != 'processed'
                        and cv_document.batch_token):
                    request.env.cr.commit()
                    cv_document._dispatch_next_in_batch()
                    next_dispatched = True
            except Exception as e:
                _logger.warning(f"No se pudo despachar el siguiente del lote: {e}")

            processing_method = data.get('processing_method', 'unknown')

            # 🔔 Notificación al usuario en el frontend
            try:
                user = import_user.sudo()
                if user and user.exists() and user.partner_id:

                    # Mensaje base según estado
                    if mapped_state == 'processed':
                        base_msg = "El CV de %s ha sido procesado correctamente." % (
                            employee_name or (cv_document.employee_id.name or '')
                        )
                    elif mapped_state == 'error':
                        base_msg = "Se produjo un error al procesar el CV de %s." % (
                            employee_name or (cv_document.employee_id.name or '')
                        )
                    else:
                        base_msg = "El CV de %s cambió de estado a: %s" % (
                            employee_name or (cv_document.employee_id.name or ''),
                            mapped_state,
                        )

                    mode = 'single'
                    if cv_document.batch_token:
                        others_count = request.env['cv.document'].sudo().search_count([
                            ('batch_token', '=', cv_document.batch_token),
                            ('id', '!=', cv_document.id),
                        ])
                        if others_count > 0:
                            mode = 'batch'

                    is_last = True
                    if mode == 'batch':
                        is_last = not next_dispatched

                    payload = {
                        'type': 'cv_importer_done',
                        'title': 'Importación de CV',
                        'message': base_msg if mode == 'single' else
                            ("Lote completado: %s" % (cv_document.batch_token,)
                             if is_last else base_msg),
                        'state': mapped_state,
                        'cv_document_id': cv_document.id,
                        'mode': mode,                     # 'single' o 'batch'
                        'batch_token': cv_document.batch_token,
                        'is_last': is_last,               # True si es el último del lote
                        'next_dispatched': next_dispatched,
                    }

                    request.env['bus.bus']._sendone(
                        user.partner_id,
                        'cv_importer_done',
                        payload
                    )
                    request.env.cr.commit()
                    _logger.info(
                        "🛎 Notificación cv_importer_done enviada a user=%s partner=%s "
                        "(mode=%s is_last=%s)",
                        user.id, user.partner_id.id, mode, is_last
                    )
            except Exception as e:
                _logger.warning(f"No se pudo enviar notificación por bus.bus: {e}")

            _logger.info(
                f"🎉 Callback procesado para {employee_name} | "
                f"estado={mapped_state} (antes={previous_state}) | "
                f"batch={cv_document.batch_token or '-'} | next={next_dispatched}"
            )


            return request.make_response(
                json.dumps({
                    'status': 'success',
                    'message': 'CV processed successfully',
                    'cedula': cedula,
                    'employee_name': employee_name,
                    'fields_updated': fields_updated,
                    'fields_applied_to_employee': fields_applied,
                    'processing_method': processing_method,
                    'auto_apply_enabled': False,
                    'extracted_fields': [],
                    'odoo_state': mapped_state,
                    'next_dispatched': next_dispatched,
                    'job_id': n8n_job_id,
                    'normalized_applied': normalized_applied,
                    'normalized_error': normalized_error,
                }),
                headers=[('Content-Type', 'application/json')],
                status=200
            )


        except Exception as e:
            _logger.error(f"Error en callback CV: {str(e)}")
            _logger.error(traceback.format_exc())
            return json_response({'status': 'error', 'message': f'Error interno: {str(e)}'}, status=500)


    @http.route('/cv/callback/test', type='json', auth='none', methods=['GET', 'POST'], csrf=False)
    def cv_callback_test(self, **kw):
        _logger.info("Endpoint de prueba de callback CV accedido")
        return {
            'status': 'success',
            'message': 'Endpoint de callback CV funcionando',
            'timestamp': str(request.env['ir.http']._get_default_session_info().get('now')),
            'test': True
        }

    @http.route('/cv/callback/debug', type='json', auth='none', methods=['POST'], csrf=False)
    def cv_callback_debug(self, **kw):
        try:
            data = request.get_json_data()
            if not data:
                data = kw
            _logger.info("Datos recibidos:")
            _logger.info(f"Estructura completa: {json.dumps(data, indent=2, ensure_ascii=False)}")
            return {
                'status': 'debug_success',
                'message': 'Debug callback recibido',
                'received_keys': list(data.keys()) if data else [],
                'extracted_data_keys': list(data.get('extracted_data', {}).keys()) if data.get('extracted_data') else [],
                'additional_fields_keys': list(data.get('additional_fields', {}).keys()) if data.get('additional_fields') else [],
                'data_sample': {
                    'cedula': data.get('cedula'),
                    'employee_name': data.get('employee_name'),
                    'has_extracted_data': bool(data.get('extracted_data')),
                    'has_additional_fields': bool(data.get('additional_fields'))
                }
            }
        except Exception as e:
            _logger.error(f"Error en debug callback: {str(e)}")
            return {'status': 'debug_error', 'error': str(e)}
