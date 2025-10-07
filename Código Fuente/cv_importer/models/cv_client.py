import requests
import logging
from datetime import datetime, timedelta
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class CvClient(models.AbstractModel):
    _name = 'cv.client'
    _description = 'Cliente seguro para importación de CV'

    def _get_cv_data(self, cedula):
        # Verificar cache primero
        cached_data = self.env['cv.cache'].search([
            ('cedula', '=', cedula),
            ('create_date', '>=', fields.Datetime.now() - timedelta(hours=24))
        ], limit=1)

        if cached_data:
            return cached_data.data

        try:
            # Configurar session con timeout y reintentos
            session = requests.Session()
            session.mount('https://', requests.adapters.HTTPAdapter(
                max_retries=3,
                pool_connections=1,
                pool_maxsize=1
            ))

            # Log de la petición por seguridad
            _logger.info(f'Solicitando CV para cédula: {cedula}')
            
            response = session.get(
                f'https://hojavida.espoch.edu.ec/cv/{cedula}',
                timeout=10,
                verify=True  # Intentar primero con verificación SSL
            )
            
            if response.status_code == 200:
                # Guardar en cache
                self.env['cv.cache'].create({
                    'cedula': cedula,
                    'data': response.json()
                })
                return response.json()
            else:
                raise UserError(f'Error al obtener CV: {response.status_code}')

        except requests.exceptions.SSLError:
            _logger.warning(f'Error SSL al obtener CV para {cedula}, reintentando sin verificación')
            # Solo si falla SSL, intentar sin verificación pero logear
            try:
                response = session.get(
                    f'https://hojavida.espoch.edu.ec/cv/{cedula}',
                    verify=False,
                    timeout=10
                )
                if response.status_code == 200:
                    return response.json()
            except Exception as e:
                raise UserError(f'Error al obtener CV: {str(e)}')

        except Exception as e:
            _logger.error(f'Error al obtener CV: {str(e)}')
            raise UserError(f'Error al obtener CV: {str(e)}')
