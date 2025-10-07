from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import base64
import requests
import urllib3
from urllib.parse import urlparse
import socket
import ssl
import time
import os
from pathlib import Path
import tempfile
import hashlib

_logger = logging.getLogger(__name__)

# ---------------------------
# Helpers de archivos temporales
# ---------------------------
def _ensure_windows_path(p: str) -> str:
    return os.path.normpath(p)

def _ensure_dir_exists(file_path: str) -> str:
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    return file_path

def _get_temp_path(env) -> Path:
    db = getattr(getattr(env, 'cr', None), 'dbname', None) or 'default'
    base = Path(tempfile.gettempdir()) / 'odoo_cv_importer' / db
    base.mkdir(parents=True, exist_ok=True)
    return base

# ---------------------------
# Configuración SSL (legacy solo cuando se solicite)
# ---------------------------
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    # Guardamos el contexto seguro por defecto.
    _original_create_default_context = ssl.create_default_context

    # Contexto "legacy" para hosts con negociación antigua.
    def _create_legacy_ssl_context(*args, **kwargs):
        ctx = _original_create_default_context(*args, **kwargs)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        # Opciones de compatibilidad
        if hasattr(ssl, 'OP_LEGACY_SERVER_CONNECT'):
            ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
        if hasattr(ssl, 'OP_ALLOW_UNSAFE_LEGACY_RENEGOTIATION'):
            ctx.options |= ssl.OP_ALLOW_UNSAFE_LEGACY_RENEGOTIATION
        try:
            ctx.set_ciphers('DEFAULT@SECLEVEL=0')
        except Exception:
            try:
                ctx.set_ciphers('DEFAULT@SECLEVEL=1')
            except Exception:
                pass
        try:
            ctx.minimum_version = ssl.TLSVersion.TLSv1
        except Exception:
            pass
        return ctx

    # Adaptador requests con el contexto legacy
    from urllib3.util.ssl_ import create_urllib3_context
    from requests.adapters import HTTPAdapter

    class LegacySSLAdapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            ctx = create_urllib3_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            if hasattr(ssl, 'OP_LEGACY_SERVER_CONNECT'):
                ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
            if hasattr(ssl, 'OP_ALLOW_UNSAFE_LEGACY_RENEGOTIATION'):
                ctx.options |= ssl.OP_ALLOW_UNSAFE_LEGACY_RENEGOTIATION
            try:
                ctx.set_ciphers('DEFAULT@SECLEVEL=0')
            except Exception:
                try:
                    ctx.set_ciphers('DEFAULT@SECLEVEL=1')
                except Exception:
                    pass
            try:
                ctx.minimum_version = ssl.TLSVersion.TLSv1
            except Exception:
                pass
            kwargs['ssl_context'] = ctx
            return super().init_poolmanager(*args, **kwargs)

except Exception as e:
    _logger.warning(f"No se pudo preparar LegacySSLAdapter: {e}")
    LegacySSLAdapter = None  # type: ignore

