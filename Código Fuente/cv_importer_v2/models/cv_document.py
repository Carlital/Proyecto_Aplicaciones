# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
import base64
import requests
import json
import urllib3
from urllib.parse import urlparse
import socket
import ssl
import traceback
import io
import time
import os
from pathlib import Path
import tempfile
import uuid
from datetime import datetime, timedelta
import hashlib

# Helpers locales para manejo de paths (reemplazan utils.path_utils)
def _ensure_windows_path(p: str) -> str:
    # Normaliza separadores y quita redundancias
    return os.path.normpath(p)

def _ensure_dir_exists(file_path: str) -> str:
    # Crea la carpeta contenedora si no existe y devuelve el mismo path
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    return file_path

def _get_temp_path(env) -> Path:
    # Carpeta temporal por base de datos para aislar archivos
    db = getattr(getattr(env, 'cr', None), 'dbname', None) or 'default'
    base = Path(tempfile.gettempdir()) / 'odoo_cv_importer' / db
    base.mkdir(parents=True, exist_ok=True)
    return base

# Deshabilitar warnings SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configurar SSL para permitir legacy renegotiation
try:
    # Configurar OpenSSL para permitir legacy renegotiation
    ssl._create_default_https_context = ssl._create_unverified_context
    
    # Configurar variables de entorno para OpenSSL legacy
    os.environ['OPENSSL_CONF'] = '/dev/null'  # Evitar configuración restrictiva
    os.environ['PYTHONHTTPSVERIFY'] = '0'
    os.environ['REQUESTS_CA_BUNDLE'] = ''
    os.environ['CURL_CA_BUNDLE'] = ''
    
    # Forzar configuración SSL legacy a nivel de Python
    import ssl
    # Crear contexto SSL con configuración legacy forzada
    _original_create_default_context = ssl.create_default_context
    
    def _create_legacy_ssl_context(*args, **kwargs):
        context = _original_create_default_context(*args, **kwargs)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        # Configurar opciones SSL legacy
        context.options |= ssl.OP_LEGACY_SERVER_CONNECT if hasattr(ssl, 'OP_LEGACY_SERVER_CONNECT') else 0
        context.options |= ssl.OP_ALLOW_UNSAFE_LEGACY_RENEGOTIATION if hasattr(ssl, 'OP_ALLOW_UNSAFE_LEGACY_RENEGOTIATION') else 0
        try:
            context.set_ciphers('DEFAULT@SECLEVEL=0')
        except:
            try:
                context.set_ciphers('DEFAULT@SECLEVEL=1')
            except:
                context.set_ciphers('DEFAULT')
        
        # Configurar protocolo mínimo para compatibilidad legacy
        try:
            context.minimum_version = ssl.TLSVersion.TLSv1
        except:
            pass
        
        return context
    
    # Reemplazar función por defecto
    ssl.create_default_context = _create_legacy_ssl_context
    
    # Crear también adaptador HTTPs personalizado para requests
    from urllib3.util.ssl_ import create_urllib3_context
    from urllib3.poolmanager import PoolManager
    from requests.adapters import HTTPAdapter
    
    class LegacySSLAdapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            ctx = create_urllib3_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT if hasattr(ssl, 'OP_LEGACY_SERVER_CONNECT') else 0
            ctx.options |= ssl.OP_ALLOW_UNSAFE_LEGACY_RENEGOTIATION if hasattr(ssl, 'OP_ALLOW_UNSAFE_LEGACY_RENEGOTIATION') else 0
            try:
                ctx.set_ciphers('DEFAULT@SECLEVEL=0')
            except:
                try:
                    ctx.set_ciphers('DEFAULT@SECLEVEL=1') 
                except:
                    ctx.set_ciphers('DEFAULT')
            try:
                ctx.minimum_version = ssl.TLSVersion.TLSv1
            except:
                pass
            
            kwargs['ssl_context'] = ctx
            return super().init_poolmanager(*args, **kwargs)
    
    # Crear session global con adaptador SSL personalizado
    global_session = requests.Session()
    global_session.mount('https://', LegacySSLAdapter())
    global_session.verify = False

    # NEW: Restaurar contexto SSL SEGURO por defecto; usar legacy solo por-URL
    try:
        ssl.create_default_context = _original_create_default_context
        ssl._create_default_https_context = ssl.create_default_context
        # Quitar variables de entorno que desactivan verificación global
        for var in ('PYTHONHTTPSVERIFY', 'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE', 'OPENSSL_CONF'):
            os.environ.pop(var, None)
    except Exception:
        pass

except Exception as e:
    print(f"Error configurando SSL legacy: {e}")
    global_session = requests.Session()
    global_session.verify = False

_logger = logging.getLogger(__name__)

