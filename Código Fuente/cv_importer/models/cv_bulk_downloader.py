# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class CvBulkDownloader(models.TransientModel):
    _name = 'cv.bulk.downloader'
    _description = 'Descarga masiva de CVs'

    # Comentar faculty_id por ahora para evitar errores
    # faculty_id = fields.Many2one('x.facultad', string='Facultad', 
    #                             default=lambda self: self._get_default_faculty())
    employee_ids = fields.Many2many('hr.employee', string='Empleados')
    download_all = fields.Boolean(string='Descargar todos los empleados', default=True)
    overwrite_existing = fields.Boolean(string='Sobrescribir CVs existentes', default=False)
    
    # @api.model
    # def _get_default_faculty(self):
    #     """Obtener la facultad de informática por defecto"""
    #     faculty = self.env['x.facultad'].search([
    #         ('name', 'ilike', 'informatica')
    #     ], limit=1)
    #     return faculty.id if faculty else False
    
    @api.onchange('download_all')
    def _onchange_download_all(self):
        """Actualizar lista de empleados cuando cambia la opción"""
        try:
            if self.download_all:
                employees = self.env['hr.employee'].search([
                    ('identification_id', '!=', False)
                ])
                self.employee_ids = [(6, 0, employees.ids)]
            else:
                self.employee_ids = [(5, 0, 0)]
        except Exception as e:
            _logger.error(f"Error in _onchange_download_all: {str(e)}")
            # En caso de error, limpiar la lista
            self.employee_ids = [(5, 0, 0)]
    
    def action_download_cvs(self):
        """Iniciar descarga masiva de CVs"""
        if not self.employee_ids:
            raise UserError(_('Debe seleccionar al menos un empleado'))
        
        created_count = 0
        updated_count = 0
        error_count = 0
        skipped_count = 0
        
        # Asegurar que employee_ids es una lista de registros
        employees = self.employee_ids if isinstance(self.employee_ids, list) else self.employee_ids.filtered(lambda x: x.id)
        
        for employee in employees:
            try:
                # Verificar si el empleado tiene los datos necesarios
                if not employee or not hasattr(employee, 'id') or not employee.id:
                    _logger.warning(f"Empleado inválido encontrado: {employee}")
                    continue
                    
                # Verificar si ya existe un documento CV
                existing_cv = self.env['cv.document'].search([
                    ('employee_id', '=', employee.id)
                ], limit=1)
                
                if existing_cv:
                    if self.overwrite_existing or existing_cv.state in ['draft', 'error']:
                        existing_cv.action_reset_to_draft()
                        existing_cv.action_download_and_process()
                        updated_count += 1
                        _logger.info(f"CV actualizado para {employee.name}")
                    else:
                        skipped_count += 1
                        _logger.info(f"CV omitido para {employee.name} (ya existe)")
                else:
                    # Crear nuevo documento CV
                    cv_document = self.env['cv.document'].create({
                        'name': f"CV - {employee.name}",
                        'employee_id': employee.id
                    })
                    cv_document.action_download_and_process()
                    created_count += 1
                    _logger.info(f"CV creado para {employee.name}")
                    
            except Exception as e:
                error_count += 1
                _logger.error(f"Error procesando CV para {employee.name}: {str(e)}")
        
        # Mensaje de resultado
        message_parts = []
        if created_count > 0:
            message_parts.append(f"✅ {created_count} CVs nuevos creados")
        if updated_count > 0:
            message_parts.append(f"🔄 {updated_count} CVs actualizados")
        if skipped_count > 0:
            message_parts.append(f"⏭️ {skipped_count} CVs omitidos")
        if error_count > 0:
            message_parts.append(f"❌ {error_count} errores")
        
        message = "Procesamiento completado:\n" + "\n".join(message_parts)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Descarga masiva completada',
                'message': message,
                'type': 'success' if error_count == 0 else 'warning'
            }
        }
    
    def action_view_cv_documents(self):
        """Ver todos los documentos CV"""
        employee_ids = []
        try:
            # Obtener IDs de empleados de forma segura
            if self.employee_ids:
                employee_ids = [emp.id for emp in self.employee_ids if emp and hasattr(emp, 'id') and emp.id]
        except Exception as e:
            _logger.error(f"Error getting employee IDs: {str(e)}")
            
        return {
            'type': 'ir.actions.act_window',
            'name': 'Documentos CV',
            'res_model': 'cv.document',
            'view_mode': 'tree,form',
            'domain': [('employee_id', 'in', employee_ids)] if employee_ids else [],
            'context': {'search_default_group_state': 1}
        }
