# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import json
import logging
import traceback

_logger = logging.getLogger(__name__)

class CVCallbackController(http.Controller):
    
    @http.route('/cv/callback', type='json', auth='none', methods=['POST'], csrf=False)
    def cv_callback(self, **kw):
        """Endpoint para recibir resultados procesados desde N8N"""
        try:
            # Obtener datos del JSON enviado por N8N
            data = request.get_json_data()
            if not data:
                data = kw
            
            _logger.info("📥 Callback recibido de N8N")
            _logger.info(f"🔍 Datos recibidos: {list(data.keys()) if data else 'No data'}")
            
            # DEBUG: Mostrar una muestra de los datos principales que deberían llegar
            if data:
                _logger.info(f"🔍 DEBUG - Muestra de datos:")
                _logger.info(f"  - cedula: {data.get('cedula', 'NOT FOUND')}")
                _logger.info(f"  - employee_name: {data.get('employee_name', 'NOT FOUND')}")
                _logger.info(f"  - extracted_data existe: {bool(data.get('extracted_data'))}")
                _logger.info(f"  - additional_fields existe: {bool(data.get('additional_fields'))}")
                if data.get('extracted_data'):
                    _logger.info(f"  - extracted_data keys: {list(data['extracted_data'].keys())}")
                if data.get('additional_fields'):
                    _logger.info(f"  - additional_fields keys: {list(data['additional_fields'].keys())}")
            
            if not data:
                _logger.error("❌ No se recibieron datos en el callback")
                return {'status': 'error', 'message': 'No data received'}
            
            # Extraer información básica
            cedula = data.get('cedula')
            employee_name = data.get('employee_name')
            
            if not cedula:
                _logger.error("❌ Falta cédula en el callback")
                return {'status': 'error', 'message': 'Missing cedula'}
            
            _logger.info(f"👤 Procesando callback para: {employee_name} (Cédula: {cedula})")
            
            # Buscar el documento CV correspondiente
            cv_document = request.env['cv.document'].sudo().search([
                ('cedula', '=', cedula)
            ], limit=1)
            
            if not cv_document:
                _logger.error(f"❌ No se encontró documento CV para cédula: {cedula}")
                return {'status': 'error', 'message': f'CV document not found for cedula: {cedula}'}
            
            # Actualizar estado del documento
            cv_document.state = 'processed'
            
            # Guardar el texto procesado desde el campo correcto
            processed_text = data.get('processed_text', '')
            if not processed_text:
                processed_text = data.get('markdown_content', '')
            cv_document.processed_text = processed_text
            
            # Extraer y guardar información procesada
            extracted_data = {}
            
            # Debug: Imprimir estructura de datos recibida
            _logger.info(f"🔍 DEBUG - Claves principales en data: {list(data.keys())}")
            
            # Obtener datos de la estructura anidada que envía n8n
            extracted_info = data.get('extracted_data', {})
            additional_info = data.get('additional_fields', {})
            
            _logger.info(f"🔍 DEBUG - extracted_data keys: {list(extracted_info.keys()) if extracted_info else 'None'}")
            _logger.info(f"🔍 DEBUG - additional_fields keys: {list(additional_info.keys()) if additional_info else 'None'}")
            
            # Datos principales del CV desde extracted_data
            if extracted_info.get('presentacion') and str(extracted_info['presentacion']).strip():
                extracted_data['extracted_presentacion'] = extracted_info['presentacion']
                _logger.info(f"✅ Extraído presentación: {len(str(extracted_info['presentacion']))} chars")
            if extracted_info.get('docencia') and str(extracted_info['docencia']).strip():
                extracted_data['extracted_docencia'] = extracted_info['docencia']
                _logger.info(f"✅ Extraído docencia: {len(str(extracted_info['docencia']))} chars")
            if extracted_info.get('proyectos') and str(extracted_info['proyectos']).strip():
                extracted_data['extracted_proyectos'] = extracted_info['proyectos']
                _logger.info(f"✅ Extraído proyectos: {len(str(extracted_info['proyectos']))} chars")
            if extracted_info.get('publicaciones') and str(extracted_info['publicaciones']).strip():
                extracted_data['extracted_publicaciones'] = extracted_info['publicaciones']
                _logger.info(f"✅ Extraído publicaciones: {len(str(extracted_info['publicaciones']))} chars")
            
            # Datos adicionales desde additional_fields
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
                if additional_info.get(n8n_field) is not None:
                    value = additional_info[n8n_field]
                    # Solo agregar si el valor no está vacío
                    if isinstance(value, str) and value.strip():
                        extracted_data[f'extracted_{odoo_field}'] = value
                        _logger.info(f"✅ Extraído {odoo_field}: {value}")
                    elif isinstance(value, (int, float)) and value != 0:
                        extracted_data[f'extracted_{odoo_field}'] = value
                        _logger.info(f"✅ Extraído {odoo_field}: {value}")
                    elif not isinstance(value, (str, int, float)) and value:
                        extracted_data[f'extracted_{odoo_field}'] = value
                        _logger.info(f"✅ Extraído {odoo_field}: {value}")
            
            # Extraer información adicional del raw_extracted_data para campos detallados
            raw_data = data.get('raw_extracted_data', {})
            if raw_data:
                _logger.info(f"🔍 DEBUG - raw_extracted_data keys: {list(raw_data.keys())}")
                
                # Títulos académicos desde educación
                if raw_data.get('educacion'):
                    titulos = []
                    for edu in raw_data['educacion']:
                        titulo = edu.get('titulo', '')
                        institucion = edu.get('institucion', '')
                        nivel = edu.get('nivel', '')
                        if titulo:
                            titulos.append(f"• {titulo} - {institucion} ({nivel})")
                    if titulos:
                        extracted_data['extracted_titulos_academicos'] = '\n'.join(titulos)
                        _logger.info(f"✅ Extraído títulos académicos: {len(titulos)} títulos")
                
                # Experiencia laboral desde experiencia
                if raw_data.get('experiencia'):
                    experiencias = []
                    for exp in raw_data['experiencia']:
                        cargo = exp.get('cargo', '')
                        fecha_inicio = exp.get('fecha_inicio', '')
                        fecha_fin = exp.get('fecha_fin', '')
                        if cargo:
                            experiencias.append(f"• {cargo} ({fecha_inicio} - {fecha_fin})")
                    if experiencias:
                        extracted_data['extracted_experiencia_laboral'] = '\n'.join(experiencias)
                        _logger.info(f"✅ Extraído experiencia laboral: {len(experiencias)} experiencias")
                
                # Capacitaciones desde certificaciones
                if raw_data.get('certificaciones'):
                    capacitaciones = []
                    for cert in raw_data['certificaciones']:
                        descripcion = cert.get('descripcion', '')
                        institucion = cert.get('institucion', '')
                        if descripcion:
                            capacitaciones.append(f"• {descripcion} - {institucion}")
                    if capacitaciones:
                        extracted_data['extracted_capacitaciones'] = '\n'.join(capacitaciones)
                        _logger.info(f"✅ Extraído capacitaciones: {len(capacitaciones)} capacitaciones")
                
                # Materias impartidas (docencia detallada)
                if raw_data.get('materias'):
                    materias = []
                    for materia in raw_data['materias']:
                        carrera = materia.get('carrera', '')
                        asignatura = materia.get('asignatura', '')
                        if asignatura:
                            materias.append(f"• {asignatura} - {carrera}")
                    if materias:
                        extracted_data['extracted_docencia_detalle'] = '\n'.join(materias)
                        _logger.info(f"✅ Extraído materias: {len(materias)} materias")
                
                # Logros y reconocimientos
                if raw_data.get('logros'):
                    logros = []
                    for logro in raw_data['logros']:
                        descripcion = logro.get('descripcion', '')
                        tipo = logro.get('tipo', '')
                        if descripcion:
                            logros.append(f"• {descripcion} ({tipo})")
                    if logros:
                        extracted_data['extracted_distinciones'] = '\n'.join(logros)
                        _logger.info(f"✅ Extraído logros: {len(logros)} logros")
            
            # También verificar si vienen directamente en el primer nivel (retrocompatibilidad)
            if not extracted_info and not additional_info:
                _logger.info("🔄 Intentando extraer datos del primer nivel como fallback")
                # Datos principales del CV
                if data.get('presentacion'):
                    extracted_data['extracted_presentacion'] = data['presentacion']
                    _logger.info(f"✅ Extraído presentación (primer nivel): {len(data['presentacion'])} chars")
                if data.get('docencia'):
                    extracted_data['extracted_docencia'] = data['docencia']
                    _logger.info(f"✅ Extraído docencia (primer nivel): {len(data['docencia'])} chars")
                if data.get('proyectos'):
                    extracted_data['extracted_proyectos'] = data['proyectos']
                    _logger.info(f"✅ Extraído proyectos (primer nivel): {len(data['proyectos'])} chars")
                if data.get('publicaciones'):
                    extracted_data['extracted_publicaciones'] = data['publicaciones']
                    _logger.info(f"✅ Extraído publicaciones (primer nivel): {len(data['publicaciones'])} chars")
                
                # Datos adicionales
                for odoo_field, n8n_field in additional_fields_mapping.items():
                    if data.get(n8n_field):
                        extracted_data[f'extracted_{odoo_field}'] = data[n8n_field]
                        _logger.info(f"✅ Extraído {odoo_field} (primer nivel): {data[n8n_field]}")
            
            _logger.info(f"📊 Total de campos extraídos: {len(extracted_data)}")
            _logger.info(f"📋 Campos extraídos: {list(extracted_data.keys())}")
            
            # Actualizar documento CV con datos extraídos
            if extracted_data:
                cv_document.write(extracted_data)
                _logger.info(f"✅ Datos extraídos guardados: {len(extracted_data)} campos")
                _logger.info(f"🔍 Campos guardados: {list(extracted_data.keys())}")
            else:
                _logger.warning(f"⚠️ No se encontraron datos para extraer del callback")
                _logger.info(f"🔍 Estructura de datos recibida: {json.dumps(data, indent=2, ensure_ascii=False)[:1000]}...")
            # Auto-aplicar datos al empleado si está configurado
            auto_apply = request.env['ir.config_parameter'].sudo().get_param('cv_importer.auto_apply_data', 'True')
            fields_applied = 0
            
            if auto_apply == 'True' and extracted_data:
                try:
                    # Contar cuántos campos se van a aplicar al empleado
                    employee = cv_document.employee_id
                    fields_to_apply = {}
                    
                    # Mapear campos extraídos a campos del empleado
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
                    
                    # Mapeos adicionales para proyectos y publicaciones detalladas
                    additional_mappings = {
                        'extracted_proyectos': 'x_participacion_proyectos',
                        'extracted_publicaciones': 'x_publicaciones_detalle'
                    }
                    
                    for extracted_field, employee_field in field_mapping.items():
                        if extracted_field in extracted_data and extracted_data[extracted_field]:
                            fields_to_apply[employee_field] = extracted_data[extracted_field]
                    
                    # Aplicar mapeos adicionales
                    for extracted_field, employee_field in additional_mappings.items():
                        if extracted_field in extracted_data and extracted_data[extracted_field]:
                            fields_to_apply[employee_field] = extracted_data[extracted_field]
                    
                    if fields_to_apply:
                        employee.write(fields_to_apply)
                        fields_applied = len(fields_to_apply)
                        _logger.info(f"✅ Datos aplicados automáticamente al empleado {employee.name}: {fields_applied} campos")
                        _logger.info(f"🔍 Campos aplicados: {list(fields_to_apply.keys())}")
                    else:
                        _logger.warning(f"⚠️ No hay campos válidos para aplicar al empleado")
                        
                except Exception as e:
                    _logger.warning(f"⚠️ Error aplicando datos automáticamente: {str(e)}")
                    _logger.error(f"🔥 Traceback: {traceback.format_exc()}")
            else:
                _logger.info(f"ℹ️ Auto-aplicación deshabilitada o sin datos para aplicar")
            
            # Log de éxito
            processing_method = data.get('processing_method', 'unknown')
            has_markdown = data.get('has_markdown', False)
            
            _logger.info(f"🎉 Callback procesado exitosamente para {employee_name}")
            _logger.info(f"📄 Método: {processing_method}")
            _logger.info(f"🔄 Conversión local usada: {'✅' if has_markdown else '❌'}")
            
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
                'extracted_fields': list(extracted_data.keys()) if extracted_data else []
            }
            
        except Exception as e:
            _logger.error(f"🔥 Error en callback CV: {str(e)}")
            return {
                'status': 'error', 
                'message': f'Internal error: {str(e)}'
            }
    
    @http.route('/cv/callback/test', type='json', auth='none', methods=['GET', 'POST'], csrf=False)
    def cv_callback_test(self, **kw):
        """Endpoint de prueba para verificar que el callback funciona"""
        _logger.info("🧪 Endpoint de prueba de callback CV accedido")
        return {
            'status': 'success',
            'message': 'CV callback endpoint is working',
            'timestamp': str(request.env['ir.http']._get_default_session_info().get('now')),
            'test': True
        }

    @http.route('/cv/callback/debug', type='json', auth='none', methods=['POST'], csrf=False)
    def cv_callback_debug(self, **kw):
        """Endpoint de debug para ver exactamente qué datos llegan"""
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
            return {
                'status': 'debug_error',
                'error': str(e)
            }
