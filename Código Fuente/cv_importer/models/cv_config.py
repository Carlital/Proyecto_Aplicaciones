# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class CvImporterConfig(models.TransientModel):
    _name = 'cv.importer.config'
    _description = 'Configuración de CV Importer'

    n8n_webhook_url = fields.Char(
        string='URL Webhook N8N',
        required=True,
        default=lambda self: self.env['ir.config_parameter'].sudo().get_param('cv_importer.n8n_webhook_url', 'https://n8n.pruebasbidata.site/webhook/process-cv'),
        help='URL del webhook de N8N para procesar CVs. Ejemplos:\n'
             '- Cloud: https://n8n.pruebasbidata.site/webhook/process-cv\n'
    )
    
    auto_apply_data = fields.Boolean(
        string='Aplicar datos automáticamente',
        default=lambda self: self.env['ir.config_parameter'].sudo().get_param('cv_importer.auto_apply_data', 'True') == 'True',
        help='Si está marcado, los datos extraídos se aplicarán automáticamente al empleado'
    )
    
    timeout = fields.Integer(
        string='Timeout (segundos)',
        default=lambda self: int(self.env['ir.config_parameter'].sudo().get_param('cv_importer.timeout', '60')),
        help='Tiempo máximo de espera para las peticiones HTTP'
    )
    
    def action_save_config(self):
        """Guardar configuración"""
        for record in self:
            # Validar URL
            if not record.n8n_webhook_url:
                raise UserError(_('La URL del webhook N8N es requerida'))
            
            if not record.n8n_webhook_url.startswith(('http://', 'https://')):
                raise UserError(_('La URL del webhook N8N debe comenzar con http:// o https://'))
            
            # Guardar parámetros
            self.env['ir.config_parameter'].sudo().set_param('cv_importer.n8n_webhook_url', record.n8n_webhook_url)
            self.env['ir.config_parameter'].sudo().set_param('cv_importer.auto_apply_data', str(record.auto_apply_data))
            self.env['ir.config_parameter'].sudo().set_param('cv_importer.timeout', str(record.timeout))
            
            _logger.info(f"Configuración de CV Importer actualizada: URL={record.n8n_webhook_url}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Configuración Guardada',
                    'message': 'Configuración guardada con exito',
                    'type': 'success'
                }
            }
    
    def action_test_connection(self):
        """Probar conexión con N8N"""
        import requests
        
        for record in self:
            if not record.n8n_webhook_url:
                raise UserError(_('La URL del webhook N8N es requerida'))
            
            try:
                # Hacer una petición simple de prueba
                response = requests.get(
                    record.n8n_webhook_url.replace('/webhook/process-cv', '/webhook/test'),
                    timeout=10
                )
                
                if response.status_code in [200, 404]:  # 404 es esperado si no hay endpoint de test
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Conexión N8N',
                            'message': f'Conexión exitosa con N8N en: {record.n8n_webhook_url}',
                            'type': 'success'
                        }
                    }
                else:
                    raise UserError(f"Error de conexión: {response.status_code}")
                    
            except requests.exceptions.ConnectionError:
                raise UserError(f"❌ No se pudo conectar con N8N.\n\n"
                              f"URL: {record.n8n_webhook_url}\n\n"
                              f"Verifica que:\n"
                              f"1. El servidor N8N esté ejecutándose\n"
                              f"2. La URL sea correcta\n"
                              f"3. No haya firewall bloqueando la conexión")
            except requests.exceptions.Timeout:
                raise UserError(f"❌ Timeout al conectar con N8N.\n\n"
                              f"El servidor tardó demasiado en responder.")
            except Exception as e:
                raise UserError(f"❌ Error inesperado: {str(e)}")
    
    def action_test_n8n_comprehensive(self):
        """Prueba completa de conexión con N8N"""
        for record in self:
            if not record.n8n_webhook_url:
                raise UserError(_('La URL del webhook N8N es requerida'))
            
            try:
                import requests
                import json
                import base64
                from datetime import datetime
                
                # 1. Prueba de conectividad básica
                test_results = []
                
                # Probar GET request primero
                try:
                    response = requests.get(record.n8n_webhook_url, timeout=10)
                    test_results.append(f"✅ GET Request: {response.status_code}")
                except Exception as e:
                    test_results.append(f"❌ GET Request falló: {str(e)}")
                
                # 2. Prueba con datos mínimos
                minimal_payload = {
                    "test": True,
                    "message": "Prueba desde Odoo CV Importer",
                    "timestamp": datetime.now().isoformat()
                }
                
                try:
                    response = requests.post(
                        record.n8n_webhook_url,
                        json=minimal_payload,
                        timeout=15
                    )
                    test_results.append(f"✅ POST Minimal: {response.status_code}")
                    if response.text:
                        test_results.append(f"📄 Response: {response.text[:100]}")
                except Exception as e:
                    test_results.append(f"❌ POST Minimal falló: {str(e)}")
                
                # 3. Prueba con payload completo de CV
                test_pdf_content = b"PDF test content for CV processing"
                pdf_base64 = base64.b64encode(test_pdf_content).decode()
                
                full_payload = {
                    "cedula": "1234567890",
                    "employee_name": "Empleado de Prueba",
                    "pdf_data": pdf_base64,
                    "filename": "cv_test.pdf",
                    "odoo_callback_url": f"{self.env['ir.config_parameter'].sudo().get_param('web.base.url')}/cv/callback",
                    "download_url": "https://hojavida.espoch.edu.ec/cv/1234567890",
                    "auto_downloaded": False
                }
                
                try:
                    headers = {
                        'Content-Type': 'application/json',
                        'User-Agent': 'Odoo-CV-Importer/2.0'
                    }
                    
                    response = requests.post(
                        record.n8n_webhook_url,
                        json=full_payload,
                        headers=headers,
                        timeout=30
                    )
                    test_results.append(f"✅ POST CV Data: {response.status_code}")
                    if response.text:
                        test_results.append(f"📄 Full Response: {response.text}")
                        
                        # Intentar parsear como JSON
                        try:
                            response_json = response.json()
                            test_results.append(f"📊 JSON Response: {json.dumps(response_json, indent=2)}")
                        except:
                            test_results.append("📄 Response is not valid JSON")
                            
                except Exception as e:
                    test_results.append(f"❌ POST CV Data falló: {str(e)}")
                
                # 4. Información de configuración
                test_results.append(f"\n🔧 CONFIGURACIÓN:")
                test_results.append(f"  URL: {record.n8n_webhook_url}")
                test_results.append(f"  Timeout: {record.timeout}s")
                test_results.append(f"  Auto Apply: {record.auto_apply_data}")
                test_results.append(f"  Callback URL: {self.env['ir.config_parameter'].sudo().get_param('web.base.url')}/cv/callback")
                
                # Mostrar resultados
                message = "\n".join(test_results)
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Resultados de Prueba N8N',
                        'message': message,
                        'type': 'info',
                        'sticky': True
                    }
                }
                
            except Exception as e:
                raise UserError(f"Error en prueba de N8N: {str(e)}")

    def action_test_n8n_simple(self):
        """Prueba simple de conexión con N8N"""
        for record in self:
            if not record.n8n_webhook_url:
                raise UserError(_('URL de webhook N8N no configurada'))
            
            try:
                import requests
                
                # Hacer una petición simple de prueba
                test_payload = {
                    "test": True,
                    "message": "Prueba de conexión desde Odoo",
                    "url": record.n8n_webhook_url
                }
                
                response = requests.post(
                    record.n8n_webhook_url,
                    json=test_payload,
                    timeout=record.timeout or 30
                )
                
                if response.status_code in [200, 201]:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Prueba N8N',
                            'message': f'✅ Conexión exitosa\nStatus: {response.status_code}\nResponse: {response.text[:200]}',
                            'type': 'success'
                        }
                    }
                else:
                    raise UserError(f"Error de respuesta: {response.status_code}\n{response.text}")
                    
            except requests.exceptions.ConnectionError:
                raise UserError(f"❌ No se pudo conectar con N8N.\n\n"
                              f"URL: {record.n8n_webhook_url}\n\n"
                              f"Verifica que:\n"
                              f"1. El servidor N8N esté ejecutándose\n"
                              f"2. La URL sea correcta\n"
                              f"3. No haya firewall bloqueando la conexión")
            except requests.exceptions.Timeout:
                raise UserError(f"❌ Timeout al conectar con N8N.")
            except Exception as e:
                raise UserError(f"❌ Error: {str(e)}")