# ===========================================================
#                       MODELOS
# ===========================================================
class CvDocument(models.Model):
    _name = 'cv.document'
    _description = 'Documento CV para procesamiento'
    _order = 'create_date desc'

    name = fields.Char(string='Nombre del Documento', required=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    cedula = fields.Char(string='Cédula', related='employee_id.identification_id', store=True)
    cv_file = fields.Binary(string='Archivo PDF', required=True)
    cv_filename = fields.Char(string='Nombre del Archivo')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('uploaded', 'Subido'),
        ('processing', 'Procesando'),
        ('processed', 'Procesado'),
        ('error', 'Error')
    ], string='Estado', default='draft')

    n8n_webhook_url = fields.Char(
        string='URL Webhook N8N',
        default=lambda self: self.env['ir.config_parameter'].sudo().get_param(
            'cv_importer.n8n_webhook_url',
            'https://n8n.pruebasbidata.site/webhook/process-cv'
        )
    )
    processed_text = fields.Text(string='Texto Procesado')
    error_message = fields.Text(string='Mensaje de Error')

    cv_download_url = fields.Char(string='URL de Descarga CV', compute='_compute_cv_download_url', store=True)
    auto_downloaded = fields.Boolean(string='Descargado Automáticamente', default=False)

    # Campos extraídos (solo como ejemplo; mantén los que uses)
    extracted_presentacion = fields.Text(string='Presentación Extraída')
    extracted_docencia = fields.Text(string='Docencia Extraída')
    extracted_proyectos = fields.Text(string='Proyectos Extraídos')
    extracted_publicaciones = fields.Text(string='Publicaciones Extraídas')
    extracted_telefono = fields.Char(string='Teléfono Extraído')
    extracted_email_personal = fields.Char(string='Email Personal Extraído')
    extracted_titulo_principal = fields.Char(string='Título Principal Extraído')
    extracted_anos_experiencia = fields.Integer(string='Años de Experiencia Extraídos')
    extracted_orcid = fields.Char(string='ORCID Extraído')
    extracted_oficina = fields.Char(string='Oficina Extraída')
    extracted_idiomas = fields.Text(string='Idiomas Extraídos')
    extracted_total_publicaciones = fields.Integer(string='Total Publicaciones')
    extracted_total_proyectos = fields.Integer(string='Total Proyectos')
    extracted_titulos_academicos = fields.Text(string='Títulos Académicos Extraídos')
    extracted_experiencia_laboral = fields.Text(string='Experiencia Laboral Extraída')
    extracted_capacitaciones = fields.Text(string='Capacitaciones Extraídas')
    extracted_docencia_detalle = fields.Text(string='Docencia Detallada Extraída')
    extracted_distinciones = fields.Text(string='Logros y Distinciones Extraídos')

    # ---------------------------
    # Compute / create
    # ---------------------------
    @api.depends('employee_id', 'employee_id.identification_id')
    def _compute_cv_download_url(self):
        for record in self:
            if record.employee_id and record.employee_id.identification_id:
                ced = record.employee_id.identification_id.zfill(10)
                record.cv_download_url = f"https://hojavida.espoch.edu.ec/cv/{ced}"
            else:
                record.cv_download_url = False

    @api.model
    def create(self, vals):
        if not vals.get('name') and vals.get('employee_id'):
            employee = self.env['hr.employee'].browse(vals['employee_id'])
            vals['name'] = f"CV - {employee.name}"
        return super().create(vals)

    # ---------------------------
    # SSL helpers / políticas
    # ---------------------------
    def _extract_host_port(self, url):
        parsed = urlparse(url or '')
        host = (parsed.hostname or '').lower()
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        return host, port

    def _ensure_ssl_params(self):
        ICP = self.env['ir.config_parameter'].sudo()
        defaults = {
            'cv_importer.allow_insecure_ssl': 'false',
            'cv_importer.insecure_hosts': '',
            'cv_importer.hojavida_pinned_sha256': '',
            'cv_importer.n8n_verify_ssl': 'true',
        }
        for k, v in defaults.items():
            current = ICP.get_param(k, default=None)
            if current in (None, False, ''):
                ICP.set_param(k, v)
                _logger.info(f"cv_importer: creado parámetro {k}={v}")

    def _should_verify_ssl(self, url):
        self._ensure_ssl_params()
        ICP = self.env['ir.config_parameter'].sudo()
        allow_insecure = (ICP.get_param('cv_importer.allow_insecure_ssl', 'false') or '').lower() == 'true'
        insecure_hosts_param = (ICP.get_param('cv_importer.insecure_hosts', '') or '').strip()
        insecure_hosts = [h.strip().lower() for h in insecure_hosts_param.split(',') if h.strip()]
        host, _ = self._extract_host_port(url)
        return not (allow_insecure and host in insecure_hosts)

    def _use_secure_ssl_context(self):
        try:
            ssl.create_default_context = _original_create_default_context  # type: ignore[name-defined]
            ssl._create_default_https_context = ssl.create_default_context
        except Exception:
            pass

    def _use_insecure_ssl_context(self):
        try:
            ssl.create_default_context = _create_legacy_ssl_context  # type: ignore[name-defined]
            ssl._create_default_https_context = ssl._create_unverified_context
        except Exception:
            pass

    def _get_session_for_url(self, url):
        verify = self._should_verify_ssl(url)
        if verify:
            self._use_secure_ssl_context()
            s = requests.Session()
            s.verify = True
            return s
        # inseguro -> solo con adaptador legacy
        self._use_insecure_ssl_context()
        s = requests.Session()
        if LegacySSLAdapter:
            s.mount('https://', LegacySSLAdapter())
        s.verify = False
        _logger.warning(f"SSL verify desactivado para {url}. Considera habilitar pinning (cv_importer.hojavida_pinned_sha256).")
        return s

    def _get_server_cert_sha256(self, host, port=443):
        pem = ssl.get_server_certificate((host, port))
        der = ssl.PEM_cert_to_DER_cert(pem)
        return hashlib.sha256(der).hexdigest()

    def _assert_pinned_cert(self, url, conf_key):
        pin = (self.env['ir.config_parameter'].sudo().get_param(conf_key, '') or '').replace(':', '').strip().lower()
        if not pin:
            return
        host, port = self._extract_host_port(url)
        current = self._get_server_cert_sha256(host, port)
        if current != pin:
            raise UserError(_(f"Pinning SSL falló para {host}. Esperado {pin}, obtenido {current}."))

    # ---------------------------
    # Diagnóstico (HEAD)
    # ---------------------------
    def action_test_connection(self):
        for record in self:
            if not record.cv_download_url:
                raise UserError(_('No se puede generar URL de descarga. Verifica que el empleado tenga cédula.'))
            parsed = urlparse(record.cv_download_url)
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == 'https' else 80)

            # DNS
            try:
                socket.gethostbyname(host)
            except socket.gaierror as e:
                raise UserError(_(f"Error de DNS para {host}: {e}"))

            # TCP
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10)
            try:
                if s.connect_ex((host, port)) != 0:
                    raise UserError(_(f"No se puede conectar a {host}:{port}"))
            finally:
                s.close()

            # HTTP HEAD
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            verify = self._should_verify_ssl(record.cv_download_url)
            session = self._get_session_for_url(record.cv_download_url)
            session.headers.update(headers)
            if not verify:
                self._assert_pinned_cert(record.cv_download_url, 'cv_importer.hojavida_pinned_sha256')

            resp = session.head(record.cv_download_url, verify=verify, timeout=15, allow_redirects=True)
            msg = (f"HTTP {resp.status_code} | Content-Type: {resp.headers.get('content-type')} | "
                   f"URL final: {resp.url} | SSL Verify: {'ON' if verify else 'OFF'}")
            record.error_message = msg
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': 'Prueba de Conexión', 'message': msg, 'type': 'success', 'sticky': True}
            }

    # ---------------------------
    # (Opcional) Descarga local – NO USAR si el SSL del host está roto
    # ---------------------------
    def action_download_cv_from_url(self):
        """Dejar disponible para entornos donde el SSL funcione; en tu caso usa action_upload_to_n8n()."""
        for record in self:
            if not record.cv_download_url:
                raise UserError(_('No se puede generar URL de descarga.'))
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'Accept': 'application/pdf,application/x-pdf,application/octet-stream,*/*',
            }
            verify = self._should_verify_ssl(record.cv_download_url)
            session = self._get_session_for_url(record.cv_download_url)
            session.headers.update(headers)
            if not verify:
                self._assert_pinned_cert(record.cv_download_url, 'cv_importer.hojavida_pinned_sha256')

            try:
                r = session.get(record.cv_download_url, verify=verify, timeout=45, allow_redirects=True, stream=True)
                if r.status_code != 200:
                    raise UserError(_(f"HTTP {r.status_code} al descargar CV"))
                content = r.content
                if not (content.startswith(b'%PDF') or b'PDF' in content[:1024]):
                    raise UserError(_('El contenido descargado no parece un PDF'))
                record.cv_file = base64.b64encode(content).decode('utf-8')
                record.cv_filename = f"cv_{(record.cedula or '').zfill(10)}.pdf"
                record.auto_downloaded = True
                record.state = 'uploaded'
            except Exception as e:
                record.state = 'error'
                record.error_message = f"Error descargando CV: {e}"

    def _prepare_file_path(self, filename):
        temp_dir = _get_temp_path(self.env)
        safe_name = os.path.basename(filename) if filename else f"tmp_{int(time.time())}.bin"
        file_path = str(temp_dir / safe_name)
        return _ensure_dir_exists(_ensure_windows_path(file_path))

    # ---------------------------
    # Envío a n8n (fetch-only)
    # ---------------------------
    def action_upload_to_n8n(self):
        """Enviar a n8n para que ÉL descargue y procese el CV (evita SSL legacy en Odoo)."""
        _logger.info("🚀 INICIANDO action_upload_to_n8n (fetch-only)")
        for record in self:
            # obtener config (última) y webhook efectivo
            config = self.env['cv.config'].search([], limit=1, order='id desc')
            effective_webhook = config._get_effective_webhook() if config else record.n8n_webhook_url
            if effective_webhook:
                record.n8n_webhook_url = effective_webhook  # sincroniza campo legacy
            if not record.n8n_webhook_url:
                raise UserError(_('URL de webhook N8N no configurada'))

            cedula = record.cedula or record.employee_id.identification_id
            if not cedula:
                raise UserError(_('El empleado debe tener una cédula asignada'))

            download_url = record.cv_download_url or ''
            if not download_url:
                raise UserError(_('No se pudo construir la URL de descarga del CV'))

            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            if 'localhost' in base_url or '127.0.0.1' in base_url:
                config = self.env['cv.config'].search([], limit=1)
                ngrok_url = (config.ngrok_url or self.env['ir.config_parameter'].sudo().get_param('cv_importer.ngrok_url', '')).strip()
                if ngrok_url and not ngrok_url.startswith('http'):
                    ngrok_url = f"https://{ngrok_url}"
                callback_url = f"{(ngrok_url or base_url)}/cv/callback"
            else:
                callback_url = f"{base_url}/cv/callback"

            payload = {
                'cedula': str(cedula),
                'employee_name': str(record.employee_id.name),
                'download_url': str(download_url),
                'odoo_callback_url': str(callback_url),
                'prefer_fetch': True,
                'timestamp': str(fields.Datetime.now().isoformat()),
                'odoo_version': '17.0',
                'module_version': '2.0',
            }

            self._ensure_ssl_params()
            verify_n8n = (self.env['ir.config_parameter'].sudo()
                          .get_param('cv_importer.n8n_verify_ssl', 'true') or '').lower() == 'true'
            timeout = int(self.env['ir.config_parameter'].sudo().get_param('cv_importer.timeout', '60'))

            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'Odoo-CV-Importer/2.0',
                'Accept': 'application/json',
                'Cache-Control': 'no-cache',
            }

            try:
                resp = requests.post(
                    record.n8n_webhook_url,  # ya efectivo
                    json=payload,
                    headers=headers,
                    timeout=timeout,
                    verify=verify_n8n
                )
                _logger.info(f"Respuesta N8N: {resp.status_code} - {resp.text[:400]}")
                if resp.status_code in (200, 201):
                    if record.state not in ['processing', 'processed']:
                        record.state = 'uploaded'
                elif resp.status_code == 404:
                    record.state = 'error'
                    record.error_message = f"Webhook N8N no encontrado (404): {record.n8n_webhook_url}"
                elif resp.status_code >= 500:
                    record.state = 'error'
                    record.error_message = f"Error del servidor N8N ({resp.status_code}): {resp.text}"
                else:
                    record.state = 'error'
                    record.error_message = f"Error en N8N: {resp.status_code} - {resp.text}"
            except requests.exceptions.Timeout as e:
                record.state = 'error'
                record.error_message = f"Timeout conectando con N8N: {e}"
            except requests.exceptions.ConnectionError as e:
                record.state = 'error'
                record.error_message = f"No se pudo conectar con N8N: {e}"
            except Exception as e:
                record.state = 'error'
                record.error_message = f"Error inesperado enviando a N8N: {e}"

    def action_download_and_process(self):
        """Compat: si alguien llama este botón, reenvía a n8n (fetch-only)."""
        self.action_upload_to_n8n()

    def action_reset_to_draft(self):
        self.write({
            'state': 'draft',
            'error_message': False,
            'processed_text': False,
            'extracted_presentacion': False,
            'extracted_docencia': False,
            'extracted_proyectos': False,
            'extracted_publicaciones': False
        })

    def action_apply_extracted_data(self):
        for record in self:
            if record.state != 'processed':
                raise UserError(_('El documento debe estar procesado para aplicar los datos'))

            update_vals = {}

            # Secciones principales
            if record.extracted_presentacion:
                update_vals['x_presentacion'] = record.extracted_presentacion
            if record.extracted_docencia:
                update_vals['x_docencia_periodo'] = record.extracted_docencia
            if record.extracted_proyectos:
                update_vals['x_proyectos'] = record.extracted_proyectos
            if record.extracted_publicaciones:
                update_vals['x_publicaciones'] = record.extracted_publicaciones

            # Campos adicionales
            if record.extracted_telefono:
                update_vals['phone'] = record.extracted_telefono
            if record.extracted_email_personal:
                update_vals['x_email_personal'] = record.extracted_email_personal
            if record.extracted_titulo_principal:
                update_vals['x_titulo_principal'] = record.extracted_titulo_principal
            if record.extracted_anos_experiencia:
                update_vals['x_anos_experiencia'] = record.extracted_anos_experiencia
            if record.extracted_orcid:
                update_vals['x_orcid'] = record.extracted_orcid
            if record.extracted_oficina:
                update_vals['x_oficina'] = record.extracted_oficina
            if record.extracted_idiomas:
                update_vals['x_idiomas'] = record.extracted_idiomas
            if record.extracted_total_publicaciones:
                update_vals['x_total_publicaciones'] = record.extracted_total_publicaciones
            if record.extracted_total_proyectos:
                update_vals['x_total_proyectos'] = record.extracted_total_proyectos

            # Detallados
            if record.extracted_titulos_academicos:
                update_vals['x_titulos_academicos'] = record.extracted_titulos_academicos
            if record.extracted_experiencia_laboral:
                update_vals['x_experiencia_laboral'] = record.extracted_experiencia_laboral

            if record.extracted_capacitaciones:
                update_vals['x_capacitaciones'] = record.extracted_capacitaciones
            if record.extracted_docencia_detalle:
                update_vals['x_formacion_continua'] = record.extracted_docencia_detalle
            if record.extracted_distinciones:
                update_vals['x_distinciones'] = record.extracted_distinciones

            # Reutilización
            if record.extracted_proyectos:
                update_vals['x_participacion_proyectos'] = record.extracted_proyectos
            if record.extracted_publicaciones:
                update_vals['x_publicaciones_detalle'] = record.extracted_publicaciones

            if not update_vals:
                raise UserError(_('No hay datos extraídos para aplicar'))

            # Evitar fallos si algún campo x_ no existe en hr.employee
            employee = record.employee_id
            to_write = {k: v for k, v in update_vals.items() if k in employee._fields}
            missing = [k for k in update_vals if k not in employee._fields]
            if missing:
                _logger.warning("Campos destino inexistentes en hr.employee: %s", ", ".join(missing))
            if to_write:
                employee.write(to_write)
            else:
                raise UserError(_('No hay campos destino disponibles en hr.employee para escribir.'))


    def action_test_n8n_connection(self):
        """Prueba conectividad usando GET y fallback POST si webhook no acepta GET."""
        import requests
        for record in self:
            config = self.env['cv.config'].search([], limit=1, order='id desc')
            effective_webhook = config._get_effective_webhook() if config else record.n8n_webhook_url
            if not effective_webhook:
                raise UserError(_('URL de webhook N8N no configurada'))
            try:
                resp = requests.get(effective_webhook, timeout=10)
                if 200 <= resp.status_code < 300:
                    msg = f"Conexión exitosa (GET {resp.status_code})"
                    level = 'success'
                elif resp.status_code == 404 and 'not registered for get' in (resp.text or '').lower():
                    payload = {"test": True, "method": "fallback_post", "timestamp": fields.Datetime.now().isoformat()}
                    post_resp = requests.post(effective_webhook, json=payload, timeout=10)
                    if 200 <= post_resp.status_code < 300:
                        msg = f"Conexión exitosa vía POST (HTTP {post_resp.status_code})"
                        level = 'success'
                    else:
                        msg = f"Fallo POST HTTP {post_resp.status_code}: {post_resp.text[:140] or 'Sin cuerpo'}"
                        level = 'danger'
                else:
                    msg = f"Fallo HTTP {resp.status_code}: {resp.text[:140] or 'Sin cuerpo'}"
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
                raise UserError(_('Timeout: el endpoint no respondió.'))
            except requests.exceptions.ConnectionError as e:
                raise UserError(_('Error de conexión: %s') % e)
            except Exception as e:
                raise UserError(_('Error inesperado: %s') % e)

