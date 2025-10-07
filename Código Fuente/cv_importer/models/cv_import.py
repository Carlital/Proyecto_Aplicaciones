import logging
import requests
from datetime import timedelta
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class CvImport(models.Model):
    _name = 'cv.import'
    _description = 'CV Import'
    _inherit = ['mail.thread']
    
    employee_id = fields.Many2one('hr.employee', required=True, tracking=True)
    cedula = fields.Char('Cédula', required=True, tracking=True)
    last_import = fields.Datetime('Última importación', readonly=True)
    cv_data = fields.Text('Datos CV', readonly=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('imported', 'Importado'),
        ('error', 'Error')
    ], default='draft', tracking=True)

    @api.constrains('cedula')
    def _check_cedula(self):
        for record in self:
            if not record.cedula.isdigit() or len(record.cedula) != 10:
                raise UserError('Cédula inválida')

    def import_cv(self):
        self.ensure_one()
        if not self._check_access_rights():
            raise UserError('No tiene permisos para importar este CV')
        try:
            _logger.info(f'Importando CV para cédula: {self.cedula}')
            
            self.write({
                'last_import': fields.Datetime.now(),
                'state': 'imported'
            })
        except Exception as e:
            _logger.error(f'Error importando CV: {str(e)}')
            self.state = 'error'
            raise UserError(f'Error al importar CV: {str(e)}')

    def _check_access_rights(self):
        """Verificar permisos de acceso"""
        user = self.env.user
        return (user.has_group('base.group_erp_manager') or 
                self.employee_id.user_id == user)
