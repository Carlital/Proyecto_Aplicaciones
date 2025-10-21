import requests
import csv
import base64
import warnings
import urllib3
import logging
import subprocess
import shutil
from io import BytesIO
from io import StringIO
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from PIL import Image
from io import BytesIO
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

_logger = logging.getLogger(__name__)
class Facultad(models.Model):
    _name = 'x.facultad'
    _description = 'Facultad'

    name = fields.Char(string='Nombre', required=True)

class Carrera(models.Model):
    _name = 'x.carrera'
    _description = 'Carrera'

    name = fields.Char(string='Nombre', required=True)
    facultad_id = fields.Many2one('x.facultad', string='Facultad')

class HREmployee(models.Model):
    _inherit = 'hr.employee'

    x_facultad = fields.Many2one('x.facultad', string='Facultad')
    x_carrera = fields.Many2one('x.carrera', string='Carrera')
    x_modalidad = fields.Char(string='Modalidad')
    x_tiempo_dedicacion = fields.Char(string='Tiempo de Dedicación')
    x_observacion = fields.Text(string='Observación')
    x_cv_url = fields.Char(string='URL CV')
    x_presentacion = fields.Text(string="Presentación")
    x_proyectos = fields.Text(string="Proyectos")
    x_publicaciones = fields.Text(string="Publicaciones")
    x_grupo_investigacion = fields.Text(string="Grupo de Investigación")
    x_contacto = fields.Char(string="Contacto")
    x_docencia_periodo = fields.Char(string="Docencia (Periodo)")
    x_seminarios = fields.Integer(string="Seminarios")
    x_titulos_academicos = fields.Text(string="Títulos Académicos")
    x_experiencia_laboral = fields.Text(string="Experiencia Laboral")
    x_formacion_continua = fields.Text(string="Formación Continua")
    x_participacion_proyectos = fields.Text(string="Participación en Proyectos")
    x_publicaciones_detalle = fields.Text(string="Detalle de Publicaciones")
    x_capacitaciones = fields.Text(string="Capacitaciones")
    x_distinciones = fields.Text(string="Premios o Distinciones")
    x_idiomas = fields.Text(string="Idiomas")
    x_cv_pdf = fields.Binary("Archivo PDF del CV")
    
    # Campos adicionales extraídos del CV
    x_email_personal = fields.Char(string='Email Personal', help='Email personal extraído del CV')
    x_titulo_principal = fields.Char(string='Título Principal', help='Título académico principal (Ing., Dr., etc.)')
    x_anos_experiencia = fields.Integer(string='Años de Experiencia', help='Años de experiencia profesional')
    x_orcid = fields.Char(string='ORCID', help='Identificador ORCID del investigador')
    x_oficina = fields.Char(string='Oficina', help='Ubicación de la oficina')
    x_total_publicaciones = fields.Integer(string='Total Publicaciones', help='Número total de publicaciones')
    x_total_proyectos = fields.Integer(string='Total Proyectos', help='Número total de proyectos dirigidos')
    
    def action_fix_identification_digits(self):
        """
        Actualizar todas las cédulas de empleados para que tengan 10 dígitos.
        Si tienen 9 dígitos, se completan con un cero al inicio.
        """
        try:
            # Buscar todos los empleados con identification_id
            employees = self.env['hr.employee'].search([
                ('identification_id', '!=', False),
                ('identification_id', '!=', '')
            ])
            
            # Contadores para el reporte
            updated_count = 0
            already_correct = 0
            errors = []
            
            _logger.info(f"=== INICIANDO ACTUALIZACIÓN DE CÉDULAS ===")
            _logger.info(f"Encontrados {len(employees)} empleados con cédula")
            
            for employee in employees:
                try:
                    cedula = str(employee.identification_id).strip()
                    
                    # Verificar si la cédula tiene exactamente 9 dígitos
                    if len(cedula) == 9 and cedula.isdigit():
                        # Completar con cero al inicio
                        new_cedula = cedula.zfill(10)
                        
                        # Actualizar el empleado
                        employee.write({'identification_id': new_cedula})
                        
                        _logger.info(f"✅ ACTUALIZADO - {employee.name}: {cedula} → {new_cedula}")
                        updated_count += 1
                        
                    elif len(cedula) == 10 and cedula.isdigit():
                        _logger.info(f"ℹ️ YA CORRECTO - {employee.name}: {cedula}")
                        already_correct += 1
                        
                    else:
                        message = f"⚠️ FORMATO NO ESTÁNDAR - {employee.name}: '{cedula}' ({len(cedula)} caracteres)"
                        _logger.warning(message)
                        errors.append(message)
                        
                except Exception as e:
                    error_msg = f"❌ ERROR - {employee.name}: {str(e)}"
                    _logger.error(error_msg)
                    errors.append(error_msg)
            
            # Log del reporte final
            _logger.info(f"=== REPORTE FINAL ===")
            _logger.info(f"✅ Empleados actualizados: {updated_count}")
            _logger.info(f"ℹ️ Ya tenían 10 dígitos: {already_correct}")
            _logger.info(f"⚠️ Formatos no estándar: {len(errors)}")
            _logger.info(f"📋 Total procesados: {len(employees)}")
            
            # Crear mensaje de resultado simplificado
            if updated_count > 0:
                title = "✅ Actualización Exitosa"
                message = f"Se actualizaron {updated_count} cédulas de 9 a 10 dígitos.\n\n📊 Resumen:\n• Actualizados: {updated_count}\n• Ya correctos: {already_correct}\n• Errores: {len(errors)}\n• Total: {len(employees)}"
                msg_type = 'success'
            elif already_correct == len(employees):
                title = "✅ Todo Correcto"
                message = f"Todas las {already_correct} cédulas ya tienen 10 dígitos.\n\nNo se necesitaron cambios."
                msg_type = 'info'
            else:
                title = "⚠️ Atención"
                message = f"No se actualizó ninguna cédula.\n\n📊 Resumen:\n• Ya correctos: {already_correct}\n• Errores: {len(errors)}\n• Total: {len(employees)}"
                msg_type = 'warning'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': title,
                    'message': message,
                    'type': msg_type,
                    'sticky': True,
                }
            }
            
        except Exception as e:
            _logger.error(f"❌ ERROR CRÍTICO en action_fix_identification_digits: {str(e)}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error Crítico',
                    'message': f'Error al actualizar cédulas: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    def action_open_webpage(self):
        self.ensure_one()
        url = f"/docente/{self.identification_id}"
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

class EmployeeImport(models.Model):
    _name = 'employee.import'
    _description = 'Importador de empleados con imágenes'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    sheet_url = fields.Char('URL CSV Datos Empleados (db_docentes)', required=True)
    imagenes_url = fields.Char('URL CSV Imágenes (nombres_docentes)', required=True)
    name = fields.Char(required=True, tracking=True)
    employee_id = fields.Many2one('hr.employee', required=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)


    def normalizar(self, texto, lower=True):
        texto = str(texto or '')
        reemplazos = (
            ("á", "a"), ("é", "e"), ("í", "i"),
            ("ó", "o"), ("ú", "u"),
            ("Á", "A"), ("É", "E"), ("Í", "I"),
            ("Ó", "O"), ("Ú", "U"),
            ("ñ", "n"), ("Ñ", "N")
        )
        for a, b in reemplazos:
            texto = texto.replace(a, b)
        texto = ' '.join(texto.strip().split())
        return texto.lower() if lower else texto.title()
    


    def _validar_y_leer_csv(self, url, tipo='desconocido'):
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

        def descargar(url_final):
            try:
                return requests.get(url_final, verify=False, timeout=15)
            except Exception as e:
                _logger.error("Error al descargar %s desde %s: %s", tipo, url_final, str(e))
                return None

        response = descargar(url)
        if response and b'<!DOCTYPE html>' not in response.content[:300]:
            return csv.DictReader(StringIO(response.content.decode('utf-8')))

        parsed = urlparse(url)
        if 'pubhtml' in parsed.path:
            new_path = parsed.path.replace('pubhtml', 'pub')
            query = parse_qs(parsed.query)
            query['output'] = ['csv']
            new_query = urlencode(query, doseq=True)
            csv_url = urlunparse(parsed._replace(path=new_path, query=new_query))

            _logger.warning("La URL original de %s devolvió HTML. Intentando con: %s", tipo, csv_url)
            response = descargar(csv_url)
            if response and b'<!DOCTYPE html>' not in response.content[:300]:
                return csv.DictReader(StringIO(response.content.decode('utf-8')))

        raise UserError(_(f'La URL de {tipo} no devuelve un CSV válido. Verifica que tenga output=csv.'))

    
    def obtener_diccionario_imagenes(self, csv_reader_img):
        imagenes_dict = {}
        for row in csv_reader_img:
            nombre = (row.get('Nombre') or '').strip()
            url = (row.get('URL de la Imagen') or '').strip()
            if nombre and url:
                clave = self.normalizar(nombre, lower=False)
                imagenes_dict[clave] = url
        return imagenes_dict

    def es_imagen_valida(self, image_data):
        try:
            Image.open(BytesIO(image_data)).verify()
            return True
        except Exception:
            return False

    def descargar_imagen(self, url_imagen):
        # Intento 1: usar requests con verify=False para mayor portabilidad
        try:
            resp = requests.get(url_imagen, timeout=20, verify=False)
            if resp.status_code == 200 and resp.content:
                raw = resp.content
                if self.es_imagen_valida(raw):
                    image = Image.open(BytesIO(raw))
                    output = BytesIO()
                    image.convert('RGBA').save(output, format='PNG')
                    return base64.b64encode(output.getvalue())
        except Exception as e:
            _logger.warning("requests no pudo descargar imagen %s: %s", url_imagen, str(e))

        # Intento 2: fallback a curl -k si está disponible (entornos legacy SSL)
        try:
            if shutil.which("curl"):
                result = subprocess.run(
                    ["curl", "-k", "-s", url_imagen],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=20
                )
                if result.returncode == 0:
                    image_data = result.stdout
                    if self.es_imagen_valida(image_data):
                        image = Image.open(BytesIO(image_data))
                        output = BytesIO()
                        image.convert('RGBA').save(output, format='PNG')
                        return base64.b64encode(output.getvalue())
                    else:
                        _logger.warning("La imagen descargada con curl no es válida: %s", url_imagen)
                else:
                    _logger.warning("curl -k falló para %s: %s", url_imagen, result.stderr.decode())
        except Exception as e:
            _logger.warning("Error al usar curl -k para descargar imagen desde %s: %s", url_imagen, str(e))
        return None

    @api.constrains('employee_id')
    def _check_access_rights(self):
        for record in self:
            if not self.env.user.has_group('base.group_erp_manager'):
                if record.employee_id.user_id != self.env.user:
                    raise UserError('Solo puede modificar sus propios datos')

    def write(self, vals):
        _logger.info(f'Modificación de registro: {self.id} - Usuario: {self.env.user.name}')
        return super().write(vals)

    def unlink(self):
        if not self.env.user.has_group('base.group_erp_manager'):
            raise UserError('Solo administradores pueden eliminar registros')
        return super().unlink()

    def import_employees(self):
        if not self.sheet_url or not self.imagenes_url:
            raise UserError(_('Debes ingresar ambas URLs.'))

        csv_reader_img = self._validar_y_leer_csv(self.imagenes_url, 'imágenes')
        imagenes_dict = self.obtener_diccionario_imagenes(csv_reader_img)

        csv_reader_emp = self._validar_y_leer_csv(self.sheet_url, 'empleados')
        rows_emp = list(csv_reader_emp)


        department = self.env['hr.department'].sudo().search([('name', '=', 'ESPOCH')], limit=1)
        if not department:
            department = self.env['hr.department'].sudo().create({'name': 'ESPOCH'})

        admin_company = self.env.user.company_id
        count = 0

        for record in rows_emp:
            if (record.get('FACULTAD') or '').strip().upper() != 'FACULTAD DE INFORMATICA Y ELECTRONICA':
                continue

            cedula = (record.get('CEDULA') or '').strip()
            if not cedula:
                _logger.info("Registro sin cédula: %s", record)
                continue

            nombres_raw = (record.get('NOMBRES') or '').strip()
            apellidos_raw = (record.get('APELLIDOS') or '').strip()
            primer_nombre = nombres_raw.split()[0].title()
            primer_apellido = apellidos_raw.split()[0].title()
            clave_foto = f"{primer_nombre} {primer_apellido}"
            clave_foto = self.normalizar(clave_foto, lower=False)
            nombre_completo = f"{nombres_raw} {apellidos_raw}"
            url_imagen = imagenes_dict.get(clave_foto)
            if url_imagen:
                image_data = self.descargar_imagen(url_imagen)
            else:
                primer_apellido_mayus = self.normalizar(apellidos_raw.split()[0], lower=False)
                primer_nombre_mayus = self.normalizar(nombres_raw.split()[0], lower=False)
                url_default = f"https://www.espoch.edu.ec/wp-content/uploads/2025/03/{primer_apellido_mayus}-{primer_nombre_mayus}-500x500.jpg"
                image_data = self.descargar_imagen(url_default)

                if not image_data:
                    _logger.info("No se encontró imagen para: %s", nombre_completo)


            facultad_name = self.normalizar(record.get('FACULTAD') or 'Sin Facultad')
            facultad = self.env['x.facultad'].sudo().search([('name', '=', facultad_name)], limit=1)
            if not facultad:
                facultad = self.env['x.facultad'].sudo().create({'name': facultad_name})

            carrera_name = self.normalizar((record.get('CARRERA') or 'Sin Carrera').split(';')[0])
            carrera = self.env['x.carrera'].sudo().search([
                ('name', '=', carrera_name),
                ('facultad_id', '=', facultad.id)
            ], limit=1)
            if not carrera:
                carrera = self.env['x.carrera'].sudo().create({'name': carrera_name, 'facultad_id': facultad.id})

            genero = self.normalizar(record.get('GENERO') or '')
            gender_value = 'other'
            if genero == 'masculino':
                gender_value = 'Masculino'
            elif genero == 'femenino':
                gender_value = 'Femenino'

            cargo_name = self.normalizar(record.get('CARGO') or 'Sin Cargo')
            job = self.env['hr.job'].sudo().search([('name', '=', cargo_name)], limit=1)
            if not job:
                job = self.env['hr.job'].sudo().create({'name': cargo_name})


            employee_vals = {
                'name': nombre_completo,
                'identification_id': cedula,
                'gender': gender_value,
                'work_email': record.get('CORREO INSTITUCIONAL'),
                'job_title': cargo_name,
                'job_id': job.id,
                'x_modalidad': self.normalizar(record.get('MODALIDAD')),
                'x_tiempo_dedicacion': self.normalizar(record.get('TIEMPO DE DEDICACION') or ''),
                'x_facultad': facultad.id,
                'x_carrera': carrera.id,
                'x_observacion': self.normalizar(record.get('OBSERVACION') or ''),
                'x_cv_url': f"https://hojavida.espoch.edu.ec/cv/{cedula.zfill(10)}",
                'department_id': department.id,
                'company_id': admin_company.id,
            }
            
            existing_employee = self.env['hr.employee'].sudo().search([('identification_id', '=', cedula)], limit=1)
            if existing_employee:
                _logger.info("Empleado actualizado: %s - %s", cedula, nombre_completo)
                existing_employee.sudo().write(employee_vals)
                if image_data:
                    existing_employee.sudo().write({'image_1920': image_data})
            else:
                _logger.info("Nuevo empleado creado: %s - %s", cedula, nombre_completo)
                if image_data:
                    employee_vals['image_1920'] = image_data
                self.env['hr.employee'].sudo().create(employee_vals)

            count += 1

        self.env.cr.commit()
        raise UserError(_(f'Se importaron o actualizaron {count} empleados correctamente.'))

    def get_cv_data(self, cedula):
        try:
            # Opción 1: Deshabilitar verificación SSL
            response = requests.get(
                f'https://hojavida.espoch.edu.ec/cv/{cedula}',
                verify=False  # No verificar SSL
            )
            return response.json()
        except Exception as e:
            return {'error': str(e)}
