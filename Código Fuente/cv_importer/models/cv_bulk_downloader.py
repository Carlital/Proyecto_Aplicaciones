# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class CvBulkDownloader(models.TransientModel):
    _name = 'cv.bulk.downloader'
    _description = 'Descarga masiva de CVs'

    employee_ids = fields.Many2many('hr.employee', string='Empleados')
    download_all = fields.Boolean(string='Descargar todos los empleados', default=True)
    overwrite_existing = fields.Boolean(string='Sobrescribir CVs existentes', default=False)

    @api.onchange('download_all')
    def _onchange_download_all(self):
        """Actualizar lista de empleados cuando cambia la opción."""
        try:
            if self.download_all:
                employees = self.env['hr.employee'].search([('identification_id', '!=', False)])
                self.employee_ids = [(6, 0, employees.ids)]
            else:
                self.employee_ids = [(5, 0, 0)]
        except Exception as e:
            _logger.error(f"Error in _onchange_download_all: {str(e)}")
            self.employee_ids = [(5, 0, 0)]

    def action_download_cvs(self):
        """Prepara un lote secuencial y lanza SOLO el primero.
        Los siguientes se enviarán cuando N8N devuelva 'processed' al callback (/cv/callback),
        que a su vez llama a _dispatch_next_in_batch() en cv.document.
        """
        if not self.employee_ids:
            raise UserError(_('Debe seleccionar al menos un empleado'))

        created_count = updated_count = error_count = skipped_count = 0

        employees = self.employee_ids if isinstance(self.employee_ids, list) else self.employee_ids.filtered(lambda x: x.id)

        import uuid
        batch_token = f"batch-{uuid.uuid4().hex}"
        order = 1
        first_doc_to_run = None

        for employee in employees:
            try:
                if not employee or not getattr(employee, 'id', None):
                    _logger.warning(f"Empleado inválido encontrado: {employee}")
                    continue

                existing_cv = self.env['cv.document'].search([('employee_id', '=', employee.id)], limit=1)

                if existing_cv:
                    if self.overwrite_existing or existing_cv.state in ['draft', 'error']:
                        existing_cv.write({
                            'batch_token': batch_token,
                            'batch_order': order,
                            'state': 'draft',
                            'error_message': False,
                        })
                        if not first_doc_to_run:
                            first_doc_to_run = existing_cv
                        updated_count += 1
                        _logger.info(f"CV preparado (batch) para {employee.name} (orden {order})")
                    else:
                        skipped_count += 1
                        _logger.info(f"CV omitido para {employee.name} (ya existe y no se sobrescribe)")
                else:
                    cv_document = self.env['cv.document'].create({
                        'name': f"CV - {employee.name}",
                        'employee_id': employee.id,
                        'batch_token': batch_token,
                        'batch_order': order,
                        'state': 'draft',
                    })
                    if not first_doc_to_run:
                        first_doc_to_run = cv_document
                    created_count += 1
                    _logger.info(f"CV creado (batch) para {employee.name} (orden {order})")

                order += 1

            except Exception as e:
                error_count += 1
                _logger.error(f"Error preparando CV para {getattr(employee, 'name', 'desconocido')}: {str(e)}")

        if first_doc_to_run:
            try:
                first_doc_to_run.action_upload_to_n8n()
                _logger.info(f"▶️ Lanzado primer documento del lote {batch_token}: id={first_doc_to_run.id}")
            except Exception as e:
                error_count += 1
                _logger.error(f"No se pudo lanzar el primer documento del lote {batch_token}: {e}")

        parts = []
        if created_count > 0: parts.append(f"{created_count} CVs nuevos creados")
        if updated_count > 0: parts.append(f"{updated_count} CVs actualizados")
        if skipped_count > 0: parts.append(f"{skipped_count} CVs omitidos")
        if error_count > 0:   parts.append(f"{error_count} errores")
        parts.append(f"Lote: {batch_token}")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Descarga masiva (modo secuencial)',
                'message': "Procesamiento preparado:\n" + "\n".join(parts) +
                           "\n\nSe inició el primero y los siguientes se encadenarán por callback.",
                'type': 'success' if error_count == 0 else 'warning',
                'sticky': True,
            }
        }

    def action_view_cv_documents(self):
        """Abrir vista de documentos CV de los empleados seleccionados."""
        employee_ids = []
        try:
            if self.employee_ids:
                employee_ids = [emp.id for emp in self.employee_ids if emp and getattr(emp, 'id', None)]
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
