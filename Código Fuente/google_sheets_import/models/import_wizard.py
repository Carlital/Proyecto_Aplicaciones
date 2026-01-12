# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json

class EmployeeImportWizard(models.TransientModel):
    _name = 'employee.import.wizard'
    _description = 'Wizard para continuar importación después de error'

    import_id = fields.Many2one('employee.import', string='Importación', required=True, readonly=True)
    error_message = fields.Text('Mensaje de Error', readonly=True)
    error_row = fields.Integer('Fila con Error', readonly=True)
    state_data = fields.Text('Datos de Estado', readonly=True)  # JSON con el estado
    
    total_processed = fields.Integer('Filas Procesadas', readonly=True)
    total_created = fields.Integer('Nuevos Empleados', readonly=True)
    total_updated = fields.Integer('Empleados Actualizados', readonly=True)
    total_skipped = fields.Integer('Filas Omitidas', readonly=True)

    def action_retry_import(self):
        """Reintentar la importación desde donde se quedó"""
        self.ensure_one()
        
        # Parsear el estado guardado
        try:
            state = json.loads(self.state_data)
        except:
            raise UserError(_('Error al cargar el estado de la importación'))
        
        # Llamar al método de importación con el estado
        result = self.import_id.import_employees_resume(state)
        
        # Si el import devuelve una notificación, cerramos el wizard y luego mostramos el mensaje
        if result and result.get('type') == 'ir.actions.client' and result.get('tag') == 'display_notification':
            result.setdefault('params', {})
            result['params']['next'] = {'type': 'ir.actions.act_window_close'}
            return result

        # En cualquier otro caso, solo cerramos el wizard
        return {'type': 'ir.actions.act_window_close'}


    def action_cancel_import(self):
        """Cancelar y volver al formulario de importación"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'employee.import',
            'res_id': self.import_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