class CvDocument(models.Model):
    _name = 'cv.document'
    _description = 'Documento CV para procesamiento'
    _order = 'create_date desc'

    name = fields.Char(string='Nombre del Documento', required=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    cedula = fields.Char(string='Cédula', related='employee_id.identification_id', store=True)
    cv_file = fields.Binary(string='Archivo PDF', required=False)
    cv_filename = fields.Char(string='Nombre del Archivo')
    cv_attachment_id = fields.Many2one('ir.attachment', string='Adjunto CV', readonly=True, help='Adjunto PDF del CV almacenado en Odoo')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('uploaded', 'Subido'),
        ('processing', 'Procesando'),
        ('processed', 'Procesado'),
        ('error', 'Error')
    ], string='Estado', default='draft')
    # Seguimiento N8N
    n8n_job_id = fields.Char(string='Job ID N8N', index=True)
    n8n_status = fields.Char(string='Estado N8N', help='Último estado reportado por n8n')
    n8n_last_callback = fields.Datetime(string='Último callback N8N')

    # NUEVO: Info de lote para secuencial (no altera tu lógica actual)
    batch_token = fields.Char(string='Token de Lote', index=True, help='Identificador de lote (opcional)')
    batch_order = fields.Integer(string='Orden en Lote', default=0, index=True, help='Orden relativo en el lote (opcional)')

    n8n_webhook_url = fields.Char(string='URL Webhook N8N', default=lambda self: self.env['ir.config_parameter'].sudo().get_param('cv_importer.n8n_webhook_url', 'https://n8n.pruebasbidata.site/webhook/process-cv'))
    processed_text = fields.Text(string='Texto Procesado')
    error_message = fields.Text(string='Mensaje de Error')
    
    cv_download_url = fields.Char(string='URL de Descarga CV', compute='_compute_cv_download_url', store=True)
    auto_downloaded = fields.Boolean(string='Descargado Automáticamente', default=False)
    
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
    
    # Campos adicionales detallados extraídos del CV
    extracted_titulos_academicos = fields.Text(string='Títulos Académicos Extraídos')
    extracted_experiencia_laboral = fields.Text(string='Experiencia Laboral Extraída')
    extracted_capacitaciones = fields.Text(string='Capacitaciones Extraídas')
    extracted_docencia_detalle = fields.Text(string='Docencia Detallada Extraída')
    extracted_distinciones = fields.Text(string='Logros y Distinciones Extraídos')
    
    @api.depends('employee_id', 'employee_id.identification_id')
    def _compute_cv_download_url(self):
        """Generar URL de descarga basada en la cédula del empleado"""
        for record in self:
            if record.employee_id and record.employee_id.identification_id:
                cedula = record.employee_id.identification_id.zfill(10)
                record.cv_download_url = f"https://hojavida.espoch.edu.ec/cv/{cedula}"
            else:
                record.cv_download_url = False
    
    @api.model
    def create(self, vals):
        if 'name' not in vals or not vals['name']:
            if 'employee_id' in vals:
                employee = self.env['hr.employee'].browse(vals['employee_id'])
                vals['name'] = f"CV - {employee.name}"
        return super().create(vals)

    def action_test_connection(self):
        """Probar conexión con el servidor institucional"""
        for record in self:
            if not record.cv_download_url:
                raise UserError(_('No se puede generar URL de descarga. Verifica que el empleado tenga cédula.'))
            
            try:
                # Probar resolución DNS
                parsed_url = urlparse(record.cv_download_url)
                host = parsed_url.hostname
                port = parsed_url.port or (443 if parsed_url.scheme == 'https' else 80)
                
                _logger.info(f"Probando conexión con {host}:{port}")
                
                # Test DNS resolution
                try:
                    socket.gethostbyname(host)
                    _logger.info(f"DNS resuelto correctamente para {host}")
                except socket.gaierror as e:
                    raise UserError(_(f"Error de DNS: No se puede resolver {host}. Detalles: {str(e)}"))
                
                # Test TCP connection
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(10)
                try:
                    result = sock.connect_ex((host, port))
                    if result == 0:
                        _logger.info(f"Conexión TCP exitosa con {host}:{port}")
                    else:
                        raise UserError(_(f"No se puede conectar con {host}:{port}. Código de error: {result}"))
                finally:
                    sock.close()
                
                # Test HTTP HEAD request con SSL personalizado
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                # Reemplazar sesión y verify según política SSL
                verify = self._should_verify_ssl(record.cv_download_url)
                session = self._get_session_for_url(record.cv_download_url)
                session.headers.update(headers)

                # Si no verificas SSL, aplica pinning si está configurado
                if not verify:
                    self._assert_pinned_cert(record.cv_download_url, 'cv_importer.hojavida_pinned_sha256')

                response = session.head(
                    record.cv_download_url,
                    verify=verify,
                    timeout=15,
                    allow_redirects=True
                )

                # NEW: mostrar estado de pinning
                pin = (self.env['ir.config_parameter'].sudo().get_param('cv_importer.hojavida_pinned_sha256', '') or '').strip()

                message = f"""
                Prueba de conexión exitosa:
                - DNS: ✓ Resuelto
                - TCP: ✓ Conectado
                - HTTP: {response.status_code} ({requests.status_codes._codes.get(response.status_code, ['Unknown'])[0]})
                - Content-Type: {response.headers.get('content-type', 'No especificado')}
                - Content-Length: {response.headers.get('content-length', 'No especificado')}
                - URL Final: {response.url}
                - SSL Verify: {'ON' if verify else 'OFF'}
                - Pinning: {'ON' if (not verify and bool(pin)) else 'OFF'}
                """
                
                record.error_message = message
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Prueba de Conexión',
                        'message': message,
                        'type': 'success',
                        'sticky': True
                    }
                }
                
            except requests.exceptions.RequestException as e:
                raise UserError(_(f"Error de conexión HTTP: {str(e)}"))
            except Exception as e:
                raise UserError(_(f"Error inesperado en prueba de conexión: {str(e)}"))

    def _create_ssl_session(self):
        """Crear sesión HTTP con configuración SSL legacy"""
        try:
            # Usar la sesión global que ya tiene el adaptador SSL configurado
            session = requests.Session()
            session.mount('https://', LegacySSLAdapter())
            session.verify = False
            
            return session
            
        except Exception as e:
            _logger.warning(f"No se pudo crear sesión SSL personalizada: {str(e)}")
            # Fallback a sesión normal sin verificación SSL
            fallback_session = requests.Session()
            fallback_session.verify = False
            return fallback_session

    # === Helpers de seguridad SSL ===
    def _extract_host_port(self, url):
        parsed = urlparse(url or '')
        host = parsed.hostname or ''
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        return host.lower(), port

    def _ensure_ssl_params(self):
        """Crea (si no existen) los parámetros de sistema usados por la política SSL."""
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
        """Decide si verificar SSL para una URL dada. Por defecto, verificar."""
        self._ensure_ssl_params()  # <-- asegura que los params existan
        ICP = self.env['ir.config_parameter'].sudo()
        allow_insecure = (ICP.get_param('cv_importer.allow_insecure_ssl', 'false') or '').lower() == 'true'
        insecure_hosts_param = (ICP.get_param('cv_importer.insecure_hosts', '') or '').strip()
        insecure_hosts = [h.strip().lower() for h in insecure_hosts_param.split(',') if h.strip()]
        host, _ = self._extract_host_port(url)
        # Verificar siempre salvo que esté permitido y listado explícitamente
        return not (allow_insecure and host in insecure_hosts)

    def _use_secure_ssl_context(self):
        """Restaura el contexto SSL seguro por defecto para peticiones verificadas."""
        try:
            ssl.create_default_context = _original_create_default_context  # type: ignore[name-defined]
            ssl._create_default_https_context = ssl.create_default_context
        except Exception:
            pass

    def _use_insecure_ssl_context(self):
        """Activa contexto SSL legacy solo cuando se requiera compatibilidad."""
        try:
            ssl.create_default_context = _create_legacy_ssl_context  # type: ignore[name-defined]
            ssl._create_default_https_context = ssl._create_unverified_context
        except Exception:
            pass

    def _get_session_for_url(self, url):
        """Crea una sesión adecuada según verify para la URL."""
        verify = self._should_verify_ssl(url)
        if verify:
            self._use_secure_ssl_context()
            s = requests.Session()
            s.verify = True
            return s
        # Inseguro solo si está explícitamente permitido
        self._use_insecure_ssl_context()
        s = requests.Session()
        s.mount('https://', LegacySSLAdapter())  # usa adapter legacy solo en modo inseguro
        s.verify = False
        _logger.warning(f"SSL verify desactivado para {url}. Considera habilitar pinning (cv_importer.hojavida_pinned_sha256).")
        return s

    def _get_server_cert_sha256(self, host, port=443):
        """Obtiene huella SHA256 del certificado del servidor (DER)."""
        pem = ssl.get_server_certificate((host, port))
        der = ssl.PEM_cert_to_DER_cert(pem)
        return hashlib.sha256(der).hexdigest()

    def _assert_pinned_cert(self, url, conf_key):
        """Si hay pin configurado, compara huella y aborta si no coincide."""
        pin = (self.env['ir.config_parameter'].sudo().get_param(conf_key, '') or '').replace(':', '').strip().lower()
        if not pin:
            return
        host, port = self._extract_host_port(url)
        try:
            current = self._get_server_cert_sha256(host, port)
        except Exception as e:
            raise UserError(_(f"No se pudo obtener el certificado de {host}:{port} para pinning: {e}"))
        if current != pin:
            raise UserError(_(f"Pinning SSL falló para {host}. Esperado {pin}, obtenido {current}. Posible ataque MITM."))

    # === Fin helpers SSL ===

    def action_download_cv_from_url(self):
        """Descargar CV desde la URL automática basada en cédula"""
        for record in self:
            if not record.cv_download_url:
                raise UserError(_('No se puede generar URL de descarga. Verifica que el empleado tenga cédula.'))
            
            try:
                record.state = 'processing'
                record.error_message = False
                
                _logger.info(f"Descargando CV desde: {record.cv_download_url}")
                
                # Configuración de headers para simular navegador
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'application/pdf,application/x-pdf,application/octet-stream,*/*',
                    'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Cache-Control': 'max-age=0'
                }
                # Sesión y verify según política SSL
                verify = self._should_verify_ssl(record.cv_download_url)
                session = self._get_session_for_url(record.cv_download_url)
                session.headers.update(headers)
                if not verify:
                    self._assert_pinned_cert(record.cv_download_url, 'cv_importer.hojavida_pinned_sha256')

                # Múltiples intentos de descarga
                max_attempts = 3
                for attempt in range(max_attempts):
                    try:
                        _logger.info(f"Intento {attempt + 1}/{max_attempts} para {record.employee_id.name}")
                        
                        response = session.get(
                            record.cv_download_url,
                            verify=verify,
                            timeout=45,
                            allow_redirects=True,
                            stream=True
                        )
                        
                        # Si llegamos aquí, la descarga fue exitosa
                        break
                        
                    except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
                        if attempt == max_attempts - 1:
                            # Último intento fallido
                            raise e
                        
                        _logger.warning(f"Error SSL/conexión en intento {attempt + 1} para {record.employee_id.name}: {str(e)}")
                        
                        # Esperar un poco antes del siguiente intento
                        import time
                        time.sleep(2)
                
                _logger.info(f"Respuesta HTTP: {response.status_code} para {record.employee_id.name}")
                _logger.info(f"Content-Type: {response.headers.get('content-type', 'No especificado')}")
                
                if response.status_code == 200:
                    # Leer el contenido
                    content = response.content
                    content_type = response.headers.get('content-type', '').lower()
                    
                    _logger.info(f"Tamaño del contenido: {len(content)} bytes")
                    _logger.info(f"Primeros 100 bytes: {content[:100]}")
                    
                    # Verificar que el contenido sea un PDF
                    if (content.startswith(b'%PDF') or 
                        'pdf' in content_type or 
                        (len(content) > 1000 and b'PDF' in content[:1000])):
                        
                        # Guardar el PDF - asegurar que sea string base64
                        try:
                            pdf_base64 = base64.b64encode(content).decode('utf-8')
                            record.cv_file = pdf_base64
                            record.cv_filename = f"cv_{record.employee_id.identification_id}.pdf"
                            record.auto_downloaded = True
                            record.state = 'uploaded'
                            
                            _logger.info(f"CV guardado exitosamente:")
                            _logger.info(f"  Tamaño original: {len(content)} bytes")
                            _logger.info(f"  Tamaño base64: {len(pdf_base64)} caracteres")
                            _logger.info(f"  Tipo guardado: {type(record.cv_file)}")
                            
                            # Verificar que se guardó correctamente
                            test_decode = base64.b64decode(record.cv_file)
                            if test_decode.startswith(b'%PDF'):
                                _logger.info("✅ Archivo guardado y validado correctamente")
                            else:
                                _logger.warning("⚠️ Advertencia: El archivo guardado podría tener problemas")
                            
                        except Exception as save_error:
                            _logger.error(f"❌ Error guardando PDF: {str(save_error)}")
                            record.state = 'error'
                            record.error_message = f"Error guardando PDF: {str(save_error)}"
                            return
                        
                        _logger.info(f"CV descargado exitosamente para {record.employee_id.name} - {len(content)} bytes")
                        
                        # Procesar automáticamente
                        record.action_upload_to_n8n()
                        
                    else:
                        # Si no es PDF, revisar el contenido
                        content_preview = content[:2000].decode('utf-8', errors='ignore')
                        
                        if any(keyword in content_preview.lower() for keyword in ['not found', '404', 'error', 'no existe']):
                            record.state = 'error'
                            record.error_message = f"CV no encontrado en el servidor institucional para la cédula {record.employee_id.identification_id}. El empleado podría no tener CV registrado."
                            _logger.warning(f"CV no encontrado para {record.employee_id.name}")
                        elif 'html' in content_preview.lower() or '<' in content_preview:
                            record.state = 'error'
                            record.error_message = f"La URL devolvió una página web en lugar de un PDF. Posible CV no disponible o página de error."
                            _logger.warning(f"HTML recibido en lugar de PDF para {record.employee_id.name}")
                        else:
                            record.state = 'error'
                            record.error_message = f"Contenido descargado no es un PDF válido. Content-Type: {content_type}, Tamaño: {len(content)} bytes"
                            _logger.error(f"Contenido no es PDF para {record.employee_id.name}")
                            
                elif response.status_code == 404:
                    record.state = 'error'
                    record.error_message = f"CV no encontrado (Error 404). El empleado con cédula {record.employee_id.identification_id} no tiene CV registrado en el sistema institucional."
                    _logger.warning(f"CV no encontrado (404) para {record.employee_id.name}")
                    
                elif response.status_code in [403, 401]:
                    record.state = 'error'
                    record.error_message = f"Acceso denegado al CV (Error {response.status_code}). Posible problema de permisos en el servidor institucional."
                    _logger.warning(f"Acceso denegado ({response.status_code}) para {record.employee_id.name}")
                    
                else:
                    record.state = 'error'
                    record.error_message = f"Error descargando CV: HTTP {response.status_code}. Servidor institucional no disponible temporalmente."
                    _logger.error(f"Error HTTP {response.status_code} descargando CV para {record.employee_id.name}")
                
            except requests.exceptions.Timeout:
                record.state = 'error'
                record.error_message = "Timeout al descargar CV. El servidor institucional no respondió en el tiempo esperado (45 segundos)."
                _logger.error(f"Timeout descargando CV para {record.employee_id.name}")
                
            except requests.exceptions.ConnectionError as e:
                record.state = 'error'
                record.error_message = f"Error de conexión al descargar CV. Verifique la conectividad con hojavida.espoch.edu.ec. Detalles: {str(e)}"
                _logger.error(f"Error de conexión descargando CV para {record.employee_id.name}: {str(e)}")
                
            except requests.exceptions.SSLError as e:
                record.state = 'error'
                record.error_message = f"Error de certificado SSL. El servidor institucional tiene problemas de certificados. Detalles: {str(e)}"
                _logger.error(f"Error SSL descargando CV para {record.employee_id.name}: {str(e)}")
                
            except Exception as e:
                record.state = 'error'
                record.error_message = f"Error inesperado al descargar CV: {str(e)}"
                _logger.error(f"Error inesperado descargando CV para {record.employee_id.name}: {str(e)}")

    def _prepare_file_path(self, filename):
        """Prepare safe file path for operations"""
        temp_dir = _get_temp_path(self.env)
        safe_name = os.path.basename(filename) if filename else f"tmp_{int(time.time())}.bin"
        file_path = str(temp_dir / safe_name)
        return _ensure_dir_exists(_ensure_windows_path(file_path))

    def process_pdf(self, pdf_data, filename):
        """Process PDF with proper path handling"""
        try:
            file_path = self._prepare_file_path(filename)
            _logger.info(f"Processing PDF at: {file_path}")
            
            with open(file_path, 'wb') as f:
                f.write(pdf_data)
            
            # ...existing processing code...
            
        except Exception as e:
            _logger.error(f"Error processing PDF: {str(e)}\n{traceback.format_exc()}")
            raise
        finally:
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
            except Exception as e:
                _logger.warning(f"Error cleaning temp file: {str(e)}")

    # ----------- NUEVO: despachar el siguiente del mismo lote (opcional) ------------
    def _dispatch_next_in_batch(self):
        """Envía el siguiente documento del mismo batch_token (si existe)."""
        for rec in self.sudo():
            if not rec.batch_token:
                continue
            dom = [
                ('batch_token', '=', rec.batch_token),
                ('state', 'in', ['draft', 'uploaded']),
                ('id', '!=', rec.id),
            ]
            order = 'id'
            if rec.batch_order:
                dom.append(('batch_order', '>', rec.batch_order))
                order = 'batch_order,id'
            nxt = self.search(dom, order=order, limit=1)
            if not nxt:
                _logger.info(f"🧵 Lote {rec.batch_token}: no hay siguiente pendiente.")
                continue
            _logger.info(f"🧵 Lote {rec.batch_token}: despachando siguiente id={nxt.id} emp={nxt.employee_id.name} (state={nxt.state})")
            try:
                nxt.action_upload_to_n8n()
            except Exception as e:
                nxt.write({'state': 'error', 'error_message': f'Error al despachar siguiente del lote: {e}'})
                _logger.warning(f"⚠️ Error despachando siguiente del lote {rec.batch_token}: {e}")
    # -------------------------------------------------------------------------------

    def action_upload_to_n8n(self):
        """Subir CV a N8N para procesamiento"""
        _logger.info("🚀 INICIANDO action_upload_to_n8n")
        for record in self:
            _logger.info(f"📋 Procesando record: {record.id} - {record.employee_id.name}")


            # Siempre delegar descarga a n8n (no enviar pdf_data)
            if True:
                _logger.warning("No hay PDF local; se enviarán metadatos para que N8N descargue usando download_url")
                # Asegura cédula y callback
                cedula = record.cedula or record.employee_id.identification_id
                if not cedula:
                    raise UserError(_('El empleado debe tener una cédula asignada'))
                base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                callback_url = f"{base_url}/cv/callback"

                # Payload mínimo (sin pdf_data)
                import uuid as _uuid
                payload = {
                    'cedula': str(cedula),
                    'employee_name': str(record.employee_id.name or ''),
                    'filename': str(record.cv_filename or f"cv_{cedula}.pdf"),
                    'odoo_callback_url': str(callback_url),
                    'download_url': str(record.cv_download_url or ''),
                    'request_id': str(_uuid.uuid4()),
                    'timestamp': str(fields.Datetime.now().isoformat()),
                    'batch_token': record.batch_token or '',
                    'batch_order': int(record.batch_order or 0),
                }

                headers = {
                    'Content-Type': 'application/json',
                    'User-Agent': 'Odoo-CV-Importer/2.0',
                    'Accept': 'application/json',
                    'Cache-Control': 'no-cache'
                }
                # Authorization Bearer si hay API key
                try:
                    api_key = record.n8n_api_key or self.env['cv.config'].search([], limit=1).n8n_api_key
                    if api_key:
                        headers['Authorization'] = f"Bearer {api_key}"
                except Exception:
                    pass

                # Respeta la política SSL de N8N
                self._ensure_ssl_params()
                verify_n8n = (self.env['ir.config_parameter'].sudo().get_param('cv_importer.n8n_verify_ssl', 'true') or '').lower() == 'true'
                response = requests.post(record.n8n_webhook_url, json=payload, headers=headers,
                                        timeout=int(self.env['ir.config_parameter'].sudo().get_param('cv_importer.timeout', '60')),
                                        verify=verify_n8n)
                if response.status_code in [200, 201]:
                    record.state = 'uploaded'
                    return
                else:
                    record.state = 'error'
                    record.error_message = f"Error en N8N: {response.status_code} - {response.text}"
                    return

            
            if not record.n8n_webhook_url:
                _logger.error("❌ URL de webhook N8N no configurada")
                raise UserError(_('URL de webhook N8N no configurada'))
            
            _logger.info("✅ Validaciones iniciales pasadas")
            try:
                _logger.info("🔄 Iniciando procesamiento de PDF...")
                if record.state not in ['uploaded', 'error']:
                    record.state = 'processing'
                record.error_message = False
                # Mantener la lógica actual: validación/limpieza del base64 y envío

                _logger.info("🔧 Preparando datos PDF...")
                # Preparar datos para N8N con validaciones mejoradas
                pdf_data = None
                
                # En Odoo, cv_file puede llegar como bytes o como string base64
                if record.cv_file:
                    try:
                        # Log para debug
                        _logger.info(f"📊 Datos del archivo:")
                        _logger.info(f"  Tipo de cv_file: {type(record.cv_file)}")
                        _logger.info(f"  Longitud cv_file: {len(str(record.cv_file))}")
                        _logger.info(f"  Primeros 50 chars: {str(record.cv_file)[:50]}")
                        
                        # Manejar diferentes tipos de datos en cv_file
                        if isinstance(record.cv_file, bytes):
                            # Si es bytes, verificar si ya son datos PDF o base64
                            if record.cv_file.startswith(b'%PDF'):
                                # Es un PDF directo en bytes, convertir a base64
                                pdf_data = base64.b64encode(record.cv_file).decode('utf-8')
                                _logger.info(f"🔄 Convertido PDF directo a base64: {len(pdf_data)} chars")
                            else:
                                # Es base64 en bytes, verificar si realmente es base64 válido
                                try:
                                    # Intentar decodificar como string primero
                                    pdf_string = record.cv_file.decode('utf-8')
                                    
                                    # Verificar que el contenido parece base64 válido
                                    import string
                                    valid_base64_chars = string.ascii_letters + string.digits + '+/='
                                    sample_check = pdf_string[:min(100, len(pdf_string))]
                                    
                                    if all(c in valid_base64_chars for c in sample_check):
                                        # Parece base64 válido, usar sin corregir padding aquí
                                        pdf_data = pdf_string.strip()
                                        
                                        _logger.info(f"🔄 Base64 detectado: {len(pdf_data)} chars")
                                        _logger.info(f"  Necesita padding: {len(pdf_data) % 4 != 0}")
                                        
                                        _logger.info(f"Usando bytes como base64 string: {len(pdf_data)} chars (padding será corregido después)")
                                        
                                        # NO VALIDAR AQUÍ - se validará después de corrección de padding global
                                        _logger.info(f"🔄 Base64 detectado, se validará después de corrección de padding")
                                    else:
                                        # No es base64 válido, tratar como PDF directo
                                        pdf_data = base64.b64encode(record.cv_file).decode('utf-8')
                                        _logger.info(f"Reinterpretado como PDF directo: {len(pdf_data)} chars")
                                        
                                except UnicodeDecodeError:
                                    # No se puede decodificar como UTF-8, debe ser PDF directo
                                    pdf_data = base64.b64encode(record.cv_file).decode('utf-8')
                                    _logger.info(f"Bytes no UTF-8, convertido como PDF: {len(pdf_data)} chars")
                        else:
                            # Ya es string, usar directamente
                            pdf_data = str(record.cv_file)
                            _logger.info(f"🔄 Usando string directo: {len(pdf_data)} chars")
                        
                        # Limpiar y corregir padding base64 ANTES de validar
                        if pdf_data:
                            _logger.info(f"📋 Procesando padding base64...")
                            _logger.info(f"  Longitud original: {len(pdf_data)}")
                            
                            pdf_data = pdf_data.strip()
                            _logger.info(f"  Longitud después de strip: {len(pdf_data)}")
                            
                            # Verificar que solo contiene caracteres base64 válidos
                            import string
                            valid_chars = string.ascii_letters + string.digits + '+/='
                            invalid_chars = [c for c in pdf_data if c not in valid_chars]
                            if invalid_chars:
                                _logger.error(f"❌ Caracteres inválidos en base64: {set(invalid_chars)}")
                                # Limpiar caracteres inválidos
                                pdf_data = ''.join(c for c in pdf_data if c in valid_chars)
                                _logger.info(f"✅ Caracteres inválidos removidos, nueva longitud: {len(pdf_data)}")
                            
                            # Agregar padding si es necesario para que sea múltiplo de 4
                            missing_padding = len(pdf_data) % 4
                            if missing_padding:
                                padding_needed = 4 - missing_padding
                                pdf_data += '=' * padding_needed
                                _logger.info(f"✅ Agregado padding base64: {padding_needed} caracteres '='")
                                _logger.info(f"  Longitud final: {len(pdf_data)}")
                            else:
                                _logger.info(f"✅ No se necesita padding, longitud es múltiplo de 4")
                        
                        # Validar que el base64 es válido decodificándolo (DESPUÉS de corregir padding)
                        try:
                            _logger.info(f"🔍 Validando base64 corregido...")
                            decoded_pdf = base64.b64decode(pdf_data)
                            _logger.info(f"✅ Base64 decodificado exitosamente: {len(decoded_pdf)} bytes")
                        except Exception as decode_error:
                            _logger.error(f"❌ Error decodificando base64 DESPUÉS de corrección: {str(decode_error)}")
                            _logger.error(f"  Longitud pdf_data: {len(pdf_data)}")
                            _logger.error(f"  Primeros 100 chars: {pdf_data[:100]}")
                            _logger.error(f"  Últimos 100 chars: {pdf_data[-100:]}")
                            _logger.error(f"  Es múltiplo de 4: {len(pdf_data) % 4 == 0}")
                            
                            # Log adicional para debug
                            import string
                            valid_chars = string.ascii_letters + string.digits + '+/='
                            invalid_chars = [c for c in pdf_data if c not in valid_chars]
                            if invalid_chars:
                                _logger.error(f"  Caracteres inválidos encontrados: {set(invalid_chars)}")
                            
                            raise UserError(_('El archivo no está en formato base64 válido después de corrección de padding'))
                        
                        # Verificar que el contenido decodificado es un PDF válido
                        if len(decoded_pdf) < 10:
                            _logger.error(f"❌ Archivo demasiado pequeño: {len(decoded_pdf)} bytes")
                            raise UserError(_('El archivo está corrupto o es demasiado pequeño'))
                        
                        # Verificar header PDF con más flexibilidad
                        header = decoded_pdf[:10]
                        _logger.info(f"📄 Header detectado: {header}")
                        
                        if not (header.startswith(b'%PDF') or b'PDF' in header[:20]):
                            # Log más detallado para debug
                            _logger.error(f"❌ VALIDACIÓN PDF FALLIDA:")
                            _logger.error(f"  Empleado: {record.employee_id.name}")
                            _logger.error(f"  Archivo descargado desde: {record.cv_download_url}")
                            _logger.error(f"  Tamaño decodificado: {len(decoded_pdf)} bytes")
                            _logger.error(f"  Header detectado (bytes): {header}")
                            _logger.error(f"  Header como string: {header.decode('latin1', errors='ignore')}")
                            _logger.error(f"  Primeros 100 bytes: {decoded_pdf[:100]}")
                            _logger.error(f"  Auto-descargado: {record.auto_downloaded}")
                            
                            # Buscar patrones comunes que indican problemas
                            content_str = decoded_pdf[:1000].decode('latin1', errors='ignore').lower()
                            if 'html' in content_str or '<html' in content_str:
                                error_detail = "El servidor devolvió HTML en lugar de PDF (posible página de error)"
                            elif '404' in content_str or 'not found' in content_str:
                                error_detail = "El CV no fue encontrado en el servidor (Error 404)"
                            elif len(decoded_pdf) < 1000:
                                error_detail = f"Archivo demasiado pequeño ({len(decoded_pdf)} bytes) - posiblemente corrupto"
                            elif decoded_pdf.startswith(b'<!DOCTYPE'):
                                error_detail = "El servidor devolvió una página web en lugar del PDF"
                            else:
                                error_detail = f"Formato de archivo no reconocido. Header: {header.decode('latin1', errors='ignore')[:20]}"
                            
                            _logger.error(f"  Diagnóstico: {error_detail}")
                            
                            raise UserError(_(f'''El archivo descargado no es un PDF válido.

🔍 DIAGNÓSTICO: {error_detail}

📋 INFORMACIÓN TÉCNICA:
• Empleado: {record.employee_id.name}
• URL fuente: {record.cv_download_url}
• Tamaño archivo: {len(decoded_pdf)} bytes
• Header detectado: {header.decode('latin1', errors='ignore')[:20]}

🔧 POSIBLES SOLUCIONES:
1. Verificar que el empleado tenga CV en el sistema institucional
2. Comprobar manualmente la URL en un navegador
3. Contactar al administrador si el problema persiste

💡 URL a verificar: {record.cv_download_url}'''))
                        
                        _logger.info(f"✅ PDF válido detectado: {len(decoded_pdf)} bytes decodificados, {len(pdf_data)} caracteres base64")
                        
                    except UserError as user_err:
                        # Capturar UserError específicos (como validación PDF)
                        _logger.error(f"❌ UserError en validación: {str(user_err)}")
                        record.state = 'error'
                        record.error_message = f"""❌ ERROR DE VALIDACIÓN

{str(user_err)}

📊 INFORMACIÓN ADICIONAL:
• Timestamp: {fields.Datetime.now()}
• Documento ID: {record.id}
• Método: Validación de archivo PDF
• Estado anterior: {record.state}

🔧 Para obtener más información técnica, revisa los logs del sistema."""
                        
                        # Re-lanzar para que el usuario vea el error
                        raise
                    except base64.binascii.Error as e:
                        # Este bloque solo debería ejecutarse si la validación final falla
                        _logger.error(f"❌ Error base64 en validación final: {str(e)}")
                        record.state = 'error'
                        record.error_message = f"""❌ ERROR DE CODIFICACIÓN BASE64 (VALIDACIÓN FINAL)

El archivo no se pudo decodificar como base64 válido incluso después de corrección de padding.

🔍 DETALLES TÉCNICOS:
• Error: {str(e)}
• Empleado: {record.employee_id.name}
• Tipo de archivo: {type(record.cv_file)}
• Longitud final: {len(pdf_data) if 'pdf_data' in locals() else 'No disponible'}

🔧 POSIBLES CAUSAS:
1. Archivo corrupto durante la descarga
2. Problema en el almacenamiento de Odoo  
3. Archivo contiene caracteres no válidos para base64

💡 SOLUCIÓN: Intenta descargar el CV nuevamente."""
                        
                        raise UserError(_('El archivo no está en formato base64 válido (validación final)'))
                    except Exception as e:
                        _logger.error(f"❌ Error procesando PDF: {str(e)}")
                        record.state = 'error'
                        record.error_message = f"""❌ ERROR PROCESANDO ARCHIVO PDF"""
                        
                        raise UserError(_(f'Error procesando el archivo PDF: {str(e)}'))
                
                _logger.info(f"📄 PDF preparado: {len(pdf_data)} caracteres base64")
                if not pdf_data:
                    _logger.error("❌ No se pudo procesar el archivo PDF")
                    raise UserError(_('No se pudo procesar el archivo PDF'))
                
                # Validar que la cédula esté presente
                cedula = record.cedula or record.employee_id.identification_id
                if not cedula:
                    raise UserError(_('El empleado debe tener una cédula asignada'))
                
                # NO PROCESAR PDF LOCALMENTE - Solo enviarlo a N8N
                _logger.info("📤 Enviando PDF directamente a N8N para procesamiento...")
                
                base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                
                # Configuración especial para desarrollo local
                if 'localhost' in base_url or '127.0.0.1' in base_url:
                    # Para desarrollo local, verificar si hay ngrok configurado
                    config = self.env['cv.config'].search([], limit=1)
                    ngrok_url = config.ngrok_url if config else ''
                    
                    # También buscar en parámetros del sistema como fallback
                    if not ngrok_url:
                        ngrok_url = self.env['ir.config_parameter'].sudo().get_param('cv_importer.ngrok_url', '')
                    
                    if ngrok_url:
                        # Limpiar URL si tiene espacios o caracteres extraños
                        ngrok_url = ngrok_url.strip()
                        if not ngrok_url.startswith('http'):
                            ngrok_url = f"https://{ngrok_url}"
                        callback_url = f"{ngrok_url}/cv/callback"
                        _logger.info(f"🔧 Usando ngrok URL configurada: {ngrok_url}")
                    else:
                        # Si no hay ngrok configurado, advertir que N8N no podrá devolver datos
                        callback_url = f"{base_url}/cv/callback"
                        _logger.warning("⚠️ Desarrollo local sin ngrok - N8N no podrá devolver resultados automáticamente")
                        _logger.warning(f"💡 Configura un túnel ngrok en: HR > CV Importer > Configuración")
                elif 'ngrok' in base_url:
                    # Ya está usando ngrok
                    callback_url = f"{base_url}/cv/callback"
                    _logger.info("🔧 Detectado ngrok en configuración")
                else:
                    # Producción normal
                    callback_url = f"{base_url}/cv/callback"
                
                payload = {
                    'cedula': str(cedula),
                    'employee_name': str(record.employee_id.name),
                    'pdf_data': str(pdf_data),  # Base64 string limpio
                    'filename': str(record.cv_filename or f"cv_{cedula}.pdf"),
                    'odoo_callback_url': str(callback_url),
                    'download_url': str(record.cv_download_url or ''),
                    'auto_downloaded': bool(record.auto_downloaded),
                    'content_length': int(len(pdf_data)),
                    'timestamp': str(fields.Datetime.now().isoformat()),
                    'odoo_version': '17.0',
                    'module_version': '2.0',
                    # Pasar datos de lote (opcional; n8n puede ignorarlos)
                    'batch_token': record.batch_token or '',
                    'batch_order': int(record.batch_order or 0),
                }
                
                # Validar que todos los valores del payload sean serializables a JSON
                try:
                    import json
                    json.dumps(payload)
                    _logger.info("✅ Payload validado - todos los valores son serializables a JSON")
                except (TypeError, ValueError) as e:
                    _logger.error(f"❌ Error: El payload contiene valores no serializables: {str(e)}")
                    # Log detallado del payload para debug
                    for key, value in payload.items():
                        _logger.error(f"  {key}: {type(value)} = {repr(value)}")
                    raise UserError(_('Error preparando datos para N8N: valores no serializables'))
                
                # LOGGING DETALLADO PARA DEBUG
                _logger.info(f"=== ENVIANDO CV A N8N ===")
                _logger.info(f"Empleado: {record.employee_id.name}")
                _logger.info(f"Cédula: {cedula} (tipo: {type(cedula)})")
                _logger.info(f"Filename: {payload['filename']}")
                _logger.info(f"PDF size: {len(pdf_data)} chars")
                _logger.info(f"Callback URL: {payload['odoo_callback_url']}")
                _logger.info(f"Webhook URL: {record.n8n_webhook_url}")
                _logger.info(f"Payload keys: {list(payload.keys())}")
                
                # Verificar que el PDF es válido antes de enviar a N8N
                try:
                    test_decode = base64.b64decode(pdf_data)
                    _logger.info(f"📋 Validación final PDF antes de envío:")
                    _logger.info(f"  PDF base64 válido: ✅")
                    _logger.info(f"  Tamaño decodificado: {len(test_decode)} bytes")
                    _logger.info(f"  Header: {test_decode[:10]}")
                    
                    # Verificar que parece ser un PDF
                    if test_decode.startswith(b'%PDF'):
                        _logger.info("  Estructura PDF válida: ✅")
                    else:
                        _logger.warning("  ⚠️ Advertencia: El archivo podría no ser un PDF válido")
                        _logger.warning(f"  Header detectado: {test_decode[:20]}")
                        
                except Exception as e:
                    _logger.error(f"❌ Error validando PDF antes de envío: {str(e)}")
                    raise UserError(_('El archivo PDF no es válido para envío a N8N'))
                
                headers = {
                    'Content-Type': 'application/json',
                    'User-Agent': 'Odoo-CV-Importer/2.0',
                    'Accept': 'application/json',
                    'Cache-Control': 'no-cache'
                }
                
                _logger.info(f"Enviando CV a N8N para empleado {record.employee_id.name}")
                
                # Log del payload (sin el PDF completo para no saturar logs)
                payload_summary = {k: v if k != 'pdf_data' else f"[BASE64_DATA:{len(v)}_chars]" for k, v in payload.items()}
                _logger.info(f"📤 Payload summary: {payload_summary}")
                
                # Verificar algunos caracteres del inicio y final del base64 para debug
                _logger.info(f"🔍 PDF Data debug:")
                _logger.info(f"  Primeros 50 chars: {payload['pdf_data'][:50]}")
                _logger.info(f"  Últimos 50 chars: {payload['pdf_data'][-50:]}")
                _logger.info(f"  Longitud total: {len(payload['pdf_data'])}")
                _logger.info(f"  Es múltiplo de 4: {len(payload['pdf_data']) % 4 == 0}")
                
                # Hacer la petición con timeout configurable
                timeout = int(self.env['ir.config_parameter'].sudo().get_param('cv_importer.timeout', '60'))
                
                # Política SSL para N8N (por defecto verificar)
                # Asegurar que el parámetro exista antes de leerlo
                self._ensure_ssl_params()
                verify_n8n = (self.env['ir.config_parameter'].sudo().get_param('cv_importer.n8n_verify_ssl', 'true') or '').lower() == 'true'
                if not verify_n8n:
                    _logger.warning(f"SSL verify desactivado para N8N: {record.n8n_webhook_url}")
                response = requests.post(
                    record.n8n_webhook_url,
                    json=payload,
                    headers=headers,
                    timeout=timeout,
                    verify=verify_n8n
                )
                
                _logger.info(f"Respuesta de N8N: {response.status_code}")
                _logger.info(f"Headers respuesta: {dict(response.headers)}")
                _logger.info(f"Contenido respuesta: {response.text}")
                
                if response.status_code in [200, 201]:
                    record.state = 'uploaded'
                    _logger.info(f"CV enviado exitosamente a N8N para {record.employee_id.name}")
                    
                    # Intentar parsear respuesta como JSON para logging adicional
                    try:
                        response_json = response.json()
                        _logger.info(f"Respuesta JSON de N8N: {response_json}")
                    except:
                        _logger.info("Respuesta de N8N no es JSON válido")
                    
                elif response.status_code == 404:
                    record.state = 'error'
                    record.error_message = f"Webhook N8N no encontrado (404). Verifica que:\n1. La URL sea correcta: {record.n8n_webhook_url}\n2. El workflow esté activado en N8N\n3. El endpoint exista"
                    _logger.error(f"Webhook N8N no encontrado: {record.n8n_webhook_url}")
                    
                elif response.status_code >= 500:
                    record.state = 'error'
                    record.error_message = f"Error del servidor N8N ({response.status_code}): {response.text}"
                    _logger.error(f"Error del servidor N8N: {response.status_code} - {response.text}")
                    
                else:
                    record.state = 'error'
                    record.error_message = f"Error en N8N: {response.status_code} - {response.text}"
                    _logger.error(f"Error enviando CV a N8N: {response.status_code} - {response.text}")
                
            except requests.exceptions.ConnectionError as e:
                record.state = 'error'
                error_msg = f"No se pudo conectar con N8N.\n\nURL: {record.n8n_webhook_url}\n\nVerifica que:\n1. El servidor N8N esté ejecutándose\n2. La URL del webhook sea correcta\n3. No haya firewall bloqueando la conexión\n\nError: {str(e)}"
                record.error_message = error_msg
                _logger.error(f"Error de conexión con N8N para {record.employee_id.name}: {str(e)}")
                
            except requests.exceptions.Timeout as e:
                record.state = 'error'
                error_msg = f"Timeout al conectar con N8N. El servidor tardó más de {timeout} segundos en responder.\n\nIntenta:\n1. Aumentar el timeout en configuración\n2. Verificar que N8N no esté sobrecargado\n\nError: {str(e)}"
                record.error_message = error_msg
                _logger.error(f"Timeout con N8N para {record.employee_id.name}: {str(e)}")
                
            except Exception as e:
                record.state = 'error'
                
                # Crear mensaje de error detallado
                error_type = type(e).__name__
                error_msg = str(e)
                
                # Log detallado del error
                _logger.error(f"🔥 ERROR PROCESANDO CV para {record.employee_id.name}")
                _logger.error(f"  ID del record: {record.id}")
                _logger.error(f"  Tipo de error: {error_type}")
                _logger.error(f"  Mensaje: {error_msg}")
                _logger.error(f"  Cédula: {record.cedula}")
                _logger.error(f"  Estado actual: {record.state}")
                
                # Si el archivo existe, mostrar información sobre él
                if record.cv_file:
                    try:
                        cv_file_info = f"  Tipo cv_file: {type(record.cv_file)}"
                        cv_file_length = f"  Longitud cv_file: {len(str(record.cv_file))}"
                        cv_file_preview = f"  Primeros 100 chars: {str(record.cv_file)[:100]}..."
                        
                        _logger.error("📄 INFORMACIÓN DEL ARCHIVO:")
                        _logger.error(cv_file_info)
                        _logger.error(cv_file_length)
                        _logger.error(cv_file_preview)
                        
                        # Intentar decodificar para más info
                        try:
                            decoded = base64.b64decode(str(record.cv_file))
                            _logger.error(f"  Decodificado exitoso: {len(decoded)} bytes")
                            _logger.error(f"  Header del archivo: {decoded[:20]}")
                        except Exception as decode_err:
                            _logger.error(f"  Error decodificando: {str(decode_err)}")
                            
                    except Exception as info_err:
                        _logger.error(f"  Error obteniendo info del archivo: {str(info_err)}")
                
                # Crear mensaje de error user-friendly pero informativo
                if "PDF válido" in error_msg:
                    detailed_error = f"""❌ ERROR DE VALIDACIÓN PDF

🔍 DETALLES:
- Empleado: {record.employee_id.name}
- Cédula: {record.cedula or 'No disponible'}
- Error técnico: {error_type}: {error_msg}

📋 POSIBLES CAUSAS:
1. El archivo descargado no es un PDF válido
2. El archivo está corrupto o dañado
3. La URL institucional devolvió contenido incorrecto
4. Problema en la codificación base64

🔧 SOLUCIONES SUGERIDAS:
1. Verificar manualmente la URL: {record.cv_download_url or 'No disponible'}
2. Intentar descargar nuevamente el CV
3. Verificar que el empleado tenga CV en el sistema institucional
4. Contactar al administrador si el problema persiste

📊 INFORMACIÓN TÉCNICA:
- Timestamp: {fields.Datetime.now()}
- Método de descarga: {'Automático' if record.auto_downloaded else 'Manual'}
- Estado anterior: {record.state}
"""
                else:
                    detailed_error = f"""❌ ERROR INESPERADO

🔍 DETALLES:
- Empleado: {record.employee_id.name}
- Cédula: {record.cedula or 'No disponible'}
- Tipo de error: {error_type}
- Mensaje: {error_msg}

📋 INFORMACIÓN DEL SISTEMA:
- ID del documento: {record.id}
- Estado anterior: {record.state}
- Timestamp: {fields.Datetime.now()}

🔧 ACCIONES RECOMENDADAS:
1. Revisar los logs del sistema para más detalles
2. Intentar procesar nuevamente el documento
3. Verificar la conectividad con N8N
4. Contactar al administrador del sistema

📞 SOPORTE:
Si el problema persiste, proporciona el ID del documento ({record.id}) 
y el timestamp ({fields.Datetime.now()}) al soporte técnico.
"""
                
                record.error_message = detailed_error
                _logger.error(f"🔥 Error procesando CV para {record.employee_id.name}: {str(e)}")
                
                # Log completo del stack trace para debug
                import traceback
                _logger.error("📋 STACK TRACE COMPLETO:")
                _logger.error(traceback.format_exc())
                
                # No lanzar UserError para permitir que el proceso masivo continúe

    def action_download_and_process(self):
        """Descargar CV y procesar automáticamente"""
        self.action_download_cv_from_url()
        # El procesamiento se hace automáticamente en action_download_cv_from_url()

    def action_reset_to_draft(self):
        """Resetear documento a borrador"""
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
        """Aplicar datos extraídos al empleado"""
        for record in self:
            if record.state != 'processed':
                raise UserError(_('El documento debe estar procesado para aplicar los datos'))
            
            update_vals = {}
            
            # Aplicar secciones principales
            if record.extracted_presentacion:
                update_vals['x_presentacion'] = record.extracted_presentacion
            if record.extracted_docencia:
                update_vals['x_docencia_periodo'] = record.extracted_docencia
            if record.extracted_proyectos:
                update_vals['x_proyectos'] = record.extracted_proyectos
            if record.extracted_publicaciones:
                update_vals['x_publicaciones'] = record.extracted_publicaciones
            
            # Aplicar campos adicionales extraídos
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
            
            # Mapear campos detallados adicionales
            if record.extracted_titulos_academicos:
                update_vals['x_titulos_academicos'] = record.extracted_titulos_academicos
            if record.extracted_experiencia_laboral:
                update_vals['x_experiencia_laboral'] = record.extracted_experiencia_laboral
            if record.extracted_capacitaciones:
                update_vals['x_capacitaciones'] = record.extracted_capacitaciones
            if record.extracted_docencia_detalle:
                update_vals['x_formacion_continua'] = record.extracted_docencia_detalle  # Mapear docencia detalle a formación continua
            if record.extracted_distinciones:
                update_vals['x_distinciones'] = record.extracted_distinciones
            
            # También usar proyectos extraídos para participación en proyectos
            if record.extracted_proyectos:
                update_vals['x_participacion_proyectos'] = record.extracted_proyectos
            
            # Usar publicaciones extraídas para el detalle de publicaciones
            if record.extracted_publicaciones:
                update_vals['x_publicaciones_detalle'] = record.extracted_publicaciones
            
            if update_vals:
                # Solo escribir campos que existan en hr.employee para evitar conflictos
                employee_model = record.employee_id
                safe_vals = {k: v for k, v in update_vals.items() if k in employee_model._fields}
                if safe_vals:
                    employee_model.write(safe_vals)
                    _logger.info(
                        f"Datos aplicados al empleado {employee_model.name}: {len(safe_vals)} campos actualizados"
                    )
                else:
                    raise UserError(_('No hay campos compatibles en el empleado para aplicar'))
            else:
                raise UserError(_('No hay datos extraídos para aplicar'))

    def action_test_n8n_connection(self):
        """Probar conexión con N8N"""
        for record in self:
            if not record.n8n_webhook_url:
                raise UserError(_('URL de webhook N8N no configurada'))
            
            try:
                # Hacer una petición simple de prueba
                response = requests.get(
                    record.n8n_webhook_url.replace('/webhook/process-cv', '/webhook/test'),
                    timeout=10
                )
                
                if response.status_code in [200, 404]: 
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Conexión N8N',
                            'message': f'✅ Conexión exitosa con N8N en: {record.n8n_webhook_url}',
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
                              f"2. La URL del webhook sea correcta\n"
                              f"3. No haya firewall bloqueando la conexión")
            except requests.exceptions.Timeout:
                raise UserError(f"❌ Timeout al conectar con N8N.\n\n"
                              f"El servidor tardó demasiado en responder.")
            except Exception as e:
                raise UserError(f"❌ Error inesperado: {str(e)}")

