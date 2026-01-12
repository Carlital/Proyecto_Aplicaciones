from odoo import models, fields, api

class ResUsers(models.Model):
    _inherit = 'res.users'

    facultad = fields.Many2one(
        'facultad',
        string='Facultad',
        related='employee_id.facultad',
        store=True,
        readonly=True,
    )

    @api.model
    def create(self, vals):
        res = super().create(vals)
        res._sync_facultad()
        res._update_employee_job_title() 
        return res

    def write(self, vals):
        res = super().write(vals)
        trigger = {'password', 'employee_id', 'groups_id'}
        if trigger & set(vals.keys()):
            self._sync_facultad()
            if 'groups_id' in vals:
                self._update_employee_job_title()
        return res

    def _sync_facultad(self):
        """Asegura que usuarios con empleado tomen la facultad del empleado."""
        for user in self:
            if user.employee_id and user.employee_id.facultad:
                user.facultad = user.employee_id.facultad.id

    def _update_employee_job_title(self):
        """Actualiza el cargo del empleado según los grupos del usuario"""
        for user in self:
            if not user.employee_id:
                continue
            
            employee = user.employee_id
            
            if user.has_group('google_sheets_import.group_admin_institucional'):
                new_title = 'Administrador Institucional'
            elif user.has_group('google_sheets_import.group_coord_academico'):
                new_title = 'Coordinador Académico'
            elif user.has_group('google_sheets_import.group_docente'):
                new_title = 'Docente'
            else:
                continue 
            
            if not employee.job_title or employee.job_title != new_title:
                employee.sudo().write({'job_title': new_title})
                from odoo import _
                import logging
                _logger = logging.getLogger(__name__)
                _logger.info(f"Cargo actualizado automáticamente: {employee.name} → {new_title}")