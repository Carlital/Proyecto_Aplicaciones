# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import json

from ..config_constants import (
    CV_IMPORT_TIMEOUT,
)

_logger = logging.getLogger(__name__)


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
    
    def _build_n8n_test_url(self, base_url):
        ICP = self.env['ir.config_parameter'].sudo()
        test_path = ICP.get_param('cv_importer.n8n_test_path')
        if test_path:
            if test_path.startswith('http://') or test_path.startswith('https://'):
                return test_path
            from urllib.parse import urljoin
            return urljoin(base_url.rstrip('/') + '/', test_path.lstrip('/'))
        sep = '&' if '?' in base_url else '?'
        return f"{base_url}{sep}test=1"

    def action_save_config(self):
        for record in self:
            if not record.n8n_webhook_url:
                raise UserError(_('La URL del webhook N8N es requerida'))
            if not record.n8n_webhook_url.startswith('https://'):
                raise UserError(_('La URL del webhook N8N debe comenzar con https://'))
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
                
                test_results = []
                
                try:
                    response = requests.get(record.n8n_webhook_url, timeout=10)
                    test_results.append(f"GET Request: {response.status_code}")
                except Exception as e:
                    test_results.append(f"GET Request falló: {str(e)}")
                
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
                    test_results.append(f"POST Minimal: {response.status_code}")
                    if response.text:
                        test_results.append(f"Response: {response.text[:100]}")
                except Exception as e:
                    test_results.append(f"POST Minimal falló: {str(e)}")
                
                test_pdf_content = b"PDF test content for CV processing"
                pdf_base64 = base64.b64encode(test_pdf_content).decode()
                
                full_payload = {
                    "cedula": "1234567890",
                    "employee_name": "Empleado de Prueba",
                    "pdf_data": pdf_base64,
                    "filename": "cv_test.pdf",
                    "odoo_callback_url": f"{self.env['ir.config_parameter'].sudo().get_param('web.base.url')}/cv/callback",
                    "download_url": "https://hojavida.espoch.edu.ec/cv/1234567890",
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
                    test_results.append(f"POST CV Data: {response.status_code}")
                    if response.text:
                        test_results.append(f"Full Response: {response.text}")
                        
                        try:
                            response_json = response.json()
                            test_results.append(f"JSON Response: {json.dumps(response_json, indent=2)}")
                        except:
                            test_results.append("Response is not valid JSON")
                            
                except Exception as e:
                    test_results.append(f"POST CV Data falló: {str(e)}")
                
                test_results.append(f"\nCONFIGURACIÓN:")
                test_results.append(f"  URL: {record.n8n_webhook_url}")
                test_results.append(f"  Timeout: {record.timeout}s")
                test_results.append(f"  Auto Apply: {record.auto_apply_data}")
                test_results.append(f"  Callback URL: {self.env['ir.config_parameter'].sudo().get_param('web.base.url')}/cv/callback")
                
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
