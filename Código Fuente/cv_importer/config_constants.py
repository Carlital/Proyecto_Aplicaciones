"""
Constantes centrales para el módulo cv_importer.
Mantener aquí valores por defecto que puedan overridearse desde ir.config_parameter
"""

# Constantes de configuración centralizadas
CV_IMPORT_TIMEOUT = 30  # segundos
CV_IMPORT_RETRIES = 3
CV_IMPORT_HEADERS = {
    "User-Agent": "cv-importer/1.0",
    "Accept": "application/json",
}

# Puedes importar estas constantes donde las necesites:
# from .config_constants import CV_IMPORT_TIMEOUT, CV_IMPORT_RETRIES, CV_IMPORT_HEADERS
