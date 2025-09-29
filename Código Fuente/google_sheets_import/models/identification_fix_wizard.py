# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class IdentificationFixWizard(models.TransientModel):
    _name = 'identification.fix.wizard'
    _description = 'Asistente para actualizar cédulas de empleados'
    
    employee_count = fields.Integer(string='Empleados encontrados', readonly=True)
    to_update_count = fields.Integer(string='Empleados a actualizar', readonly=True)
    already_correct_count = fields.Integer(string='Ya tienen 10 dígitos', readonly=True)
    preview_text = fields.Text(string='Vista previa de cambios', readonly=True)
    
    @api.model
    def default_get(self, fields_list):
        """Calcular estadísticas al abrir el wizard"""
        res = super().default_get(fields_list)
        
        # Buscar todos los empleados con identification_id
        employees = self.env['hr.employee'].search([
            ('identification_id', '!=', False),
            ('identification_id', '!=', '')
        ])
        
        to_update = []
        already_correct = []
        preview_lines = []
        
        for employee in employees[:20]:  # Mostrar máximo 20 en la vista previa
            try:
                cedula = str(employee.identification_id).strip()
                
                if len(cedula) == 9 and cedula.isdigit():
                    new_cedula = cedula.zfill(10)
                    to_update.append(employee)
                    preview_lines.append(f"✅ {employee.name}: {cedula} → {new_cedula}")
                    
                elif len(cedula) == 10 and cedula.isdigit():
                    already_correct.append(employee)
                    if len(preview_lines) < 10:  # Mostrar algunos ejemplos
                        preview_lines.append(f"ℹ️ {employee.name}: {cedula} (ya correcto)")
                        
            except Exception as e:
                preview_lines.append(f"❌ Error con {employee.name}: {str(e)}")
        
        if len(employees) > 20:
            preview_lines.append(f"... y {len(employees) - 20} empleados más")
        
        res.update({
            'employee_count': len(employees),
            'to_update_count': len([e for e in employees if len(str(e.identification_id).strip()) == 9]),
            'already_correct_count': len([e for e in employees if len(str(e.identification_id).strip()) == 10]),
            'preview_text': '\n'.join(preview_lines)
        })
        
        return res
    
    def action_update_identifications(self):
        """Ejecutar la actualización de cédulas"""
        return self.env['hr.employee'].action_fix_identification_digits()
    
    def action_cancel(self):
        """Cancelar sin hacer cambios"""
        return {'type': 'ir.actions.act_window_close'}