class HrEmployeeCV(models.Model):
    _inherit = 'hr.employee'
    
    cv_document_ids = fields.One2many('cv.document', 'employee_id', string='Documentos CV')
    cv_document_count = fields.Integer(string='Cantidad de CVs', compute='_compute_cv_document_count')
    
    @api.depends('cv_document_ids')
    def _compute_cv_document_count(self):
        for employee in self:
            employee.cv_document_count = len(employee.cv_document_ids)
    
    def action_view_cv_documents(self):
        """Ver documentos CV del empleado"""
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
        """Crear nuevo documento CV"""
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
        """Descargar CV automáticamente desde URL institucional"""
        self.ensure_one()
        
        if not self.identification_id:
            raise UserError(_('El empleado debe tener una cédula para descargar el CV automáticamente'))
        
        # Verificar si ya existe un documento CV
        existing_cv = self.env['cv.document'].search([
            ('employee_id', '=', self.id)
        ], limit=1)
        
        if existing_cv:
            # Si existe, resetear y descargar de nuevo
            # Limpia info de lote para evitar encadenado accidental
            existing_cv.write({'batch_token': False, 'batch_order': 0})
            existing_cv.action_reset_to_draft()
            existing_cv.action_upload_to_n8n()
            return {
                'type': 'ir.actions.act_window',
                'name': f'CV actualizado para {self.name}',
                'res_model': 'cv.document',
                'res_id': existing_cv.id,
                'view_mode': 'form',
                'target': 'current'
            }
        else:
            # Crear nuevo documento CV
            cv_doc = self.env['cv.document'].create({
                'employee_id': self.id,
                'name': f'CV - {self.name}',
                'batch_token': False,
                'batch_order': 0,
            })
            cv_doc.action_upload_to_n8n()
            
            
            return {
                'type': 'ir.actions.act_window',
                'name': f'CV descargado para {self.name}',
                'res_model': 'cv.document',
                'res_id': cv_doc.id,
                'view_mode': 'form',
                'target': 'current'
            }

