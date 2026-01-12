from odoo import models, fields, api
from datetime import datetime, timedelta
import time
import logging
import json as pyjson

_logger = logging.getLogger(__name__)

class CvMetrics(models.Model):
    _name = 'cv.metrics'
    _description = 'CV Import Metrics'
    _order = 'create_date desc'
    
    operation_type = fields.Selection([
        ('import', 'Import CV'),
        ('parse', 'Parse CV'),
        ('validate', 'Validate CV'),
        ('error', 'Error')
    ], required=True)
    
    execution_time = fields.Float('Tiempo de Ejecución (segundos)', digits=(10, 4))
    success = fields.Boolean('Éxito', default=True)
    error_message = fields.Text('Mensajes de Error')
    employee_id = fields.Many2one('hr.employee')

    profiling_pre_json = fields.Text('Profiling Pre (JSON)')
    profiling_post_json = fields.Text('Profiling Post (JSON)')
    pdf_text_length = fields.Integer('Longitud del Texto PDF')
    pdf_pages = fields.Integer('Nro de Páginas del PDF')


    import_time = fields.Float('Tiempo de Importación (s)')
    error_count = fields.Integer('Errores')
    imported_at = fields.Datetime('Fecha de Importación', default=fields.Datetime.now)
    user_id = fields.Many2one('res.users', 'Usuario')
    
    completeness_ratio = fields.Float('Radio de Completitud', digits=(4, 2))

    @api.model
    def record_import_metric(
        self,
        start_time=None,
        success=True,
        error_msg=None,
        employee_id=None,
        operation_type='import',
        duration_seconds=None,
        user_id=None,
        profiling_pre=None,
        profiling_post=None,
        pdf_pages=None,
        pdf_text_length=None,
        completeness_ratio=None,

    ):
        """
        Helper para crear un registro de métricas desde el callback/subida.
        Devuelve el record creado (recordset) o False en caso de fallo.
        Se adapta dinámicamente a los campos definidos en el modelo para evitar excepciones.
        """
        try:
            vals = {}
            # operation_type es required en el modelo
            vals['operation_type'] = operation_type or 'import'

            if 'success' in self._fields:
                vals['success'] = bool(success)
            if 'error_message' in self._fields:
                vals['error_message'] = error_msg or False
            if 'employee_id' in self._fields and employee_id:
                vals['employee_id'] = employee_id.id if hasattr(employee_id, 'id') else employee_id

            if 'pdf_pages' in self._fields and pdf_pages is not None:
                vals['pdf_pages'] = int(pdf_pages)

            if 'pdf_text_length' in self._fields and pdf_text_length is not None:
                vals['pdf_text_length'] = int(pdf_text_length)

            if 'profiling_pre_json' in self._fields and profiling_pre:
                vals['profiling_pre_json'] = pyjson.dumps(profiling_pre, ensure_ascii=False)

            if 'profiling_post_json' in self._fields and profiling_post:
                vals['profiling_post_json'] = pyjson.dumps(profiling_post, ensure_ascii=False)

            if 'completeness_ratio' in self._fields and completeness_ratio is not None:
                vals['completeness_ratio'] = float(completeness_ratio)



            computed_duration = None
            try:
                if duration_seconds is not None:
                    computed_duration = float(duration_seconds)
                elif start_time is not None:
                    import time as _time
                    st = float(start_time)
                    computed_duration = float(_time.time() - st)
            except Exception:
                computed_duration = None

            if computed_duration is not None:
                if 'execution_time' in self._fields:
                    try:
                        vals['execution_time'] = float(computed_duration)
                    except Exception:
                        pass
                if 'import_time' in self._fields:
                    try:
                        vals['import_time'] = float(computed_duration)
                    except Exception:
                        pass
            else:
                # si no se pudo calcular duration y se pasó duration_seconds, intentar asignar
                if duration_seconds is not None and 'execution_time' in self._fields:
                    try:
                        vals['execution_time'] = float(duration_seconds)
                    except Exception:
                        pass


            if 'user_id' in self._fields and user_id:
                vals['user_id'] = user_id.id if hasattr(user_id, 'id') else user_id

            
            rec = self.sudo().create(vals)

            # Si nos dan start_time, intentar setear imported_at
            if start_time and 'imported_at' in self._fields:
                try:
                    from datetime import datetime, timezone
                    if isinstance(start_time, (int, float)):
                        dt = datetime.fromtimestamp(float(start_time), timezone.utc)
                    else:
                        dt = datetime.fromisoformat(str(start_time))
                    rec.write({'imported_at': dt.strftime('%Y-%m-%d %H:%M:%S')})
                except Exception:
                    pass

            _logger.info(
                "cv.metrics creado id=%s operation_type=%s success=%s",
                getattr(rec, 'id', False),
                vals.get('operation_type'),
                vals.get('success'),
            )
            return rec
        except Exception:
            _logger.exception("Error creando métrica en record_import_metric")
            return False

    
    @api.model
    def get_performance_report(self, days=7):
        """Genera reporte de rendimiento"""
        domain = [('create_date', '>=', datetime.now() - timedelta(days=days))]
        metrics = self.search(domain)
        
        if not metrics:
            return {'error': 'No metrics found'}
        
        # Métricas de tiempo
        import_metrics = metrics.filtered(lambda m: m.operation_type == 'import')
        avg_import_time = sum(import_metrics.mapped('execution_time')) / len(import_metrics) if import_metrics else 0
        
        # Métricas de errores
        error_metrics = metrics.filtered(lambda m: m.operation_type == 'error')
        error_rate = (len(error_metrics) / len(metrics)) * 100 if metrics else 0
        
        return {
            'total_operations': len(metrics),
            'avg_import_time': round(avg_import_time, 2),
            'error_rate': round(error_rate, 2),
            'total_errors': len(error_metrics),
            'period_days': days
        }
