from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from unittest.mock import patch, MagicMock
import tempfile
import os

class TestCvParser(TransactionCase):
    
    def setUp(self):
        super().setUp()
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
        
    
    def test_validate_cv_data_invalid_name(self):
        """Test validación con nombre inválido"""
        invalid_data = {
            'name': 'A',  # Muy corto
            'email': 'test@example.com'
        }
        
        with self.assertRaises(ValidationError):
            self.cv_config.validate_cv_data(invalid_data)
    
    def test_validate_cv_data_invalid_experience(self):
        """Test validación con experiencia inválida"""
        invalid_data = {
            'name': 'Test User',
            'email': 'test@example.com',
            'experience_years': -1  # Negativo
        }
        
        with self.assertRaises(ValidationError):
            self.cv_config.validate_cv_data(invalid_data)
    
    def test_metrics_recording(self):
        """Test grabación de métricas"""
        import time
        start_time = time.time()
        
        # Simular operación
        time.sleep(0.1)
        
        self.cv_metrics.record_import_metric(
            start_time=start_time,
            success=True
        )
        
        metrics = self.cv_metrics.search([('operation_type', '=', 'import')])
        self.assertTrue(metrics)
        self.assertGreater(metrics[0].execution_time, 0)
    
    
    def test_performance_report(self):
        """Test generación de reporte de rendimiento"""
        # Crear algunas métricas de prueba
        import time
        start_time = time.time()
        
        self.cv_metrics.record_import_metric(start_time, success=True)
        self.cv_metrics.record_import_metric(start_time, success=False, error_msg="Test error")
    
        
        report = self.cv_metrics.get_performance_report(days=1)
        
        self.assertIn('total_operations', report)
        self.assertIn('error_rate', report)
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