class CvConfig(models.Model):
    _name = 'cv.config'
    _description = 'Configuración CV Importer'
    _rec_name = 'id'

    # Configuración de N8N
    n8n_webhook_url = fields.Char(
        string='URL Webhook N8N',
        help='URL del webhook de N8N para procesamiento de CV',
        default='https://n8n.pruebasbidata.site/webhook/process-cv'
    )
    n8n_api_key = fields.Char(
        string='API Key N8N',
        help='API Key para autenticación en N8N'
    )
    
    ngrok_url = fields.Char(
        string='URL Ngrok',
        help='URL de ngrok para recibir callbacks cuando Odoo está en localhost. Ejemplo: https://abc123.ngrok-free.app'
    )
    local_development = fields.Boolean(
        string='Modo Desarrollo Local',
        default=True,
        help='Activa optimizaciones para desarrollo local (localhost)'
    )

    def action_test_n8n(self):
        """Probar conexión con N8N"""
        if not self.n8n_webhook_url:
            raise UserError(_('Debes configurar la URL del webhook de N8N'))
            
        try:
            test_payload = {
                'test': True,
                'message': 'Prueba de conexión desde Odoo',
                'timestamp': fields.Datetime.now().isoformat()
            }
            
            response = requests.post(
                self.n8n_webhook_url,
                json=test_payload,
                timeout=10
            )
            
            if response.status_code in [200, 201]:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('¡Prueba exitosa!'),
                        'message': _('N8N está respondiendo correctamente'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(_('N8N respondió con código: %s') % response.status_code)
                
        except Exception as e:
            raise UserError(_('Error conectando con N8N: %s') % str(e))
    
    def action_init_cv_importer_params(self):
        """Inicializa los parámetros de sistema requeridos por cv_importer."""
        ICP = self.env['ir.config_parameter'].sudo()
        created = []
        updated = []
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
                'message': "\n\n".join(msg) + "\n\nVe a Ajustes → Técnico → Parámetros del sistema para ajustar valores (p.ej. pegar la huella).",
                'type': 'success',
                'sticky': False,
            }
        }
    
    # NEW: crear parámetros automáticamente al cargar el módulo
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
