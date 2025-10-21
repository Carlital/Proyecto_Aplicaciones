# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import json

# 👉 Usa una sola fuente de verdad
from ..config_constants import (
    CV_IMPORT_TIMEOUT,
    CV_IMPORT_RETRIES,
    CV_IMPORT_HEADERS,
)

_logger = logging.getLogger(__name__)

class CvConfig(models.Model):
    _inherit = 'cv.config'
    
    # Alias “semánticos” para que el resto del código/tests sigan igual
    DEFAULT_TIMEOUT = CV_IMPORT_TIMEOUT
    MAX_RETRIES = CV_IMPORT_RETRIES
    RETRY_DELAY = 1  # si quieres también centralizarlo, añádelo a config_constants
    DEFAULT_HEADERS = CV_IMPORT_HEADERS

    # Configuraciones de parsing/validación/caché
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS = ['.pdf', '.doc', '.docx', '.txt']
    MIN_EXPERIENCE_YEARS = 0
    MAX_EXPERIENCE_YEARS = 50
    MIN_NAME_LENGTH = 2
    MAX_NAME_LENGTH = 100
    CACHE_TTL = 3600  # 1 hora
    MAX_CACHE_SIZE = 1000
    
    # ===== Getters centralizados =====
    @api.model
    def get_timeout(self):
        # ⚠️ cast a int para que tus tests no fallen
        return int(self.env['ir.config_parameter'].sudo().get_param(
            'cv_importer.timeout', self.DEFAULT_TIMEOUT
        ))
    
    @api.model
    def get_max_retries(self):
        return int(self.env['ir.config_parameter'].sudo().get_param(
            'cv_importer.max_retries', self.MAX_RETRIES
        ))
    
    @api.model
    def get_headers(self):
        headers = dict(self.DEFAULT_HEADERS)  # copia
        custom_headers = self.env['ir.config_parameter'].sudo().get_param(
            'cv_importer.custom_headers', '{}'
        )
        if custom_headers:
            try:
                headers.update(json.loads(custom_headers))
            except Exception:
                # podrías loggear el error si quieres auditar
                pass
        return headers

    # ===== Campos persistentes =====
    url_base = fields.Char('URL Base', required=True, default='https://hojavida.espoch.edu.ec/cv/')
    timeout = fields.Integer('Timeout (segundos)', default=CV_IMPORT_TIMEOUT)
    
    # N8N
    n8n_webhook_url = fields.Char('URL Webhook N8N', help='URL del webhook N8N para procesamiento de CVs')
    n8n_api_key = fields.Char('API Key N8N', help='API Key para autenticación con N8N')

    # Desarrollo local
    local_development = fields.Boolean('Modo Desarrollo Local', help='Activar para desarrollo local con ngrok')
    ngrok_url = fields.Char('URL Ngrok', help='URL de ngrok para desarrollo local')

    def action_setup_local_development(self):
        """Setup local development environment guide."""
        self.ensure_one()
        # (Opcional) valida que el modelo exista para evitar errores de carga
        # if not self.env.registry.get('cv.setup.wizard'):
        #     raise UserError(_('El wizard cv.setup.wizard no está disponible.'))
        return {
            'type': 'ir.actions.act_window',
            'name': 'Local Development Setup Guide',
            'view_mode': 'form',
            'res_model': 'cv.setup.wizard',
            'target': 'new',
            'context': {'default_config_id': self.id},
        }
    
    def _get_callback_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        if self.local_development and self.ngrok_url:
            base_url = (self.ngrok_url or '').rstrip('/')
        return f"{base_url}/cv/callback"

    def action_test_n8n(self):
        """Test N8N connection with proper callback URL"""
        self.ensure_one()
        try:
            import requests
            callback_url = self._get_callback_url()
            test_payload = {
                "test": True,
                "message": "Test desde Odoo",
                "callback_url": callback_url,
                "timestamp": fields.Datetime.now()
            }
            # Usa la configuración centralizada
            headers = self.get_headers()
            if self.n8n_api_key:
                headers['Authorization'] = f"Bearer {self.n8n_api_key}"
            response = requests.post(
                self.n8n_webhook_url,
                json=test_payload,
                timeout=self.get_timeout(),
                headers=headers,
            )
            if response.status_code in [200, 201]:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Conexión Exitosa',
                        'message': f'N8N respondió correctamente (status {response.status_code})',
                        'type': 'success'
                    }
                }
            else:
                raise UserError(f"Error: Status {response.status_code}\n{response.text}")
        except Exception as e:
            raise UserError(f"Error al conectar con N8N: {str(e)}")


