from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from unittest.mock import patch, MagicMock
import tempfile
import os

class TestCvParser(TransactionCase):
    
    def setUp(self):
        super().setUp()
        self.cv_config = self.env['cv.config']
        self.cv_candidate = self.env['cv.candidate']
        self.cv_metrics = self.env['cv.metrics']
    
    def test_config_constants(self):
        """Test que las constantes están correctamente definidas"""
        self.assertGreater(self.cv_config.DEFAULT_TIMEOUT, 0)
        self.assertGreater(self.cv_config.MAX_RETRIES, 0)
        self.assertIsInstance(self.cv_config.DEFAULT_HEADERS, dict)
        self.assertIn('User-Agent', self.cv_config.DEFAULT_HEADERS)
    
    def test_validate_cv_data_success(self):
        """Test validación exitosa de datos de CV"""
        valid_data = {
            'name': 'Juan Pérez',
            'email': 'juan@example.com',
            'phone': '+1234567890',
            'experience_years': 5
        }
        
        candidate = self.cv_candidate.create(valid_data)
        self.assertTrue(candidate.id)
        self.assertEqual(candidate.name, 'Juan Pérez')
    
    def test_validate_cv_data_invalid_name(self):
        """Test validación con nombre inválido"""
        invalid_data = {
            'name': 'A',  # Muy corto
            'email': 'test@example.com'
        }
        
        with self.assertRaises(ValidationError):
            self.cv_candidate.create(invalid_data)
    
    def test_validate_cv_data_invalid_experience(self):
        """Test validación con experiencia inválida"""
        invalid_data = {
            'name': 'Test User',
            'email': 'test@example.com',
            'experience_years': -1  # Negativo
        }
        
        with self.assertRaises(ValidationError):
            self.cv_candidate.create(invalid_data)
    
    def test_metrics_recording(self):
        """Test grabación de métricas"""
        import time
        start_time = time.time()
        
        # Simular operación
        time.sleep(0.1)
        
        self.cv_metrics.record_import_metric(
            start_time=start_time,
            file_size=1024,
            success=True
        )
        
        metrics = self.cv_metrics.search([('operation_type', '=', 'import')])
        self.assertTrue(metrics)
        self.assertGreater(metrics[0].execution_time, 0)
    
    def test_cache_metrics(self):
        """Test métricas de caché"""
        # Cache hit
        self.cv_metrics.record_cache_metric(cache_hit=True)
        
        # Cache miss
        self.cv_metrics.record_cache_metric(cache_hit=False)
        
        hit_metrics = self.cv_metrics.search([('operation_type', '=', 'cache_hit')])
        miss_metrics = self.cv_metrics.search([('operation_type', '=', 'cache_miss')])
        
        self.assertTrue(hit_metrics)
        self.assertTrue(miss_metrics)
    
    def test_performance_report(self):
        """Test generación de reporte de rendimiento"""
        # Crear algunas métricas de prueba
        import time
        start_time = time.time()
        
        self.cv_metrics.record_import_metric(start_time, success=True)
        self.cv_metrics.record_import_metric(start_time, success=False, error_msg="Test error")
        self.cv_metrics.record_cache_metric(cache_hit=True)
        
        report = self.cv_metrics.get_performance_report(days=1)
        
        self.assertIn('total_operations', report)
        self.assertIn('error_rate', report)
        self.assertIn('cache_hit_rate', report)
        self.assertGreater(report['total_operations'], 0)
    
    @patch('requests.post')
    def test_api_with_centralized_config(self, mock_post):
        """Test que las APIs usan configuración centralizada"""
        mock_response = MagicMock()
        mock_response.json.return_value = {'status': 'success'}
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        headers = self.cv_config.get_headers()
        timeout = self.cv_config.get_timeout()
        
        # Verificar que se usan los valores centralizados
        self.assertIn('User-Agent', headers)
        self.assertGreater(timeout, 0)
    
    def test_cv_parser_valid_data():
        # TODO: Implementar test para datos válidos
        pass

    def test_cv_parser_invalid_data():
        # TODO: Implementar test para datos inválidos
        pass

    def test_cv_parser_cache_hit():
        # TODO: Implementar test para acierto de caché
        pass
