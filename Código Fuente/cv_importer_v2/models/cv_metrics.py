from odoo import models, fields, api
from datetime import datetime, timedelta
import time
import logging

_logger = logging.getLogger(__name__)

class CvMetrics(models.Model):
    _name = 'cv.metrics'
    _description = 'CV Import Metrics'
    _order = 'create_date desc'
    
    operation_type = fields.Selection([
        ('import', 'Import CV'),
        ('parse', 'Parse CV'),
        ('validate', 'Validate CV'),
        ('cache_hit', 'Cache Hit'),
        ('cache_miss', 'Cache Miss'),
        ('error', 'Error')
    ], required=True)
    
    execution_time = fields.Float('Execution Time (seconds)', digits=(10, 4))
    file_size = fields.Integer('File Size (bytes)')
    success = fields.Boolean('Success', default=True)
    error_message = fields.Text('Error Message')
    cv_candidate_id = fields.Many2one('cv.candidate', 'Candidate')
    import_time = fields.Float('Tiempo de Importación (s)')
    error_count = fields.Integer('Errores')
    cache_hits = fields.Integer('Aciertos de Caché')
    cache_misses = fields.Integer('Fallos de Caché')
    imported_at = fields.Datetime('Fecha de Importación', default=fields.Datetime.now)
    user_id = fields.Many2one('res.users', 'Usuario')
    
    @api.model
    def record_import_metric(self, start_time, file_size=0, success=True, error_msg=None, candidate_id=None):
        """Registra métricas de importación de CV"""
        execution_time = time.time() - start_time
        self.create({
            'operation_type': 'error' if not success else 'import',
            'execution_time': execution_time,
            'file_size': file_size,
            'success': success,
            'error_message': error_msg,
            'cv_candidate_id': candidate_id
        })
        
        if not success:
            _logger.warning(f"CV Import failed in {execution_time:.2f}s: {error_msg}")
        else:
            _logger.info(f"CV Import successful in {execution_time:.2f}s")
    
    @api.model
    def record_cache_metric(self, cache_hit=True):
        """Registra métricas de caché"""
        self.create({
            'operation_type': 'cache_hit' if cache_hit else 'cache_miss',
            'execution_time': 0,
            'success': True
        })
    
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
        
        # Métricas de caché
        cache_hits = metrics.filtered(lambda m: m.operation_type == 'cache_hit')
        cache_misses = metrics.filtered(lambda m: m.operation_type == 'cache_miss')
        cache_hit_rate = (len(cache_hits) / (len(cache_hits) + len(cache_misses))) * 100 if (cache_hits or cache_misses) else 0
        
        return {
            'total_operations': len(metrics),
            'avg_import_time': round(avg_import_time, 2),
            'error_rate': round(error_rate, 2),
            'cache_hit_rate': round(cache_hit_rate, 2),
            'total_errors': len(error_metrics),
            'period_days': days
        }
