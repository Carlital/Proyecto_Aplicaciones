import requests
import logging
import re
from datetime import datetime, timedelta
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class HttpClient(models.AbstractModel):
    _name = 'http.client'
    _description = 'HTTP Client for API calls'

    def _validate_cedula(self, cedula):
        if not re.match(r'^\d{10}$', cedula):
            raise UserError('Cédula inválida: debe tener 10 dígitos')
        return True

    def get_espoch_cv(self, cedula):
        """Método específico para llamadas a hojavida.espoch.edu.ec"""
        try:
            # Validar cédula
            self._validate_cedula(cedula)

            # Verificar cache
            cache_key = f'cv_data_{cedula}'
            cached = self.env['ir.cache'].get(cache_key)
            if cached:
                return cached

            # Configurar session con timeout y reintentos
            session = requests.Session()
            session.mount('https://', requests.adapters.HTTPAdapter(
                max_retries=3,
                pool_connections=1,
                pool_maxsize=1
            ))

            # Log de seguridad
            _logger.info(f'Solicitando CV para cédula: {cedula}')
            
            # Intentar primero con SSL verificado
            try:
                response = session.get(
                    f'https://hojavida.espoch.edu.ec/cv/{cedula}',
                    timeout=10,
                    verify=True
                )
            except requests.exceptions.SSLError:
                _logger.warning(f'Error SSL al obtener CV para {cedula}')
                # Solo si falla SSL, intentar sin verificación
                response = session.get(
                    f'https://hojavida.espoch.edu.ec/cv/{cedula}',
                    timeout=10,
                    verify=False
                )

            if response.status_code != 200:
                raise UserError(f'Error del servidor: {response.status_code}')

            # Guardar en cache por 1 hora
            data = response.json()
            self.env['ir.cache'].set(cache_key, data, ttl=3600)
            
            return data

        except requests.exceptions.Timeout:
            _logger.error(f'Timeout al obtener CV para {cedula}')
            raise UserError('Tiempo de espera agotado')
        except requests.exceptions.RequestException as e:
            _logger.error(f'Error al obtener CV: {str(e)}')
            raise UserError(f'Error de conexión: {str(e)}')
        except Exception as e:
            _logger.error(f'Error inesperado: {str(e)}')
            raise UserError('Error interno del servidor')
