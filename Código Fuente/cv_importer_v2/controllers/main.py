# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
import json
import logging
import traceback
import base64
import requests

_logger = logging.getLogger(__name__)

class CVCallbackController(http.Controller):

    @http.route('/cv/callback', type='json', auth='none', methods=['POST'], csrf=False)
    def cv_callback(self, **kw):
        """Endpoint para recibir resultados procesados desde N8N"""
        try:
            # Obtener datos del JSON enviado por N8N
            data = request.get_json_data()
            if not data:
                data = kw or {}

            # Seguridad opcional por token: si está configurado, exigir encabezado X-CV-Token
            try:
                icp = request.env['ir.config_parameter'].sudo()
                expected = (icp.get_param('cv_importer.callback_token', '') or '').strip()
                if expected:
                    provided = (request.httprequest.headers.get('X-CV-Token') or data.get('token') or '').strip()
                    if not provided or provided != expected:
                        _logger.error("Callback rechazado: token inválido o ausente")
                        return {'status': 'error', 'message': 'unauthorized'}
            except Exception:
                # En caso de error en validación de token, continuar para no romper flujos existentes
                pass

            _logger.info("📥 Callback recibido de N8N")
            _logger.info(f"🔍 Datos recibidos: {list(data.keys()) if data else 'No data'}")

            if not data:
                _logger.error("❌ No se recibieron datos en el callback")
                return {'status': 'error', 'message': 'No data received'}

            # === Estado/headers reportados por N8N ===
            status_raw = (str((data or {}).get('status') or '') or
                          str(request.httprequest.headers.get('X-Job-Status') or '')).strip().lower()

            batch_token_hdr = (request.httprequest.headers.get('X-Job-Batch') or '').strip()
            try:
                batch_order_hdr = int(request.httprequest.headers.get('X-Job-Order', '0'))
            except Exception:
                batch_order_hdr = 0

            n8n_job_id = (str(data.get('job_id') or '') or
                          str(request.httprequest.headers.get('X-Job-Id') or '')).strip()

            # Si viene {result: true/false} sin 'status', inferimos
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
                _logger.error("❌ Falta cédula en el callback")
                return {'status': 'error', 'message': 'Missing cedula'}

            _logger.info(f"👤 Procesando callback para: {employee_name} (Cédula: {cedula})")

            # Buscar el documento CV correspondiente (el más reciente por cédula)
            cv_document = request.env['cv.document'].sudo().search(
                [('cedula', '=', cedula)],
                order='create_date desc', limit=1
            )
            if not cv_document:
                _logger.error(f"❌ No se encontró documento CV para cédula: {cedula}")
                return {'status': 'error', 'message': f'CV document not found for cedula: {cedula}'}

            previous_state = cv_document.state or 'draft'

            # Si N8N no manda status pero sí contenido procesado, inferir éxito
            if not status_raw:
                if (data.get('processed_text') or data.get('markdown_content') or
                    data.get('extracted_data') or data.get('additional_fields')):
                    mapped_state = 'processed'
                else:
                    mapped_state = 'processing'

            # Idempotencia: ya estaba processed y llega processed de nuevo
            if previous_state == 'processed' and mapped_state == 'processed':
                _logger.info(f"♻️ Callback duplicado ignorado (ya estaba processed). Doc {cv_document.id}")
                return {
                    'status': 'success',
                    'message': 'Duplicate processed callback ignored',
                    'cedula': cedula,
                    'employee_name': employee_name,
                    'odoo_state': previous_state,
                    'next_dispatched': False,
                    'duplicate': True,
                }

            # Guardar texto procesado (si viene)
            processed_text = data.get('processed_text') or data.get('markdown_content') or ''

            # === Escribir estado/fechas/status/job/batch ===
            write_vals = {
                'processed_text': processed_text,
                'state': mapped_state,
                'n8n_status': status_raw or mapped_state,
                'n8n_last_callback': fields.Datetime.now(),
                'batch_token': cv_document.batch_token or (data.get('batch_token') or batch_token_hdr or False),
                'batch_order': cv_document.batch_order or int(data.get('batch_order') or batch_order_hdr or 0),
            }
            if n8n_job_id:
                write_vals['n8n_job_id'] = n8n_job_id

            # Descarga segura desde storage_url firmado (patrón A)
            storage_url = (data.get('storage_url') or '').strip()
            filename = (data.get('filename') or f"cv_{cedula}.pdf").strip()
            mimetype = (data.get('mimetype') or 'application/pdf').strip()
            checksum = (data.get('checksum_sha256') or '').strip()
            downloaded = False
            if storage_url and mapped_state in ('processed', 'success', 'ok'):
                try:
                    resp = requests.get(storage_url, timeout=30)
                    if resp.status_code == 200 and resp.content:
                        content = resp.content
                        # Validar checksum si viene
                        if checksum:
                            import hashlib
                            h = hashlib.sha256(content).hexdigest()
                            if h.lower() != checksum.lower():
                                _logger.warning("Checksum SHA256 no coincide para storage_url")
                            else:
                                _logger.info("Checksum SHA256 verificado para storage_url")
                        att_vals = {
                            'name': filename,
                            'datas': base64.b64encode(content),
                            'res_model': 'cv.document',
                            'res_id': cv_document.id,
                            'mimetype': mimetype,
                        }
                        # Crear o actualizar adjunto y enlazar
                        if getattr(cv_document, 'cv_attachment_id', False):
                            cv_document.cv_attachment_id.sudo().write(att_vals)
                            attachment = cv_document.cv_attachment_id
                        else:
                            attachment = request.env['ir.attachment'].sudo().create(att_vals)
                            cv_document.sudo().write({'cv_attachment_id': attachment.id})
                        # Asegurar access_token para descarga vía web/content
                        try:
                            if not attachment.access_token:
                                # En Odoo 17 existe access_token; generar si falta
                                token = request.env['ir.attachment']._generate_access_token() if hasattr(request.env['ir.attachment'], '_generate_access_token') else None
                                if token:
                                    attachment.write({'access_token': token})
                        except Exception:
                            pass
                        downloaded = True
                except Exception as e:
                    _logger.warning(f"No se pudo descargar storage_url: {str(e)}")

            cv_document.write(write_vals)

            # ========= EXTRACCIÓN DE DATOS =========
            extracted_data = {}
            _logger.info(f"🔍 DEBUG - Claves principales en data: {list(data.keys())}")

            extracted_info = data.get('extracted_data', {}) or {}
            additional_info = data.get('additional_fields', {}) or {}

            _logger.info(f"🔍 DEBUG - extracted_data keys: {list(extracted_info.keys()) if extracted_info else 'None'}")
            _logger.info(f"🔍 DEBUG - additional_fields keys: {list(additional_info.keys()) if additional_info else 'None'}")

            # Secciones principales
            if str(extracted_info.get('presentacion') or '').strip():
                extracted_data['extracted_presentacion'] = extracted_info['presentacion']
            if str(extracted_info.get('docencia') or '').strip():
                extracted_data['extracted_docencia'] = extracted_info['docencia']
            if str(extracted_info.get('proyectos') or '').strip():
                extracted_data['extracted_proyectos'] = extracted_info['proyectos']
            if str(extracted_info.get('publicaciones') or '').strip():
                extracted_data['extracted_publicaciones'] = extracted_info['publicaciones']

            # Campos adicionales “flat”
            additional_fields_mapping = {
                'telefono': 'telefono',
                'email_personal': 'email_personal',
                'titulo_principal': 'titulo_principal',
                'anos_experiencia': 'anos_experiencia',
                'orcid': 'orcid',
                'oficina': 'oficina',
                'idiomas': 'idiomas',
                'total_publicaciones': 'total_publicaciones',
                'indice_h': 'indice_h',
                'total_citas': 'total_citas',
                'total_proyectos': 'total_proyectos'
            }
            for odoo_field, n8n_field in additional_fields_mapping.items():
                if n8n_field in additional_info:
                    val = additional_info[n8n_field]
                    if (isinstance(val, str) and val.strip()) or \
                       (isinstance(val, (int, float)) and val != 0) or \
                       (val and not isinstance(val, (str, int, float))):
                        extracted_data[f'extracted_{odoo_field}'] = val

            # Campos “detallados” desde raw_extracted_data
            raw_data = data.get('raw_extracted_data', {}) or {}
            if raw_data.get('educacion'):
                titulos = []
                for edu in raw_data['educacion']:
                    t = (edu or {}).get('titulo') or ''
                    inst = (edu or {}).get('institucion') or ''
                    niv = (edu or {}).get('nivel') or ''
                    if t:
                        titulos.append(f"• {t} - {inst} ({niv})")
                if titulos:
                    extracted_data['extracted_titulos_academicos'] = '\n'.join(titulos)

            if raw_data.get('experiencia'):
                exp_lines = []
                for exp in raw_data['experiencia']:
                    cargo = (exp or {}).get('cargo') or ''
                    fi = (exp or {}).get('fecha_inicio') or ''
                    ff = (exp or {}).get('fecha_fin') or ''
                    if cargo:
                        exp_lines.append(f"• {cargo} ({fi} - {ff})")
                if exp_lines:
                    extracted_data['extracted_experiencia_laboral'] = '\n'.join(exp_lines)

            if raw_data.get('certificaciones'):
                caps = []
                for cert in raw_data['certificaciones']:
                    desc = (cert or {}).get('descripcion') or ''
                    inst = (cert or {}).get('institucion') or ''
                    if desc:
                        caps.append(f"• {desc} - {inst}")
                if caps:
                    extracted_data['extracted_capacitaciones'] = '\n'.join(caps)

            if raw_data.get('materias'):
                mats = []
                for m in raw_data['materias']:
                    carrera = (m or {}).get('carrera') or ''
                    asig = (m or {}).get('asignatura') or ''
                    if asig:
                        mats.append(f"• {asig} - {carrera}")
                if mats:
                    extracted_data['extracted_docencia_detalle'] = '\n'.join(mats)

            if raw_data.get('logros'):
                logs = []
                for lg in raw_data['logros']:
                    desc = (lg or {}).get('descripcion') or ''
                    tipo = (lg or {}).get('tipo') or ''
                    if desc:
                        logs.append(f"• {desc} ({tipo})")
                if logs:
                    extracted_data['extracted_distinciones'] = '\n'.join(logs)

            # Fallback (retrocompatibilidad)
            if not extracted_info and not additional_info:
                if data.get('presentacion'): extracted_data['extracted_presentacion'] = data['presentacion']
                if data.get('docencia'): extracted_data['extracted_docencia'] = data['docencia']
                if data.get('proyectos'): extracted_data['extracted_proyectos'] = data['proyectos']
                if data.get('publicaciones'): extracted_data['extracted_publicaciones'] = data['publicaciones']
                for odoo_field, n8n_field in additional_fields_mapping.items():
                    if data.get(n8n_field):
                        extracted_data[f'extracted_{odoo_field}'] = data[n8n_field]

            # Guardar extraídos
            if extracted_data:
                cv_document.write(extracted_data)
                _logger.info(f"✅ Datos extraídos guardados: {len(extracted_data)} campos")

            # Auto-aplicar al empleado (opcional)
            auto_apply = request.env['ir.config_parameter'].sudo().get_param('cv_importer.auto_apply_data', 'True')
            fields_applied = 0
            if auto_apply == 'True' and extracted_data:
                try:
                    employee = cv_document.employee_id
                    field_mapping = {
                        'extracted_presentacion': 'x_presentacion',
                        'extracted_docencia': 'x_docencia_periodo',
                        'extracted_proyectos': 'x_proyectos',
                        'extracted_publicaciones': 'x_publicaciones',
                        'extracted_telefono': 'phone',
                        'extracted_email_personal': 'x_email_personal',
                        'extracted_titulo_principal': 'x_titulo_principal',
                        'extracted_anos_experiencia': 'x_anos_experiencia',
                        'extracted_orcid': 'x_orcid',
                        'extracted_oficina': 'x_oficina',
                        'extracted_idiomas': 'x_idiomas',
                        'extracted_total_publicaciones': 'x_total_publicaciones',
                        'extracted_total_proyectos': 'x_total_proyectos',
                        'extracted_titulos_academicos': 'x_titulos_academicos',
                        'extracted_experiencia_laboral': 'x_experiencia_laboral',
                        'extracted_capacitaciones': 'x_capacitaciones',
                        'extracted_docencia_detalle': 'x_formacion_continua',
                        'extracted_distinciones': 'x_distinciones'
                    }
                    additional_mappings = {
                        'extracted_proyectos': 'x_participacion_proyectos',
                        'extracted_publicaciones': 'x_publicaciones_detalle'
                    }
                    vals = {}
                    for k, dest in field_mapping.items():
                        if extracted_data.get(k):
                            vals[dest] = extracted_data[k]
                    for k, dest in additional_mappings.items():
                        if extracted_data.get(k):
                            vals[dest] = extracted_data[k]
                    if vals:
                        employee.write(vals)
                        fields_applied = len(vals)
                except Exception as e:
                    _logger.warning(f"⚠️ Error aplicando datos automáticamente: {str(e)}")
                    _logger.error(f"🔥 Traceback: {traceback.format_exc()}")

            # Encadenado del lote si este pasó a processed y no lo estaba antes
            next_dispatched = False
            try:
                if (mapped_state == 'processed'
                        and previous_state != 'processed'
                        and cv_document.batch_token):
                    request.env.cr.commit()  # asegurar persistencia antes de despachar
                    cv_document._dispatch_next_in_batch()
                    next_dispatched = True
            except Exception as e:
                _logger.warning(f"⚠️ No se pudo despachar el siguiente del lote: {e}")

            processing_method = data.get('processing_method', 'unknown')
            has_markdown = data.get('has_markdown', False)

            _logger.info(
                f"🎉 Callback procesado para {employee_name} | "
                f"estado={mapped_state} (antes={previous_state}) | "
                f"batch={cv_document.batch_token or '-'} | next={next_dispatched}"
            )

            return {
                'status': 'success',
                'message': 'CV processed successfully',
                'cedula': cedula,
                'employee_name': employee_name,
                'fields_updated': len(extracted_data),
                'fields_applied_to_employee': fields_applied,
                'processing_method': processing_method,
                'has_markdown': has_markdown,
                'auto_apply_enabled': auto_apply == 'True',
                'extracted_fields': list(extracted_data.keys()) if extracted_data else [],
                'odoo_state': mapped_state,
                'next_dispatched': next_dispatched,
                'job_id': n8n_job_id,
            }

        except Exception as e:
            _logger.error(f"🔥 Error en callback CV: {str(e)}")
            return {'status': 'error', 'message': f'Internal error: {str(e)}'}

    @http.route('/cv/callback/test', type='json', auth='none', methods=['GET', 'POST'], csrf=False)
    def cv_callback_test(self, **kw):
        _logger.info("🧪 Endpoint de prueba de callback CV accedido")
        return {
            'status': 'success',
            'message': 'CV callback endpoint is working',
            'timestamp': str(request.env['ir.http']._get_default_session_info().get('now')),
            'test': True
        }

    @http.route('/cv/callback/debug', type='json', auth='none', methods=['POST'], csrf=False)
    def cv_callback_debug(self, **kw):
        try:
            data = request.get_json_data()
            if not data:
                data = kw
            _logger.info("🐛 DEBUG CALLBACK - Datos recibidos:")
            _logger.info(f"🔍 Estructura completa: {json.dumps(data, indent=2, ensure_ascii=False)}")
            return {
                'status': 'debug_success',
                'message': 'Debug callback received',
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
            _logger.error(f"🔥 Error en debug callback: {str(e)}")
            return {'status': 'debug_error', 'error': str(e)}
