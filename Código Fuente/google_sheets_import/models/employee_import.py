import requests
import csv
import base64
import logging
import subprocess
import shutil
import json
from io import BytesIO, StringIO
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from PIL import Image

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import urllib3
import warnings
import re

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

_logger = logging.getLogger(__name__)
class Facultad(models.Model):
    _name = 'facultad'
    _description = 'Facultad'

    name = fields.Char(string='Nombre', required=True)
    name_normalized = fields.Char(string='Nombre Normalizado', compute='_compute_name_normalized', store=True, index=True)

    @api.depends('name')
    def _compute_name_normalized(self):
        """Guarda una versión normalizada para búsquedas rápidas"""
        for record in self:
            if record.name:
                texto = str(record.name or '')
                reemplazos = (
                    ("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"),
                    ("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"), ("Ú", "U"),
                    ("ñ", "n"), ("Ñ", "N")
                )
                for a, b in reemplazos:
                    texto = texto.replace(a, b)
                record.name_normalized = ' '.join(texto.strip().split()).lower()
            else:
                record.name_normalized = False

    def action_corregir_tildes_masivo(self):
        facultades_correccion = {
            'INFORMATICA Y ELECTRONICA': 'Informática Y Electrónica',
            'CIENCIAS': 'Ciencias',
            'MECANICA': 'Mecánica',
            'RECURSOS NATURALES': 'Recursos Naturales',
            'SALUD PUBLICA': 'Salud Pública',
            'ADMINISTRACION DE EMPRESAS': 'Administración De Empresas',
            'CIENCIAS PECUARIAS': 'Ciencias Pecuarias',
            'ZOOTECNIA': 'Zootecnia',
        }
        
        facultades = self.search([])
        updated = 0
        
        for facultad in facultades:
            nombre_upper = facultad.name.upper()
            if nombre_upper in facultades_correccion:
                nuevo_nombre = facultades_correccion[nombre_upper]
                if facultad.name != nuevo_nombre:
                    facultad.write({'name': nuevo_nombre})
                    _logger.info(f"Facultad actualizada: {facultad.name} → {nuevo_nombre}")
                    updated += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Facultades Actualizadas',
                'message': f'Se actualizaron {updated} facultades con tildes y ñ correctas.',
                'type': 'success',
                'sticky': True,
            }
        }

class Carrera(models.Model):
    _name = 'carrera'
    _description = 'Carrera'

    name = fields.Char(string='Nombre', required=True)
    name_normalized = fields.Char(string='Nombre Normalizado', compute='_compute_name_normalized', store=True, index=True)
    facultad_id = fields.Many2one('facultad', string='Facultad')

    @api.depends('name')
    def _compute_name_normalized(self):
        for record in self:
            if record.name:
                texto = str(record.name or '')
                reemplazos = (
                    ("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"),
                    ("Á", "A"), ("É", "E"), ("Í", "I"), ("Ó", "O"), ("Ú", "U"),
                    ("ñ", "n"), ("Ñ", "N")
                )
                for a, b in reemplazos:
                    texto = texto.replace(a, b)
                record.name_normalized = ' '.join(texto.strip().split()).lower()
            else:
                record.name_normalized = False

    def action_corregir_tildes_masivo(self):
        """
        Acción para corregir tildes y ñ de todas las carreras existentes
        """
        carreras_correccion = {
            'SOFTWARE': 'Software',
            'DISENO GRAFICO': 'Diseño Gráfico',
            'TECNOLOGIAS DE LA INFORMACION': 'Tecnologías De La Información',
            'TELECOMUNICACIONES': 'Telecomunicaciones',
            'TELEMATICA': 'Telemática',
            'ELECTRICIDAD': 'Electricidad',
            'ELECTRONICA Y AUTOMATIZACION': 'Electrónica Y Automatización',
            'ELECTRONICA Y TELECOMUNICACIONES': 'Electrónica Y Telecomunicaciones',
            'INFORMATICA': 'Informática',
            'SISTEMAS': 'Sistemas',
            'REDES Y TELECOMUNICACIONES': 'Redes Y Telecomunicaciones',
        }
        
        carreras = self.search([])
        updated = 0
        
        for carrera in carreras:
            nombre_upper = carrera.name.upper()
            if nombre_upper in carreras_correccion:
                nuevo_nombre = carreras_correccion[nombre_upper]
                if carrera.name != nuevo_nombre:
                    carrera.write({'name': nuevo_nombre})
                    _logger.info(f"Carrera actualizada: {carrera.name} → {nuevo_nombre}")
                    updated += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Carreras Actualizadas',
                'message': f'Se actualizaron {updated} carreras con tildes y ñ correctas.',
                'type': 'success',
                'sticky': True,
            }
        }

