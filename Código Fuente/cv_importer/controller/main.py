from odoo import http
from odoo.http import request
import json
import logging
import base64

_logger = logging.getLogger(__name__)

class CvImportController(http.Controller):
    
    @http.route('/cv/upload', type='http', auth='user', methods=['POST'])
    def upload_cv(self, **kwargs):
        """Subir CV directamente desde formulario web"""
        try:
            employee_id = kwargs.get('employee_id')
            if not employee_id:
                return json.dumps({'error': 'ID de empleado requerido'})
            
            employee = request.env['hr.employee'].browse(int(employee_id))
            if not employee.exists():
                return json.dumps({'error': 'Empleado no encontrado'})
            
            # Obtener archivo subido
            cv_file = request.httprequest.files.get('cv_file')
            if not cv_file:
                return json.dumps({'error': 'Archivo PDF requerido'})
            
            # Validar tipo de archivo
            if not cv_file.filename.lower().endswith('.pdf'):
                return json.dumps({'error': 'Solo se permiten archivos PDF'})
            
            # Crear documento CV
            cv_document = request.env['cv.document'].create({
                'name': f"CV - {employee.name}",
                'employee_id': employee.id,
                'cv_file': base64.b64encode(cv_file.read()),
                'cv_filename': cv_file.filename
            })
            
            # Procesar automáticamente
            cv_document.action_upload_to_n8n()
            
            return json.dumps({
                'success': True,
                'message': f'CV subido y enviado para procesamiento',
                'cv_document_id': cv_document.id
            })
            
        except Exception as e:
            _logger.error(f"Error subiendo CV: {str(e)}")
            return json.dumps({'error': str(e)})

    @http.route('/cv/download_auto/<string:cedula>', type='json', auth='user')
    def download_cv_auto(self, cedula, **kwargs):
        """Descargar CV automáticamente por cédula"""
        try:
            employee = request.env['hr.employee'].search([('identification_id', '=', cedula)], limit=1)
            if not employee:
                return {'error': 'Empleado no encontrado'}
            
            # Verificar si ya existe un documento CV
            existing_cv = request.env['cv.document'].search([
                ('employee_id', '=', employee.id)
            ], limit=1)
            
            if existing_cv:
                existing_cv.action_reset_to_draft()
                existing_cv.action_download_and_process()
                cv_document_id = existing_cv.id
            else:
                cv_document = request.env['cv.document'].create({
                    'name': f"CV - {employee.name}",
                    'employee_id': employee.id
                })
                cv_document.action_download_and_process()
                cv_document_id = cv_document.id
            
            return {
                'success': True,
                'message': 'CV descargado y enviado para procesamiento',
                'cv_document_id': cv_document_id,
                'employee_name': employee.name
            }
            
        except Exception as e:
            _logger.error(f"Error descargando CV automático: {str(e)}")
            return {'error': str(e)}

    @http.route('/cv/bulk_download', type='json', auth='user')
    def bulk_download_cvs(self, **kwargs):
        """Descarga masiva de CVs"""
        try:
            faculty_id = kwargs.get('faculty_id')
            employee_ids = kwargs.get('employee_ids', [])
            overwrite_existing = kwargs.get('overwrite_existing', False)
            
            if faculty_id:
                # Buscar empleados por facultad
                domain = [
                    ('x_facultad', '=', faculty_id),
                    ('identification_id', '!=', False)
                ]
                employees = request.env['hr.employee'].search(domain)
            elif employee_ids:
                # Empleados específicos
                employees = request.env['hr.employee'].browse(employee_ids)
            else:
                return {'error': 'Debe especificar facultad o empleados'}
            
            results = []
            
            for employee in employees:
                try:
                    existing_cv = request.env['cv.document'].search([
                        ('employee_id', '=', employee.id)
                    ], limit=1)
                    
                    if existing_cv:
                        if overwrite_existing or existing_cv.state in ['draft', 'error']:
                            existing_cv.action_reset_to_draft()
                            existing_cv.action_download_and_process()
                            results.append({
                                'employee_name': employee.name,
                                'status': 'updated',
                                'cv_document_id': existing_cv.id
                            })
                        else:
                            results.append({
                                'employee_name': employee.name,
                                'status': 'skipped',
                                'cv_document_id': existing_cv.id
                            })
                    else:
                        cv_document = request.env['cv.document'].create({
                            'name': f"CV - {employee.name}",
                            'employee_id': employee.id
                        })
                        cv_document.action_download_and_process()
                        results.append({
                            'employee_name': employee.name,
                            'status': 'created',
                            'cv_document_id': cv_document.id
                        })
                        
                except Exception as e:
                    results.append({
                        'employee_name': employee.name,
                        'status': 'error',
                        'error': str(e)
                    })
            
            return {
                'success': True,
                'results': results,
                'total_processed': len(results)
            }
            
        except Exception as e:
            _logger.error(f"Error en descarga masiva: {str(e)}")
            return {'error': str(e)}

    @http.route('/cv/callback', type='json', auth='public', methods=['POST'], csrf=False)
    def cv_callback(self, **kwargs):
        """Callback desde N8N con datos procesados"""
        try:
            cedula = kwargs.get('cedula')
            if not cedula:
                return {'error': 'Cédula no proporcionada'}
            
            # Buscar documento CV pendiente
            cv_document = request.env['cv.document'].sudo().search([
                ('cedula', '=', cedula),
                ('state', 'in', ['uploaded', 'processing'])
            ], limit=1)
            
            if not cv_document:
                return {'error': 'Documento CV no encontrado'}
            
            # Extraer datos del callback
            extracted_data = kwargs.get('extracted_data', {})
            additional_fields = kwargs.get('additional_fields', {})
            processed_text = kwargs.get('processed_text', '')
            
            # Actualizar documento con secciones principales
            update_vals = {
                'state': 'processed',
                'processed_text': processed_text,
                'extracted_presentacion': extracted_data.get('presentacion', ''),
                'extracted_docencia': extracted_data.get('docencia', ''),
                'extracted_proyectos': extracted_data.get('proyectos', ''),
                'extracted_publicaciones': extracted_data.get('publicaciones', ''),
                
                # Campos adicionales extraídos (con nombres correctos del modelo)
                'extracted_telefono': additional_fields.get('telefono', ''),
                'extracted_email_personal': additional_fields.get('email_personal', ''),
                'extracted_titulo_principal': additional_fields.get('titulo_principal', ''),
                'extracted_anos_experiencia': additional_fields.get('anos_experiencia', 0),
                'extracted_orcid': additional_fields.get('orcid', ''),
                'extracted_oficina': additional_fields.get('oficina', ''),
                'extracted_idiomas': additional_fields.get('idiomas', ''),
                'extracted_total_publicaciones': additional_fields.get('total_publicaciones', 0),
                'extracted_total_proyectos': additional_fields.get('total_proyectos', 0)
            }
            
            cv_document.write(update_vals)
            
            # Aplicar automáticamente los datos al empleado
            cv_document.action_apply_extracted_data()
            
            _logger.info(f"CV procesado exitosamente para {cv_document.employee_id.name}")
            
            return {
                'success': True,
                'message': 'CV procesado y aplicado correctamente',
                'employee_name': cv_document.employee_id.name,
                'extracted_fields': len(additional_fields),
                'quality_score': kwargs.get('data_quality_score', 0.0)
            }
            
        except Exception as e:
            _logger.error(f"Error en callback de CV: {str(e)}")
            return {'error': str(e)}

    @http.route('/cv/update', type='json', auth='user')
    def update_cv(self, **kwargs):
        """Actualizar datos de CV manualmente (mantener compatibilidad)"""
        cedula = kwargs.get("cedula")
        if not cedula:
            return {'error': 'Cédula no proporcionada'}

        employee = request.env['hr.employee'].sudo().search([('identification_id', '=', cedula)], limit=1)
        if not employee:
            return {'error': 'Empleado no encontrado'}

        campos = [
            'x_presentacion', 'x_proyectos', 'x_publicaciones',
            'x_grupo_investigacion', 'x_contacto', 'x_docencia_periodo',
            'x_seminarios', 'x_titulos_academicos', 'x_experiencia_laboral',
            'x_formacion_continua', 'x_participacion_proyectos',
            'x_publicaciones_detalle', 'x_capacitaciones',
            'x_distinciones', 'x_idiomas'
        ]
        
        update_vals = {}
        for campo in campos:
            if campo in kwargs:
                update_vals[campo] = kwargs[campo]
        
        if update_vals:
            employee.write(update_vals)
            _logger.info(f"Datos actualizados manualmente para {employee.name}")

        return {'success': True, 'empleado': employee.name}

    @http.route('/cv/status/<int:cv_document_id>', type='json', auth='user')
    def get_cv_status(self, cv_document_id, **kwargs):
        """Obtener estado del procesamiento del CV"""
        try:
            cv_document = request.env['cv.document'].browse(cv_document_id)
            if not cv_document.exists():
                return {'error': 'Documento no encontrado'}
            
            return {
                'success': True,
                'state': cv_document.state,
                'employee_name': cv_document.employee_id.name,
                'error_message': cv_document.error_message,
                'has_extracted_data': bool(cv_document.extracted_presentacion or 
                                         cv_document.extracted_docencia or 
                                         cv_document.extracted_proyectos or 
                                         cv_document.extracted_publicaciones)
            }
            
        except Exception as e:
            _logger.error(f"Error obteniendo estado del CV: {str(e)}")
            return {'error': str(e)}

    @http.route('/cv/reprocess/<int:cv_document_id>', type='json', auth='user')
    def reprocess_cv(self, cv_document_id, **kwargs):
        """Reprocesar un CV"""
        try:
            cv_document = request.env['cv.document'].browse(cv_document_id)
            if not cv_document.exists():
                return {'error': 'Documento no encontrado'}
            
            cv_document.action_reset_to_draft()
            cv_document.action_upload_to_n8n()
            
            return {
                'success': True,
                'message': 'CV reenviado para procesamiento'
            }
            
        except Exception as e:
            _logger.error(f"Error reprocesando CV: {str(e)}")
            return {'error': str(e)}