# -----------------------------------------------------------
# HR Employee – acciones de alto nivel
# -----------------------------------------------------------
class HrEmployeeCV(models.Model):
    _inherit = 'hr.employee'

    cv_document_ids = fields.One2many('cv.document', 'employee_id', string='Documentos CV')
    cv_document_count = fields.Integer(string='Cantidad de CVs', compute='_compute_cv_document_count')

    x_email_personal = fields.Char(string='Email Personal')
    x_titulo_principal = fields.Char(string='Título Principal')
    x_anos_experiencia = fields.Integer(string='Años de Experiencia')
    x_orcid = fields.Char(string='ORCID')
    x_oficina = fields.Char(string='Oficina')
    x_idiomas = fields.Text(string='Idiomas')
    x_total_publicaciones = fields.Integer(string='Total Publicaciones')
    x_total_proyectos = fields.Integer(string='Total Proyectos')

    @api.depends('cv_document_ids')
    def _compute_cv_document_count(self):
        for employee in self:
            employee.cv_document_count = len(employee.cv_document_ids)

    def action_view_cv_documents(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'CVs de {self.name}',
            'res_model': 'cv.document',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id}
        }

    def action_create_cv_document(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Nuevo CV para {self.name}',
            'res_model': 'cv.document',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_employee_id': self.id}
        }

    def action_download_cv_auto(self):
        """Procesar CV vía n8n (descarga en n8n para saltar SSL roto)."""
        self.ensure_one()
        if not self.identification_id:
            raise UserError(_('El empleado debe tener una cédula para procesar el CV'))

        existing_cv = self.env['cv.document'].search([('employee_id', '=', self.id)], limit=1)
        if existing_cv:
            existing_cv.action_reset_to_draft()
            existing_cv.state = 'uploaded'       # se envía a n8n
            existing_cv.auto_downloaded = False  # descargará n8n
            existing_cv.action_upload_to_n8n()
            res_id = existing_cv.id
        else:
            cv_doc = self.env['cv.document'].create({
                'employee_id': self.id,
                'name': f'CV - {self.name}',
                # placeholder mínimo (no se usará, n8n descarga)
                'cv_file': base64.b64encode(b'dummy'),
                'cv_filename': f'cv_{self.identification_id}.pdf',
            })
            cv_doc.state = 'uploaded'
            cv_doc.auto_downloaded = False
            cv_doc.action_upload_to_n8n()
            res_id = cv_doc.id

        return {
            'type': 'ir.actions.act_window',
            'name': f'CV procesado vía n8n - {self.name}',
            'res_model': 'cv.document',
            'res_id': res_id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_test_n8n_connection(self):
        """Prueba conectividad (GET + fallback POST) usando URL efectiva del último cv.config."""
        import requests
        for record in self:
            config = self.env['cv.config'].search([], limit=1, order='id desc')
            url = config._get_effective_webhook() if config else False
            if not url:
                raise UserError(_('Configura primero un webhook en cv.config'))
            try:
                resp = requests.get(url, timeout=10)
                if 200 <= resp.status_code < 300:
                    msg = f"Conexión exitosa (GET {resp.status_code})"
                    level = 'success'
                elif resp.status_code == 404 and 'not registered for get' in (resp.text or '').lower():
                    payload = {"test": True, "method": "fallback_post", "timestamp": fields.Datetime.now().isoformat()}
                    post_resp = requests.post(url, json=payload, timeout=10)
                    if 200 <= post_resp.status_code < 300:
                        msg = f"Conexión exitosa vía POST (HTTP {post_resp.status_code})"
                        level = 'success'
                    else:
                        msg = f"Fallo POST HTTP {post_resp.status_code}: {post_resp.text[:140] or 'Sin cuerpo'}"
                        level = 'danger'
                else:
                    msg = f"Fallo HTTP {resp.status_code}: {resp.text[:140] or 'Sin cuerpo'}"
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
                raise UserError(_('Timeout: el endpoint no respondió.'))
            except requests.exceptions.ConnectionError as e:
                raise UserError(_('Error de conexión: %s') % e)
            except Exception as e:
                raise UserError(_('Error inesperado: %s') % e)

# -----------------------------------------------------------
# Configuración (Modelo base)
# -----------------------------------------------------------
class CvConfig(models.Model):
    _name = 'cv.config'
    _description = 'Configuración CV Importer'
    _rec_name = 'id'

    n8n_webhook_url_prod = fields.Char(
        string='Webhook Producción',
        help='Webhook principal de n8n para procesamiento real.'
    )
    n8n_webhook_url_test = fields.Char(
        string='Webhook Pruebas',
        help='Webhook alterno de n8n para pruebas (no producción).'
    )
    environment = fields.Selection(
        [('prod', 'Producción'), ('test', 'Pruebas')],
        string='Entorno Activo',
        default='prod',
        help='Selecciona qué URL usar para envíos y pruebas.'
    )
    n8n_api_key = fields.Char(string='API Key N8N')
    ngrok_url = fields.Char(string='URL Ngrok',
                            help='URL de ngrok para callbacks cuando Odoo está en localhost. '
                                 'Ej: https://abc123.ngrok-free.app')
    local_development = fields.Boolean(string='Modo Desarrollo Local', default=True)

    # Campo legacy (mantener). Se seguirá usando si no se configura producción.
    n8n_webhook_url = fields.Char(
        string='(Legacy) Webhook N8N',
        help='Usado si no se define Webhook Producción.'
    )

    def _get_effective_webhook(self):
        """Devuelve el webhook según entorno. Producción > legacy si vacío."""
        self.ensure_one()
        if self.environment == 'test' and self.n8n_webhook_url_test:
            return self.n8n_webhook_url_test
        return self.n8n_webhook_url_prod or self.n8n_webhook_url

    def action_test_n8n(self):
        """Prueba POST al webhook efectivo. Éxito solo 2xx."""
        import requests
        for rec in self:
            url = rec._get_effective_webhook()
            if not url:
                raise UserError(_('Configura un webhook (producción o test).'))
            payload = {
                'test': True,
                'entorno': rec.environment,
                'timestamp': fields.Datetime.now().isoformat()
            }
            try:
                r = requests.post(url, json=payload, timeout=10)
                ok = 200 <= r.status_code < 300
                if ok:
                    msg = f"OK HTTP {r.status_code}"
                else:
                    msg = f"Fallo HTTP {r.status_code}: {r.text[:160] or 'Sin cuerpo'}"
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': f'Test N8N ({rec.environment})',
                        'message': msg,
                        'type': 'success' if ok else 'danger',
                        'sticky': not ok,
                    }
                }
            except requests.exceptions.Timeout:
                raise UserError(_('Timeout al conectar con el webhook.'))
            except requests.exceptions.ConnectionError as e:
                raise UserError(_('Error de conexión: %s') % e)
            except Exception as e:
                raise UserError(_('Error inesperado: %s') % e)

    def action_init_cv_importer_params(self):
        ICP = self.env['ir.config_parameter'].sudo()
        created, updated = [], []
        defaults = {
            'cv_importer.allow_insecure_ssl': 'false',
            'cv_importer.insecure_hosts': '',
            'cv_importer.hojavida_pinned_sha256': '',
            'cv_importer.n8n_verify_ssl': 'true',
        }
        for k, v in defaults.items():
            current = ICP.get_param(k, default=None)
            if current in (None, False, ''):
                ICP.set_param(k, v)
                created.append(f"{k}={v}")
            else:
                updated.append(f"{k}={current}")

        msg = []
        if created:
            msg.append("Creados:\n- " + "\n- ".join(created))
        if updated:
            msg.append("Existentes:\n- " + "\n- ".join(updated))
        if not msg:
            msg.append("Sin cambios")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Parámetros cv_importer',
                'message': "\n\n".join(msg) + "\n\nAjusta valores en Ajustes → Técnico → Parámetros del sistema.",
                'type': 'success',
                'sticky': False,
            }
        }

    def _register_hook(self):
        res = super()._register_hook()
        try:
            ICP = self.env['ir.config_parameter'].sudo()
            defaults = {
                'cv_importer.allow_insecure_ssl': 'false',
                'cv_importer.insecure_hosts': '',
                'cv_importer.hojavida_pinned_sha256': '',
                'cv_importer.n8n_verify_ssl': 'true',
            }
            for k, v in defaults.items():
                current = ICP.get_param(k, default=None)
                if current in (None, False, ''):
                    ICP.set_param(k, v)
                    _logger.info(f"cv_importer: _register_hook creó {k}={v}")
        except Exception as e:
            _logger.warning(f"No se pudieron inicializar parámetros cv_importer: {e}")
        return res