class HREmployee(models.Model):
    _inherit = 'hr.employee'

    facultad = fields.Many2one('facultad', string='Facultad')
    carrera = fields.Many2one('carrera', string='Carrera')
    x_cv_url = fields.Char(string='URL CV')
    gender = fields.Selection(
        selection=[
            ('female', 'Femenino'),
            ('male', 'Masculino'),
            ('other', 'Otro'),
        ],
        string='Género',
    )

    _sql_constraints = [
        (
            'employee_identification_unique',
            'unique(identification_id)',
            'La cédula del docente debe ser única en el sistema.'
        ),
    ]


    def action_fix_identification_digits(self):
        try:
            employees = self.env['hr.employee'].search([
                ('identification_id', '!=', False),
                ('identification_id', '!=', '')
            ])
            
            updated_count = 0
            already_correct = 0
            errors = []
            
            _logger.info(f"Encontrados {len(employees)} empleados con cédula")
            
            for employee in employees:
                try:
                    cedula = str(employee.identification_id).strip()
                    
                    if len(cedula) == 9 and cedula.isdigit():
                        new_cedula = cedula.zfill(10)
                        
                        employee.write({'identification_id': new_cedula})
                        
                        _logger.info(f"ACTUALIZADO - {employee.name}: {cedula} → {new_cedula}")
                        updated_count += 1
                        
                    elif len(cedula) == 10 and cedula.isdigit():
                        _logger.info(f"YA CORRECTO - {employee.name}: {cedula}")
                        already_correct += 1
                        
                    else:
                        message = f"FORMATO NO ESTÁNDAR - {employee.name}: '{cedula}' ({len(cedula)} caracteres)"
                        _logger.warning(message)
                        errors.append(message)
                        
                except Exception as e:
                    error_msg = f"ERROR - {employee.name}: {str(e)}"
                    _logger.error(error_msg)
                    errors.append(error_msg)
            
            _logger.info(f"=== REPORTE FINAL ===")
            _logger.info(f"Empleados actualizados: {updated_count}")
            _logger.info(f"Ya tenían 10 dígitos: {already_correct}")
            _logger.info(f"Formatos no estándar: {len(errors)}")
            _logger.info(f"Total procesados: {len(employees)}")
            
            if updated_count > 0:
                title = "Actualización Exitosa"
                message = f"Se actualizaron {updated_count} cédulas de 9 a 10 dígitos.\n\nResumen:\n• Actualizados: {updated_count}\n• Ya correctos: {already_correct}\n• Errores: {len(errors)}\n• Total: {len(employees)}"
                msg_type = 'success'
            elif already_correct == len(employees):
                title = "Todo Correcto"
                message = f"Todas las {already_correct} cédulas ya tienen 10 dígitos.\n\nNo se necesitaron cambios."
                msg_type = 'info'
            else:
                title = "Atención"
                message = f"No se actualizó ninguna cédula.\n\nResumen:\n• Ya correctos: {already_correct}\n• Errores: {len(errors)}\n• Total: {len(employees)}"
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
            _logger.error(f"ERROR CRÍTICO en action_fix_identification_digits: {str(e)}")
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
    name = fields.Char(required=True, tracking=True,default=lambda self: self.env.user.name)

    facultad_filter = fields.Selection(
        selection=[
            ('', 'Todas las Facultades'),
            ('FACULTAD DE INFORMATICA Y ELECTRONICA', '🎓 Informática y Electrónica'),
            ('FACULTAD DE CIENCIAS', '🎓 Ciencias'),
            ('FACULTAD DE MECANICA', '🎓 Mecánica'),
            ('FACULTAD DE RECURSOS NATURALES', '🎓 Recursos Naturales'),
            ('FACULTAD DE SALUD PUBLICA', '🎓 Salud Pública'),
            ('FACULTAD DE ADMINISTRACION DE EMPRESAS', '🎓 Administración de Empresas'),
            ('FACULTAD DE CIENCIAS PECUARIAS', '🎓 Ciencias Pecuarias'),
        ],
        string='Filtrar por Facultad',
        default='',
        help='Seleccione una facultad para importar solo sus docentes'
    )
    
    facultad_custom = fields.Char(
        string='O escriba otra Facultad',
        help='Escriba el nombre EXACTO de la facultad tal como aparece en el CSV (ejemplo: FACULTAD DE ZOOTECNIA)'
    )

    def action_update_job_titles(self):
        """Actualizar cargos de todos los empleados según sus grupos"""
        employees = self.env['hr.employee'].sudo().search([('user_id', '!=', False)])
        updated = 0

        for emp in employees:
            old_title = emp.job_title or ''
            new_title = old_title

            # EJEMPLO: si el usuario está en tu grupo docente, asigna "Docente"
            if emp.user_id and emp.user_id.has_group('google_sheets_import.group_docente'):
                new_title = "Docente"

            if new_title != old_title:
                emp.write({'job_title': new_title})
                _logger.info(f"Cargo actualizado: {emp.name} - {old_title} → {new_title}")
                updated += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cargos Actualizados'),
                'message': _(f'Se actualizaron {updated} cargos de empleados.'),
                'type': 'success',
                'sticky': True,
            }
        }


    @api.model
    def _default_employee(self):
        emp = self.env['hr.employee'].sudo().search([('user_id', '=', self.env.uid)], limit=1)
        return emp.id or False

    employee_id = fields.Many2one(
        'hr.employee',
        string='Empleado (registro de responsabilidad)',
        required=False,
        default=_default_employee,
        readonly=True,
        tracking=True,
    )

    user_id = fields.Many2one(
        'res.users',
        string='Usuario',
        default=lambda self: self.env.uid,
        readonly=True,
        tracking=True,
    )
    active = fields.Boolean(default=True, tracking=True)

    FACULTADES_CORRECCION = {
        'INFORMATICA Y ELECTRONICA': 'Informática Y Electrónica',
        'CIENCIAS': 'Ciencias',
        'MECANICA': 'Mecánica',
        'RECURSOS NATURALES': 'Recursos Naturales',
        'SALUD PUBLICA': 'Salud Pública',
        'ADMINISTRACION DE EMPRESAS': 'Administración De Empresas',
        'CIENCIAS PECUARIAS': 'Ciencias Pecuarias',
        'ZOOTECNIA': 'Zootecnia',
    }
    
    CARRERAS_CORRECCION = {
        'SOFTWARE': 'Software',
        'DISENO GRAFICO': 'Diseño Gráfico',
        'TECNOLOGIAS DE LA INFORMACION': 'Tecnologías De La Información',
        'TELECOMUNICACIONES': 'Telecomunicaciones',
        'TELEMATICA': 'Telemática',
        'ELECTRICIDAD': 'Electricidad',
        'ELECTRONICA Y AUTOMATIZACION': 'Electrónica Y Automatización',
        'ELECTRONICA Y TELECOMUNICACIONES': 'Electrónica Y Telecomunicaciones',
        'INFORMATICA': 'Informática',
        'SISTEMAS': 'Sistemas',
        'REDES Y TELECOMUNICACIONES': 'Redes Y Telecomunicaciones',
    }

    def _corregir_tildes(self, texto, tipo='carrera'):
        texto_upper = texto.strip().upper()
        
        diccionario = self.CARRERAS_CORRECCION if tipo == 'carrera' else self.FACULTADES_CORRECCION
        
        if texto_upper in diccionario:
            return diccionario[texto_upper]
        
        return texto.strip().title()

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
    
    def _find_or_create_user(self, email, name):
        """
        Buscar usuario existente por email o crearlo si no existe.
        Evita la creación de usuarios duplicados con email1, email2, etc.
        """
        if not email:
            return False
            
        email = email.strip().lower()
        
        Users = self.env['res.users'].sudo().with_context(active_test=False)

        user = Users.search([('login', '=ilike', email)], limit=1)

        if user:
            _logger.info(f"Usuario encontrado para email {email}: {user.id}")
            #si estaba inactivo, reactivarlo para reusarlo (evita duplicados)
            if not user.active:
                user.write({'active': True})
            if user.name != name:
                user.write({'name': name})
            return user
        
        try:
            grupo_docente = self.env.ref('google_sheets_import.group_docente')
            
            user = self.env['res.users'].sudo().create({
                'name': name,
                'login': email,
                'email': email,
                'groups_id': [(4, grupo_docente.id)],
                'active': True,
            })
            _logger.info(f"Nuevo usuario creado: {email} - ID: {user.id}")
            return user
        except Exception as e:
            _logger.error(f"Error al crear usuario {email}: {e}")
            return False
    
    def _find_or_create_employee(self, employee_data):
        """
        Buscar empleado existente o crear uno nuevo.
        Prioridad de búsqueda:
        1. Por identification_id (cédula)
        2. Por work_email
        3. Por user_id
        """
        Employee = self.env['hr.employee'].sudo().with_context(active_test=False)

        
        #Buscar por cédula
        if employee_data.get('identification_id'):
            employee = Employee.search([
                ('identification_id', '=', employee_data['identification_id'])
            ], limit=1)
            
            if employee:
                _logger.info(f"Empleado encontrado por cédula {employee_data['identification_id']}: {employee.id}")
                return employee
        
        #Buscar por email
        if employee_data.get('work_email'):
            email = employee_data['work_email'].strip().lower()
            employee = Employee.search([
                ('work_email', '=ilike', email)
            ], limit=1)
            
            if employee:
                _logger.info(f"Empleado encontrado por email {email}: {employee.id}")
                return employee
        
        # Buscar por user_id
        if employee_data.get('user_id'):
            employee = Employee.search([
                ('user_id', '=', employee_data['user_id'])
            ], limit=1)
            
            if employee:
                _logger.info(f"Empleado encontrado por user_id {employee_data['user_id']}: {employee.id}")
                return employee
        
        # No existe, crea uno nuevo
        return False
    
    def _import_employee_data(self, row_data):
        """
        Importar o actualizar un empleado desde los datos de la fila.
        """
        try:
            # Extraer datos
            name = row_data.get('name', '').strip()
            work_email = row_data.get('work_email', '').strip()
            identification_id = row_data.get('identification_id', '').strip()
            
            if not name or not work_email:
                _logger.warning("Fila sin nombre o email, se omite")
                return False
            
            # Buscar o crear usuario
            user = self._find_or_create_user(work_email, name)
            
            if not user:
                _logger.error(f"No se pudo crear/encontrar usuario para {work_email}")
                return False
            
            #Preparar datos del empleado
            employee_data = {
                'name': name,
                'work_email': work_email,
                'identification_id': identification_id,
                'user_id': user.id,
                'job_title': row_data.get('job_title', ''),
                'department_id': row_data.get('department_id', False),
                'carrera': row_data.get('carrera_id', False),
            }
            
            #Buscar empleado existente
            employee = self._find_or_create_employee(employee_data)
            
            if employee:
                # Actualizar empleado existente
                employee.write(employee_data)
                _logger.info(f"Empleado actualizado: {name} (ID: {employee.id})")
            else:
                # Crear nuevo
                employee = self.env['hr.employee'].sudo().create(employee_data)
                _logger.info(f"Nuevo empleado creado: {name} (ID: {employee.id})")
            
            return employee
            
        except Exception as e:
            _logger.error(f"Error importando empleado {row_data.get('name', 'Unknown')}: {e}")
            return False

    def cleanup_duplicate_users(self):
        """
        Método para limpiar usuarios duplicados existentes.
        """
        Users = self.env['res.users'].sudo()
        Employees = self.env['hr.employee'].sudo()
        
        all_users = Users.search([
            ('login', '!=', False),
            ('id', '!=', 1),
            ('login', 'not in', ['admin'])
        ])

        
        cleaned = 0
        deleted_users = 0
        deleted_employees = 0
        errors = []
        
        for user in all_users:
            import re
            
            base_email = None
            patron_detectado = None
            
            # Patrón 1: usuario1@dominio.ext
            match1 = re.match(r'^(.+?)(\d+)(@.+)$', user.login)
            
            # Patrón 2: usuario@dominio.ext1
            match2 = re.match(r'^(.+@.+\..+?)(\d+)$', user.login)
            
            # Patrón 3: usuario@dominio.ext/n1 o s/n1
            match3 = re.match(r'^(.+?)(/n\d+)$', user.login)
            
            if match1:
                base_email = match1.group(1) + match1.group(3)
                patron_detectado = "Patrón 1 (antes de @)"
                _logger.info(f"Patrón 1 detectado: {user.login} -> {base_email}")
                
            elif match2:
                base_email = match2.group(1)
                patron_detectado = "Patrón 2 (sufijo numérico al final)"
                _logger.info(f"Patrón 2 detectado: {user.login} -> {base_email}")
                
            elif match3:
                base_email = match3.group(1)
                patron_detectado = "Patrón 3 (/nX)"
                _logger.info(f"Patrón 3 detectado: {user.login} -> {base_email}")
            
            if base_email:
                original_user = Users.search([
                    ('login', '=', base_email),
                    ('id', '!=', user.id)
                ], limit=1)
                
                if original_user:
                    _logger.info(f"Usuario duplicado encontrado: {user.login} ({patron_detectado})")
                    _logger.info(f"Usuario original: {original_user.login} (ID: {original_user.id})")
                    
                    try:
                        duplicate_employees = Employees.search([('user_id', '=', user.id)])
                        
                        for emp in duplicate_employees:
                            original_employee = Employees.search([
                                ('user_id', '=', original_user.id)
                            ], limit=1)
                            
                            if original_employee:
                                _logger.info(f"Merge empleados:")
                                _logger.info(f"   Duplicado: {emp.name} (ID: {emp.id})")
                                _logger.info(f"   Original: {original_employee.name} (ID: {original_employee.id})")
                                
                                update_vals = {}
                                merge_fields = [
                                    'work_email', 'private_email', 'mobile_phone', 'work_phone',
                                    'job_title', 'job_id', 'department_id', 'parent_id',
                                    'coach_id', 'address_id', 'work_location_id',
                                    'facultad', 'carrera', 'x_cv_url',
                                    'birthday', 'place_of_birth', 'country_of_birth',
                                    'gender', 'marital', 'spouse_complete_name', 'spouse_birthdate',
                                    'children', 'emergency_contact', 'emergency_phone',
                                    'visa_no', 'visa_expire', 'permit_no', 'work_permit_expiration_date',
                                    'certificate', 'study_field', 'study_school',
                                    'image_1920', 'image_1024', 'image_512', 'image_256', 'image_128'
                                ]
                                
                                for field in merge_fields:
                                    if field in emp._fields:
                                        dup_value = emp[field]
                                        orig_value = original_employee[field]
                                        
                                        if not orig_value and dup_value:
                                            update_vals[field] = dup_value
                                            _logger.info(f"Actualizando '{field}': {dup_value}")
                                
                                if update_vals:
                                    original_employee.write(update_vals)
                                    _logger.info(f"{len(update_vals)} campos actualizados")
                                
                                emp_name = emp.name
                                emp_id = emp.id
                                emp.sudo().unlink()
                                deleted_employees += 1
                                _logger.info(f"Empleado duplicado ELIMINADO: {emp_name} (ID: {emp_id})")
                                
                            else:
                                _logger.info(f"Vinculando empleado {emp.name} al usuario original")
                                emp.write({
                                    'user_id': original_user.id,
                                    'work_email': original_user.email or emp.work_email
                                })
                        
                        user_login = user.login
                        user_id = user.id
                        
                        user.sudo().write({'active': False})
                        
                        user.sudo().unlink()
                        deleted_users += 1
                        cleaned += 1
                        
                        
                    except Exception as e:
                        error_msg = f" Error procesando usuario {user.login}: {str(e)}"
                        _logger.error(error_msg)
                        errors.append(error_msg)
                else:
                    _logger.warning(f" Usuario duplicado detectado pero no se encontró el original:")
                    _logger.warning(f"   Login duplicado: {user.login}")
                    _logger.warning(f"   Login esperado: {base_email}")
                    _logger.warning("")
        
        _logger.info("=" * 60)
        _logger.info("RESUMEN DE LIMPIEZA")
        _logger.info(f"Usuarios duplicados procesados: {cleaned}")
        _logger.info(f"Usuarios eliminados: {deleted_users}")
        _logger.info(f"Empleados eliminados: {deleted_employees}")
        _logger.info(f"Errores encontrados: {len(errors)}")
        _logger.info("=" * 60)
        
        if errors:
            for i, err in enumerate(errors, 1):
                _logger.error(f"  {i}. {err}")
        
        mensaje = (
            f"Usuarios duplicados procesados: {cleaned}\n"
            f"Usuarios eliminados: {deleted_users}\n"
            f"Empleados eliminados: {deleted_employees}\n"
            f"Errores: {len(errors)}"
        )

        
        if errors:
            mensaje += f'\n\nSe encontraron {len(errors)} errores. Revisa los logs para más detalles.'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _(' Limpieza Completada'),
                'message': mensaje,
                'type': 'success' if not errors else 'warning',
                'sticky': True,
            }
        }



    def _map_gender(self, valor_normalizado):
        """
        Devuelve la clave interna ('female'|'male'|'other') o False si no se reconoce.
        """
        if not valor_normalizado:
            return False
        v = str(valor_normalizado).strip().lower()
        mapping = {
            'femenino': 'female', 'mujer': 'female', 'f': 'female', 'fem': 'female',
            'masculino': 'male', 'hombre': 'male', 'm': 'male', 'masc': 'male',
            'otro': 'other', 'no binario': 'other', 'no binaria': 'other', 'nb': 'other',
            'female': 'female', 'male': 'male', 'other': 'other',
        }
        return mapping.get(v, False)


    def _normalize_cedula(self, cedula_raw):
        """
        Normaliza la cédula:
        - Elimina espacios
        - Si tiene 9 dígitos, le agrega un 0 al inicio -> 10 dígitos
        - Si ya tiene 10 dígitos numéricos, la deja igual
        """
        ced = str(cedula_raw or '').strip()

        if ced.isdigit():
            if len(ced) == 9:
                return ced.zfill(10)
            return ced

        return ced


    def _clean_facultad_name(self, raw):
        txt = (raw or '').split(';')[0].strip()
        txt_lower = txt.lower()

        prefixes = [
            'facultad de ',
            'facultad en ',
            'facultad ',
        ]

        for p in prefixes:
            if txt_lower.startswith(p):
                txt = txt[len(p):].strip()
                break

        return txt


    def _clean_carrera_name(self, raw):
        txt = (raw or '').split(';')[0].strip()
        txt_lower = txt.lower()

        prefixes = [
            'carrera de ',
            'carrera en ',
            'carrera ',
        ]

        for p in prefixes:
            if txt_lower.startswith(p):
                txt = txt[len(p):].strip()
                break

        return txt


    def _get_http_session(self):
        s = requests.Session()
        retry = Retry(
            total=2,
            connect=2,
            read=2,
            backoff_factor=0.2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=50, pool_maxsize=50)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        return s


    def _validar_y_leer_csv(self, url, tipo='desconocido', session=None):
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

        s = session or self._get_http_session()

        def descargar(url_final):
            try:
                return s.get(url_final, verify=False, timeout=15)
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

    def es_imagen_valida(self, image_b64):
        try:
            if not image_b64:
                return False
            raw = base64.b64decode(image_b64)
            Image.open(BytesIO(raw)).verify()
            return True
        except Exception:
            return False


    def descargar_imagen(self, url_imagen, session=None):
        if not url_imagen:
            return False

        session = session or requests.Session()

        def _download(verify_flag):
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            }
            resp = session.get(
                url_imagen,
                timeout=20,
                verify=verify_flag,
                allow_redirects=True,
                headers=headers,
            )
            resp.raise_for_status()

            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "image" not in ctype:
                _logger.warning("La URL no devuelve imagen (Content-Type=%s): %s", ctype, url_imagen)
                return b""
            return resp.content


        try:
            try:
                raw = _download(True)
            except (requests.exceptions.SSLError, requests.exceptions.RequestException):
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                raw = _download(False)

            if not raw:
                return False

            # Abrir 1 sola vez y convertir (evita verify + reopen)
            try:
                img = Image.open(BytesIO(raw))
                img = img.convert("RGBA")
                output = BytesIO()
                img.save(output, format="PNG", optimize=True)
                return base64.b64encode(output.getvalue())
            except Exception:
                _logger.warning("Contenido descargado no es imagen válida: %s", url_imagen)
                return False

        except Exception as e:
            _logger.warning("requests no pudo descargar imagen %s: %s", url_imagen, str(e))

        # Fallback curl (igual que tu lógica)
        try:
            if shutil.which("curl"):
                result = subprocess.run(
                    ["curl", "-k", "-s", url_imagen],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=20
                )
                if result.returncode == 0 and result.stdout:
                    try:
                        img = Image.open(BytesIO(result.stdout))
                        img = img.convert("RGBA")
                        output = BytesIO()
                        img.save(output, format="PNG", optimize=True)
                        return base64.b64encode(output.getvalue())
                    except Exception:
                        _logger.warning("La imagen descargada con curl no es válida: %s", url_imagen)
                else:
                    _logger.warning("curl -k falló para %s: %s", url_imagen, result.stderr.decode())
        except Exception as e:
            _logger.warning("Error al usar curl -k para descargar imagen desde %s: %s", url_imagen, str(e))

        return None


    @api.constrains('employee_id')
    def _check_access_rights(self):
        for record in self:
            if not self.env.user.has_group('base.group_system'):
                if not record.employee_id or record.employee_id.user_id != self.env.user:
                    raise UserError('Solo puede modificar sus propios datos')


    def write(self, vals):
        _logger.info("Modificación de registro: %s - Usuario: %s", self.ids, self.env.user.name)
        return super().write(vals)

    def unlink(self):
        if not self.env.user.has_group('base.group_system'):
            raise UserError('Solo administradores pueden eliminar registros')
        return super().unlink()

    def _show_error_wizard(self, error_row, error_message, count, created_count, updated_count, skipped_count, facultad_seleccionada):
        """Mostrar wizard con el error y permitir continuar"""
        import json
        
        # Guardar el estado actual
        state_data = {
            'last_idx': error_row,
            'count': count,
            'created_count': created_count,
            'updated_count': updated_count,
            'skipped_count': skipped_count,
            'facultad_seleccionada': facultad_seleccionada,
        }
        
        # Crear el wizard
        wizard = self.env['employee.import.wizard'].create({
            'import_id': self.id,
            'error_message': error_message,
            'error_row': error_row,
            'state_data': json.dumps(state_data),
            'total_processed': count,
            'total_created': created_count,
            'total_updated': updated_count,
            'total_skipped': skipped_count,
        })
        
        return {
            'name': _('Error en Importación'),
            'type': 'ir.actions.act_window',
            'res_model': 'employee.import.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
    
    def import_employees_resume(self, resume_state):
        """Continuar importación desde donde se quedó"""
        return self.import_employees(resume_state=resume_state)


    def _check_identity_conflicts(self, employee, cedula, email, user):
        Employee = self.env['hr.employee'].sudo().with_context(active_test=False)
        Users = self.env['res.users'].sudo().with_context(active_test=False)

        msgs = []

        if cedula:
            other_emp = Employee.search([
                ('identification_id', '=', cedula),
                ('id', '!=', employee.id)
            ], limit=1)
            if other_emp:
                msgs.append(
                    f"Conflicto de CÉDULA: {cedula} ya está asignada a '{other_emp.name}' "
                    f"(ID {other_emp.id}, {'Archivado' if not other_emp.active else 'Activo'})."
                )

        if email:
            email_l = email.strip().lower()
            u = Users.search([('login', '=ilike', email_l)], limit=1)
            if u:
                emp_with_user = Employee.search([('user_id', '=', u.id)], limit=1)
                if emp_with_user and emp_with_user.id != employee.id:
                    msgs.append(
                        f"Conflicto: el email '{email_l}' corresponde al usuario (ID {u.id}) "
                        f"que ya está vinculado al empleado '{emp_with_user.name}' "
                        f"(ID {emp_with_user.id}, {'Archivado' if not emp_with_user.active else 'Activo'})."
                    )

        if user:
            emp_with_same_user = Employee.search([
                ('user_id', '=', user.id),
                ('id', '!=', employee.id)
            ], limit=1)
            if emp_with_same_user:
                msgs.append(
                    f"Conflicto: el usuario '{user.login}' (ID {user.id}) ya está vinculado al empleado "
                    f"'{emp_with_same_user.name}' (ID {emp_with_same_user.id}, "
                    f"{'Archivado' if not emp_with_same_user.active else 'Activo'})."
                )


        if employee.identification_id and cedula and employee.identification_id != cedula:
            msgs.append(
                f"El docente ya existía con cédula '{employee.identification_id}' y el CSV intenta cambiarla a '{cedula}'."
            )
        if employee.work_email and email and (employee.work_email.strip().lower() != email.strip().lower()):
            msgs.append(
                f"El docente ya existía con email '{employee.work_email}' y el CSV intenta cambiarlo a '{email}'."
            )

        if msgs:
            return (
                "Conflicto de identidad detectado.\n\n"
                + "\n".join(f"• {m}" for m in msgs)
                + "\n\nCorrección: Ajusta el CSV con el valor correcto (cédula/email) y luego reanuda la importación."
            )

        return False


    def import_employees(self, resume_state=None):
        """
        Importar empleados. Si resume_state está presente, continúa desde donde se quedó.
        """
        if not self.sheet_url or not self.imagenes_url:
            raise UserError(_('Debes ingresar ambas URLs.'))


        ctx_fast = dict(self.env.context, tracking_disable=True, mail_notrack=True, mail_create_nosubscribe=True)
        self = self.with_context(ctx_fast)

        http_session = self._get_http_session()

        csv_reader_img = self._validar_y_leer_csv(self.imagenes_url, 'imágenes', session=http_session)
        imagenes_dict = self.obtener_diccionario_imagenes(csv_reader_img)



        csv_reader_emp = self._validar_y_leer_csv(self.sheet_url, 'empleados', session=http_session)
        rows_emp = list(csv_reader_emp)

        # ========= PRE-CARGA (CACHE) PARA ACELERAR =========
        Users = self.env['res.users'].sudo().with_context(active_test=False)
        Employee = self.env['hr.employee'].sudo().with_context(active_test=False)
        Job = self.env['hr.job'].sudo()

        emails_set = set()
        cedulas_set = set()
        cargos_set = set()

        for r in rows_emp:
            em = (r.get('CORREO INSTITUCIONAL') or '').strip().lower()
            if em:
                emails_set.add(em)

            ced_raw = (r.get('CEDULA') or '').strip()
            if ced_raw:
                ced = self._normalize_cedula(ced_raw)
                if ced:
                    cedulas_set.add(ced)

            cargo_name = self.normalizar(r.get('CARGO') or 'Sin Cargo', lower=False)
            if cargo_name:
                cargos_set.add(cargo_name)

        users_pref = Users.search([('login', 'in', list(emails_set))]) if emails_set else Users.browse()
        user_by_login = {u.login.strip().lower(): u for u in users_pref}

        emps_pref = Employee.search(['|', ('identification_id', 'in', list(cedulas_set)), ('work_email', 'in', list(emails_set))]) if (cedulas_set or emails_set) else Employee.browse()
        emp_by_cedula = {e.identification_id: e for e in emps_pref if e.identification_id}
        emp_by_email = {e.work_email.strip().lower(): e for e in emps_pref if e.work_email}

        jobs_pref = Job.search([('name', 'in', list(cargos_set))]) if cargos_set else Job.browse()
        job_by_name = {j.name.strip().lower(): j for j in jobs_pref}

        fac_by_norm = {}
        car_by_key = {}  # (fac_id, carrera_norm) -> carrera
        # ========= FIN CACHE =========


        try:
            import hashlib, json
            from urllib.parse import urlparse, parse_qs

            content_bytes = json.dumps(rows_emp, ensure_ascii=False, sort_keys=True).encode('utf-8')
            hash_sha256 = hashlib.sha256(content_bytes).hexdigest()

            sheet_gid = None
            try:
                parsed = urlparse(self.sheet_url or '')
                qs = parse_qs(parsed.query)
                if 'gid' in qs:
                    sheet_gid = qs['gid'][0]
            except Exception:
                sheet_gid = None

            name_ds = f"Importación {self.env.user.name}"

            headers = list(rows_emp[0].keys()) if rows_emp else []
            sample_rows = rows_emp[:5] if rows_emp else []
            meta = {
                'headers': headers,
                'sample_rows_count': len(sample_rows),
            }

            vals_ds = {
                'name': name_ds,
                'sheet_url': self.sheet_url or '',
                'sheet_gid': sheet_gid or False,
                'import_datetime': fields.Datetime.now(),
                'user_id': self.env.user.id,
                'row_count': len(rows_emp),
                'hash_sha256': hash_sha256,
                'json_schema': json.dumps({'headers': headers}, ensure_ascii=False),
                'meta_json': json.dumps(meta, ensure_ascii=False),
            }

            ds = self.env['google.sheets.dataset.version'].sudo().search([('hash_sha256', '=', hash_sha256)], limit=1)
            if ds:
                ds.sudo().write({'import_datetime': vals_ds['import_datetime'], 'row_count': vals_ds['row_count']})
            else:
                self.env['google.sheets.dataset.version'].sudo().create(vals_ds)
        except Exception as e:
            _logger.warning("No se pudo registrar google_sheets.dataset.version: %s", e)

        department = self.env['hr.department'].sudo().search([('name', '=', 'ESPOCH')], limit=1)
        if not department:
            department = self.env['hr.department'].sudo().create({'name': 'ESPOCH'})


        if resume_state and isinstance(resume_state, str):
            resume_state = json.loads(resume_state)

        # Restaurar estado si es una reanudación
        if resume_state:
            count = resume_state.get('count', 0)
            created_count = resume_state.get('created_count', 0)
            updated_count = resume_state.get('updated_count', 0)
            skipped_count = resume_state.get('skipped_count', 0)
            start_idx = resume_state.get('last_idx', 2)
            facultad_seleccionada = resume_state.get('facultad_seleccionada')
            _logger.info(f"🔄 REANUDANDO importación desde fila {start_idx}")
        else:
            count = 0
            created_count = 0
            updated_count = 0
            skipped_count = 0
            start_idx = 2
            
            if self.facultad_custom:
                facultad_seleccionada = self.facultad_custom.strip().upper()
                _logger.info("Usando filtro PERSONALIZADO: %s", facultad_seleccionada)
            elif self.facultad_filter:
                facultad_seleccionada = self.facultad_filter.strip().upper()
                _logger.info("Usando filtro PREDEFINIDO: %s", facultad_seleccionada)
            else:
                facultad_seleccionada = None
                _logger.info("Importando TODAS las facultades")

        facultades_en_csv = set()

        for idx, record in enumerate(rows_emp, start=2):
            if idx < start_idx:
                continue
            with self.env.cr.savepoint():
                try:
                    facultad_csv = (record.get('FACULTAD') or '').strip().upper()
                    if facultad_csv: 
                        facultades_en_csv.add(facultad_csv)
                    
                    if facultad_seleccionada and facultad_csv != facultad_seleccionada:
                        skipped_count += 1
                        continue

                    cedula_raw = (record.get('CEDULA') or '').strip()
                    if not cedula_raw:
                        error_msg = (
                            f" Fila {idx}: Falta CÉDULA\n"
                            f"   Nombre: {record.get('NOMBRES', 'N/A')} {record.get('APELLIDOS', 'N/A')}\n"
                            f"   Corrección: Agregar cédula en columna 'CEDULA'"
                        )
                        return self._show_error_wizard(idx, error_msg, count, created_count, updated_count, skipped_count, facultad_seleccionada)

                    cedula = self._normalize_cedula(cedula_raw)
                    
                    if not cedula.isdigit() or len(cedula) not in [9, 10]:
                        error_msg = (
                            f" Fila {idx}: CÉDULA inválida: '{cedula_raw}'\n"
                            f"   Nombre: {record.get('NOMBRES', 'N/A')} {record.get('APELLIDOS', 'N/A')}\n"
                            f"   Corrección: La cédula debe tener 9 o 10 dígitos numéricos"
                        )
                        return self._show_error_wizard(idx, error_msg, count, created_count, updated_count, skipped_count, facultad_seleccionada)

                    nombres_raw = (record.get('NOMBRES') or '').strip()
                    apellidos_raw = (record.get('APELLIDOS') or '').strip()
                    
                    if not nombres_raw or not apellidos_raw:
                        error_msg = (
                            f" Fila {idx}: Faltan datos obligatorios\n"
                            f"   Cédula: {cedula}\n"
                            f"   Nombres: {' FALTA' if not nombres_raw else '✓'}\n"
                            f"   Apellidos: {' FALTA' if not apellidos_raw else '✓'}\n"
                            f"   Corrección: Complete las columnas 'NOMBRES' y 'APELLIDOS'"
                        )
                        return self._show_error_wizard(idx, error_msg, count, created_count, updated_count, skipped_count, facultad_seleccionada)
                    
                    primer_nombre = nombres_raw.split()[0].title()
                    primer_apellido = apellidos_raw.split()[0].title()
                    clave_foto = f"{primer_nombre} {primer_apellido}"
                    clave_foto = self.normalizar(clave_foto, lower=False)
                    nombre_completo = f"{nombres_raw} {apellidos_raw}"
                    
                    work_email = (record.get('CORREO INSTITUCIONAL') or '').strip()
                    
                    if not work_email:
                        error_msg = (
                            f" Fila {idx}: Falta EMAIL\n"
                            f"   Nombre: {nombre_completo}\n"
                            f"   Cédula: {cedula}\n"
                            f"   Corrección: Agregar email en columna 'CORREO INSTITUCIONAL'"
                        )
                        return self._show_error_wizard(idx, error_msg, count, created_count, updated_count, skipped_count, facultad_seleccionada)
                    
                    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                    if not re.match(email_pattern, work_email):
                        error_msg = (
                            f" Fila {idx}: EMAIL inválido: '{work_email}'\n"
                            f"   Nombre: {nombre_completo}\n"
                            f"   Cédula: {cedula}\n"
                            f"   Corrección: Usar formato correcto (ejemplo: usuario@dominio.com)"
                        )
                        return self._show_error_wizard(idx, error_msg, count, created_count, updated_count, skipped_count, facultad_seleccionada)


                    email_l = work_email.strip().lower()

                    # 1) Primero detecta si ya existe el empleado por CÉDULA (antes de tocar usuarios)
                    existing_employee = emp_by_cedula.get(cedula)
                    if not existing_employee:
                        # fallback opcional (por si cache no lo tenía)
                        existing_employee = self.env['hr.employee'].sudo().with_context(active_test=False).search([
                            ('identification_id', '=', cedula)
                        ], limit=1)
                        if existing_employee:
                            emp_by_cedula[cedula] = existing_employee

                    # 2) Si ya existe empleado y el CSV intenta cambiarle el email -> wizard inmediato
                    if existing_employee:
                        current_email = (existing_employee.work_email or '').strip().lower()

                        # Si el empleado ya tenía correo y el CSV quiere cambiarlo: bloquear
                        if current_email and current_email != email_l:
                            conflict_msg = (
                                "Conflicto de identidad detectado.\n\n"
                                f"• El docente ya existe con email '{existing_employee.work_email}'\n"
                                f"• El CSV intenta cambiarlo a '{work_email}'\n\n"
                                "Corrección: Ajusta el CSV con el correo correcto del docente y reanuda la importación."
                            )
                            return self._show_error_wizard(
                                idx, conflict_msg, count, created_count, updated_count, skipped_count, facultad_seleccionada
                            )

                        # Si el empleado NO tenía correo, pero ese email del CSV ya pertenece a otro empleado: bloquear también
                        if not current_email:
                            other_emp_same_email = emp_by_email.get(email_l)
                            if other_emp_same_email and other_emp_same_email.id != existing_employee.id:
                                conflict_msg = (
                                    "Conflicto de identidad detectado.\n\n"
                                    f"• El email '{work_email}' ya está asignado a '{other_emp_same_email.name}' "
                                    f"(Cédula: {other_emp_same_email.identification_id}).\n"
                                    f"• El CSV intenta usarlo para '{existing_employee.name}' (Cédula: {existing_employee.identification_id}).\n\n"
                                    "Corrección: Corrige el correo en el CSV y reanuda la importación."
                                )
                                return self._show_error_wizard(
                                    idx, conflict_msg, count, created_count, updated_count, skipped_count, facultad_seleccionada
                                )


                    # 3) Recién aquí busca/crea el usuario (porque ya no hay conflicto)
                    user = user_by_login.get(email_l)
                    if not user:
                        try:
                            user = self._find_or_create_user(work_email, nombre_completo)
                            if not user:
                                raise Exception("No se pudo crear/encontrar usuario")
                            user_by_login[email_l] = user
                        except Exception as e:
                            error_msg = (
                                f"📍 Fila {idx}: Error al crear/encontrar USUARIO\n"
                                f"   Nombre: {nombre_completo}\n"
                                f"   Email: {work_email}\n"
                                f"   Error: {str(e)}\n"
                                f"   Corrección: Verifica que el email no esté causando conflicto"
                            )
                            return self._show_error_wizard(idx, error_msg, count, created_count, updated_count, skipped_count, facultad_seleccionada)
                    else:
                        if user.name != nombre_completo:
                            user.sudo().write({'name': nombre_completo})
        
                    try:
                        url_imagen = imagenes_dict.get(clave_foto)
                        if url_imagen:
                            image_data = self.descargar_imagen(url_imagen, session=http_session)
                        else:
                            primer_apellido_mayus = self.normalizar(apellidos_raw.split()[0], lower=False)
                            primer_nombre_mayus = self.normalizar(nombres_raw.split()[0], lower=False)
                            url_default = f"https://www.espoch.edu.ec/wp-content/uploads/2025/03/{primer_apellido_mayus}-{primer_nombre_mayus}-500x500.jpg"
                            image_data = self.descargar_imagen(url_default, session=http_session)

                            if not image_data:
                                _logger.info("No se encontró imagen para: %s", nombre_completo)

                        raw_facultad = record.get('FACULTAD') or 'Sin Facultad'

                        facultad_limpia = self._clean_facultad_name(raw_facultad)
                        facultad_name_display = self._corregir_tildes(facultad_limpia, tipo='facultad')
                        facultad_name_search = self.normalizar(facultad_limpia, lower=True)

                        facultad = fac_by_norm.get(facultad_name_search)
                        if not facultad:
                            facultad = self.env['facultad'].sudo().search([
                                '|',
                                ('name', '=ilike', facultad_name_display),
                                ('name_normalized', '=', facultad_name_search),
                            ], limit=1)

                            if not facultad:
                                facultad = self.env['facultad'].sudo().create({'name': facultad_name_display})
                            else:
                                if facultad.name != facultad_name_display:
                                    facultad.write({'name': facultad_name_display})

                            fac_by_norm[facultad_name_search] = facultad


                        raw_carrera = record.get('CARRERA') or 'Sin Carrera'
                        carrera_limpia = self._clean_carrera_name(raw_carrera)
                        carrera_name_display = self._corregir_tildes(carrera_limpia, tipo='carrera')
                        carrera_name_search = self.normalizar(carrera_limpia, lower=True)

                        car_key = (facultad.id, carrera_name_search)
                        carrera = car_by_key.get(car_key)

                        if not carrera:
                            carrera = self.env['carrera'].sudo().search([
                                ('facultad_id', '=', facultad.id),
                                '|',
                                ('name', '=ilike', carrera_name_display),
                                ('name_normalized', '=', carrera_name_search),
                            ], limit=1)

                            if not carrera:
                                carrera = self.env['carrera'].sudo().create({
                                    'name': carrera_name_display,
                                    'facultad_id': facultad.id
                                })
                            else:
                                if carrera.name != carrera_name_display:
                                    carrera.write({'name': carrera_name_display})

                            car_by_key[car_key] = carrera

                        genero = self.normalizar(record.get('GENERO') or '')
                        mapped_gender = self._map_gender(genero)
                        gender_value = mapped_gender if mapped_gender else 'other'

                        cargo_name = self.normalizar(record.get('CARGO') or 'Sin Cargo', lower=False)
                        job = job_by_name.get(cargo_name.strip().lower())
                        if not job:
                            job = self.env['hr.job'].sudo().create({'name': cargo_name})
                            job_by_name[cargo_name.strip().lower()] = job

                        employee_vals = {
                            'name': nombre_completo,
                            'job_title': cargo_name,
                            'identification_id': cedula,
                            'gender': gender_value,
                            'work_email': work_email,
                            'user_id': user.id,  
                            'facultad': facultad.id,
                            'carrera': carrera.id,
                            'x_cv_url': f"https://hojavida.espoch.edu.ec/cv/{cedula.zfill(10)}",
                        }
                        
                        if not existing_employee:
                            existing_employee = self._find_or_create_employee(employee_vals)
                        else:
                            # refresca cache por si acaso
                            emp_by_cedula[cedula] = existing_employee
                            emp_by_email[email_l] = existing_employee


                        if existing_employee:

                            if not existing_employee.active:
                                existing_employee.sudo().write({'active': True})

                            safe_vals = {
                                'gender': gender_value,
                                'facultad': facultad.id,
                                'carrera': carrera.id,
                                'x_cv_url': f"https://hojavida.espoch.edu.ec/cv/{cedula.zfill(10)}",
                                'name': nombre_completo,
                            }

                            conflict_msg = self._check_identity_conflicts(existing_employee, cedula, work_email, user)

                            if conflict_msg:
                                return self._show_error_wizard(
                                    idx,
                                    conflict_msg,
                                    count, created_count, updated_count, skipped_count, facultad_seleccionada
                                )

                            safe_vals.update({
                                'identification_id': cedula,
                                'work_email': work_email,
                                'user_id': user.id,
                            })

                            # Solo escribe si realmente cambió algo (misma lógica, menos costo)
                            to_write = {}
                            for k, v in safe_vals.items():
                                if k not in existing_employee._fields:
                                    continue

                                field = existing_employee._fields[k]

                                # Many2one: comparar por ID (y convertir si viene '1' como string)
                                if field.type == 'many2one':
                                    current_id = existing_employee[k].id if existing_employee[k] else False

                                    if isinstance(v, str):
                                        v = v.strip()
                                        new_id = int(v) if v.isdigit() else False
                                    elif hasattr(v, "id"):  # por si algún día mandas recordset
                                        new_id = v.id
                                    else:
                                        new_id = v or False

                                    if current_id != new_id:
                                        to_write[k] = new_id

                                # Otros tipos: comparación normal
                                else:
                                    if existing_employee[k] != v:
                                        to_write[k] = v


                            changed = False

                            if to_write:
                                existing_employee.sudo().write(to_write)
                                changed = True

                            if image_data and existing_employee.image_1920 != image_data:
                                existing_employee.sudo().write({'image_1920': image_data})
                                changed = True

                            if changed:
                                updated_count += 1


                        else:
                            if image_data:
                                employee_vals['image_1920'] = image_data
                            new_employee = self.env['hr.employee'].sudo().create(employee_vals)

                            # refrescar caches
                            if cedula:
                                emp_by_cedula[cedula] = new_employee
                            if email_l:
                                emp_by_email[email_l] = new_employee

                            created_count += 1
                            _logger.info(f"Fila {idx}: Nuevo empleado - {nombre_completo} (ID: {new_employee.id})")

                        count += 1
                        
                    except Exception as e:
                        error_msg = (
                            f" Fila {idx}: Error al guardar EMPLEADO\n"
                            f"   Nombre: {nombre_completo}\n"
                            f"   Cédula: {cedula}\n"
                            f"   Email: {work_email}\n"
                            f"   Error: {str(e)}\n"
                            f"   Corrección: Verificar integridad de datos (facultad, carrera, género válidos)"
                        )
                        return self._show_error_wizard(idx, error_msg, count, created_count, updated_count, skipped_count, facultad_seleccionada)

                except Exception as e:
                    error_msg = (
                        f" Fila {idx}: ERROR INESPERADO\n"
                        f"   Datos: {record}\n"
                        f"   Error: {str(e)}\n"
                        f"   Corrección: Revise el formato de la fila completa o contacte al administrador"
                    )
                    return self._show_error_wizard(idx, error_msg, count, created_count, updated_count, skipped_count, facultad_seleccionada)

        # Si llegamos aquí, la importación fue exitosa
        if count > 0:
            if facultad_seleccionada:
                if self.facultad_custom:
                    nombre_fac = self.facultad_custom.title()
                else:
                    selection_dict = dict(self._fields['facultad_filter'].selection)
                    nombre_fac = selection_dict.get(self.facultad_filter, self.facultad_filter).replace('🎓 ', '')
                
                filtro_msg = f"\n\n🎓 Facultad filtrada: {nombre_fac}"
            else:
                filtro_msg = "\n\n🎓 Todas las facultades"
            
            mensaje = _(
                "Importación completada exitosamente:{filtro}\n\n"
                "• Procesados exitosamente: {total}\n"
                "• Nuevos empleados: {created}\n"
                "• Empleados actualizados: {updated}\n"
                "• Filas omitidas (por filtro): {skipped}\n"
            ).format(
                filtro=filtro_msg,
                total=count,
                created=created_count,
                updated=updated_count,
                skipped=skipped_count,
            )
            tipo = 'success'
        else:
            tipo = 'info'
            mensaje = _("No se procesó ningún empleado. Todos los registros ya estaban actualizados.")

        cedulas_vistas = {}
        cedulas_duplicadas = []

        for idx, record in enumerate(rows_emp, start=1):
            cedula_raw = (record.get('CEDULA') or '').strip()
            if cedula_raw:
                cedula = self._normalize_cedula(cedula_raw)
                if cedula in cedulas_vistas:
                    cedulas_duplicadas.append(f"Fila {idx}: Cédula {cedula} (duplica fila {cedulas_vistas[cedula]})")
                else:
                    cedulas_vistas[cedula] = idx

        if cedulas_duplicadas:
            raise UserError(_(
                f"Se encontraron {len(cedulas_duplicadas)} cédulas duplicadas en el CSV:\n\n" +
                "\n".join(cedulas_duplicadas[:10]) +
                (f"\n... y {len(cedulas_duplicadas)-10} más" if len(cedulas_duplicadas) > 10 else "")
            ))

        emails_vistos = {}
        emails_duplicados = []

        for idx, record in enumerate(rows_emp, start=1):
            email = (record.get('CORREO INSTITUCIONAL') or '').strip().lower()
            if email:
                if email in emails_vistos:
                    emails_duplicados.append(f"Fila {idx}: {email} (duplica fila {emails_vistos[email]})")
                else:
                    emails_vistos[email] = idx

        if emails_duplicados:
            _logger.warning(f" Emails duplicados en CSV: {len(emails_duplicados)}")


        cedulas_en_csv = set()
        for record in rows_emp:
            cedula_raw = (record.get('CEDULA') or '').strip()
            if not cedula_raw:
                continue
            
            if facultad_seleccionada:
                facultad_csv = (record.get('FACULTAD') or '').strip().upper()
                if facultad_csv == facultad_seleccionada:
                    cedulas_en_csv.add(self._normalize_cedula(cedula_raw))
            else:
                cedulas_en_csv.add(self._normalize_cedula(cedula_raw))

        all_employees_sistema = self.env['hr.employee'].sudo().search([
            ('identification_id', '!=', False),
            ('active', '=', True)
        ])
        
        _logger.info(f" Total empleados activos en sistema: {len(all_employees_sistema)}")
        
        employees_to_check = all_employees_sistema
        if facultad_seleccionada:
            fac_sel_limpia = self._clean_facultad_name(facultad_seleccionada)
            fac_sel_norm = self.normalizar(fac_sel_limpia, lower=True)
            _logger.info(f" Buscando empleados de facultad: '{facultad_seleccionada}'")
            _logger.info(f" Limpiado: '{fac_sel_limpia}'")
            _logger.info(f" Normalizado: '{fac_sel_norm}'")
            
            empleados_con_facultad = 0
            empleados_sin_facultad = 0
            facultades_unicas = set()
            
            for emp in all_employees_sistema:
                if emp.facultad:
                    empleados_con_facultad += 1
                    facultades_unicas.add(emp.facultad.name)
                else:
                    empleados_sin_facultad += 1
            
            _logger.info(f" De {len(all_employees_sistema)} empleados activos:")
            _logger.info(f"   - Con facultad: {empleados_con_facultad}")
            _logger.info(f"   - Sin facultad: {empleados_sin_facultad}")
            _logger.info(f" Facultades únicas en sistema: {facultades_unicas}")
            
            employees_filtered = []
            primera_facultad_mostrada = False
            for emp in all_employees_sistema:
                if emp.facultad:
                    fac_emp_norm = self.normalizar(emp.facultad.name, lower=True)
                    
                    if not primera_facultad_mostrada:
                        _logger.info(f"EJEMPLO de facultad en sistema:")
                        _logger.info(f"   Original: '{emp.facultad.name}'")
                        _logger.info(f"   Normalizado: '{fac_emp_norm}'")
                        _logger.info(f"   Comparando con: '{fac_sel_norm}'")
                        _logger.info(f"   ¿Son iguales? {fac_emp_norm == fac_sel_norm}")
                        primera_facultad_mostrada = True
                    
                    if fac_emp_norm == fac_sel_norm:
                        employees_filtered.append(emp)
                    else:
                        if len(employees_filtered) == 0:
                            _logger.warning(f"NO COINCIDE: '{emp.facultad.name}' -> '{fac_emp_norm}' vs '{fac_sel_norm}'")
            
            employees_to_check = self.env['hr.employee'].browse([e.id for e in employees_filtered])
            _logger.info(f"Filtrado: {len(employees_to_check)} empleados de {facultad_seleccionada}")
            _logger.info(f"DEBUG: employees_to_check después de filtrar = {len(employees_to_check)} empleados")
            _logger.info(f"DEBUG: IDs = {[e.id for e in employees_to_check[:3]]}")
            
            if len(employees_to_check) > 0:
                _logger.info(f" Empleados encontrados:")
                for emp in employees_to_check[:5]:
                    _logger.info(f"   - {emp.name} (Cédula: {emp.identification_id}, Facultad: {emp.facultad.name})")
                if len(employees_to_check) > 5:
                    _logger.info(f"   ... y {len(employees_to_check) - 5} más")
            else:
                _logger.error(f" NO SE ENCONTRARON EMPLEADOS con facultad '{fac_sel_norm}'")

        if not cedulas_en_csv:
            raise UserError(_(
                "ATENCIÓN: No se detectaron cédulas en el CSV.\n"
                "No se archivará ningún empleado por seguridad.\n"
                "Verifica que el archivo CSV tenga datos válidos."
            ))

        _logger.info(f" DEBUG: Verificando employees_to_check, tipo={type(employees_to_check)}, len={len(employees_to_check)}")
        empleados_activos = len(employees_to_check)
        empleados_en_csv = len(cedulas_en_csv)
        porcentaje = (empleados_en_csv / empleados_activos * 100) if empleados_activos > 0 else 0
        
        _logger.info(f" Validación de seguridad:")
        _logger.info(f"   - Empleados en CSV: {empleados_en_csv}")
        _logger.info(f"   - Empleados activos (filtrados): {empleados_activos}")
        _logger.info(f"   - Porcentaje: {porcentaje:.1f}%")

        if porcentaje < 50 and empleados_activos > 10:
            raise UserError(_(
                f"ATENCIÓN: El CSV solo contiene {empleados_en_csv} empleados, "
                f"pero hay {empleados_activos} activos en el sistema ({porcentaje:.1f}%).\n\n"
                "Por seguridad, no se archivarán empleados.\n"
                "Si esto es correcto, contacta al administrador del sistema."
            ))

        
        _logger.info(" Verificando empleados para archivar...")

        if not 'mensaje' in locals():
            mensaje = ""

        archived_count = 0
        for emp in employees_to_check:
            if emp.identification_id not in cedulas_en_csv:
                _logger.warning(f" EMPLEADO FALTANTE DETECTADO:")
                _logger.warning(f"   Nombre: {emp.name}")
                _logger.warning(f"   Cédula: {emp.identification_id}")
                _logger.warning(f"   Email: {emp.work_email}")
                _logger.warning(f"   Facultad: {emp.facultad.name if emp.facultad else 'SIN FACULTAD'}")
                _logger.warning(f"   Carrera: {emp.carrera.name if emp.carrera else 'SIN CARRERA'}")
                _logger.warning(f"   ARCHIVANDO...")
                
                emp.sudo().write({'active': False})
                archived_count += 1

        if archived_count > 0:
            mensaje += f"\n Archivados (no están en CSV): {archived_count}"
            _logger.warning(f" Total archivados: {archived_count} empleados")
        else:
            _logger.info(" No hay empleados para archivar")

        _logger.info("=" * 60)
        _logger.info("RESUMEN DETALLADO DE IMPORTACIÓN")
        _logger.info(f"Total filas procesadas: {count}")
        _logger.info(f"Nuevos empleados: {created_count}")
        _logger.info(f"Empleados actualizados: {updated_count}")
        _logger.info(f"Filas omitidas: {skipped_count}")
        _logger.info(f"Empleados archivados: {archived_count}")
        _logger.info(f"Cédulas en CSV: {len(cedulas_en_csv)}")
        _logger.info(f"Empleados activos en sistema (filtrados): {empleados_activos}")
        if facultad_seleccionada:
            _logger.info(f"Filtro aplicado: {facultad_seleccionada}")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Importación completada'),
                'message': mensaje,
                'type': tipo,
                'sticky': False,
            }
        }