class CvImporterConfig(models.TransientModel):
    _name = 'cv.importer.config'
    _description = 'Configuración de CV Importer'

    n8n_webhook_url = fields.Char(
        string='URL Webhook N8N',
        required=True,
        default=lambda self: self.env['ir.config_parameter'].sudo().get_param(
            'cv_importer.n8n_webhook_url',
            'https://n8n.pruebasbidata.site/webhook/process-cv'
        ),
        help='URL del webhook de N8N para procesar CVs.'
    )
    auto_apply_data = fields.Boolean(
        string='Aplicar datos automáticamente',
        default=lambda self: self.env['ir.config_parameter'].sudo().get_param(
            'cv_importer.auto_apply_data', 'True'
        ) == 'True',
    )
    timeout = fields.Integer(
        string='Timeout (segundos)',
        default=lambda self: int(self.env['ir.config_parameter'].sudo().get_param(
            'cv_importer.timeout', str(CV_IMPORT_TIMEOUT)
        )),
    )
    
    # --- Helper centralizado para probar conexión N8N ---
    def _build_n8n_test_url(self, base_url):
        ICP = self.env['ir.config_parameter'].sudo()
        test_path = ICP.get_param('cv_importer.n8n_test_path')  # opcional: ej '/webhook/test'
        if test_path:
            if test_path.startswith('http://') or test_path.startswith('https://'):
                return test_path
            # une preservando esquema/host
            from urllib.parse import urljoin
            return urljoin(base_url.rstrip('/') + '/', test_path.lstrip('/'))
        # fallback: mismo URL con query ?test=1
        sep = '&' if '?' in base_url else '?'
        return f"{base_url}{sep}test=1"

    def action_save_config(self):
        for record in self:
            if not record.n8n_webhook_url:
                raise UserError(_('La URL del webhook N8N es requerida'))
            if not record.n8n_webhook_url.startswith(('http://', 'https://')):
                raise UserError(_('La URL del webhook N8N debe comenzar con http:// o https://'))
            ICP = self.env['ir.config_parameter'].sudo()
            ICP.set_param('cv_importer.n8n_webhook_url', record.n8n_webhook_url)
            ICP.set_param('cv_importer.auto_apply_data', str(record.auto_apply_data))
            ICP.set_param('cv_importer.timeout', str(record.timeout))
            _logger.info(f"Configuración de CV Importer actualizada: URL={record.n8n_webhook_url}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': 'Configuración Guardada', 'message': 'Configuración guardada con éxito', 'type': 'success'}
            }

    def action_test_connection(self):
        """Prueba simple contra N8N:
           1) GET al endpoint de test (o webhook?test=1)
           2) Si 404 indica que solo acepta POST, hace POST mínimo.
        """
        import requests
        for record in self:
            if not record.n8n_webhook_url:
                raise UserError(_('La URL del webhook N8N es requerida'))
            test_url = self._build_n8n_test_url(record.n8n_webhook_url)
            try:
                resp = requests.get(test_url, timeout=10)
                if 200 <= resp.status_code < 300:
                    msg = f"Conexión exitosa (GET {resp.status_code})"
                    level = 'success'
                elif resp.status_code == 404 and 'not registered for GET' in (resp.text or '').lower():
                    # Fallback a POST mínimo
                    payload = {"test": True, "method": "fallback_post", "timestamp": fields.Datetime.now().isoformat()}
                    post_resp = requests.post(record.n8n_webhook_url, json=payload, timeout=10)
                    if 200 <= post_resp.status_code < 300:
                        msg = f"Conexión exitosa vía POST (HTTP {post_resp.status_code})"
                        level = 'success'
                    else:
                        msg = f"Fallo POST HTTP {post_resp.status_code}: {post_resp.text[:160] or 'Sin cuerpo'}"
                        level = 'danger'
                else:
                    msg = f"Fallo HTTP {resp.status_code}: {resp.text[:160] or 'Sin cuerpo'}"
                    level = 'danger'

                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Conexión N8N',
                        'message': msg,
                        'type': level,
                        'sticky': level != 'success',
                    }
                }
            except requests.exceptions.Timeout:
                raise UserError(_('Timeout: el endpoint no respondió dentro del límite.'))
            except requests.exceptions.ConnectionError as e:
                raise UserError(_('Error de conexión: %s') % e)
            except Exception as e:
                raise UserError(_('Error inesperado: %s') % e)

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
        """POST mínimo al webhook principal (no endpoint de test)."""
        import requests
        for record in self:
            if not record.n8n_webhook_url:
                raise UserError(_('URL de webhook N8N no configurada'))
            try:
                payload = {
                    "test": True,
                    "message": "Prueba de conexión desde Odoo",
                    "timestamp": fields.Datetime.now()
                }
                resp = requests.post(record.n8n_webhook_url, json=payload, timeout=record.timeout or 30)
                ok = 200 <= resp.status_code < 300
                msg = (f"Webhook aceptó la petición (HTTP {resp.status_code})"
                       if ok else f"Error HTTP {resp.status_code}: {resp.text[:160]}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Prueba N8N (POST)',
                        'message': msg,
                        'type': 'success' if ok else 'danger',
                        'sticky': not ok,
                    }
                }
            except requests.exceptions.Timeout:
                raise UserError(_('Timeout al conectar con N8N.'))
            except requests.exceptions.ConnectionError as e:
                raise UserError(_('No se pudo conectar con N8N: %s') % e)
            except Exception as e:
                raise UserError(_('Error inesperado: %s') % e)
