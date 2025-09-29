# -*- coding: utf-8 -*-
"""
Configuración SSL personalizada para compatibilidad con servidores legacy
"""
import ssl
import os
import logging

_logger = logging.getLogger(__name__)

def configure_ssl_environment():
    """Configurar el entorno SSL para compatibilidad con servidores legacy"""
    try:
        os.environ['PYTHONHTTPSVERIFY'] = '0'
        os.environ['CURL_CA_BUNDLE'] = ''
        os.environ['REQUESTS_CA_BUNDLE'] = ''
        
        if os.name == 'nt':  
            os.environ['OPENSSL_CONF'] = 'NUL'
        else:  
            os.environ['OPENSSL_CONF'] = '/dev/null'
            
        _logger.info("Variables de entorno SSL configuradas para compatibilidad legacy")
        
    except Exception as e:
        _logger.warning(f"No se pudieron configurar las variables de entorno SSL: {str(e)}")

def create_legacy_ssl_context():
    """Crear contexto SSL personalizado para servidores legacy"""
    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        if hasattr(ssl, 'OP_LEGACY_SERVER_CONNECT'):
            context.options |= ssl.OP_LEGACY_SERVER_CONNECT
            
        try:
            context.set_ciphers('DEFAULT@SECLEVEL=1')
        except ssl.SSLError:
            context.set_ciphers('DEFAULT')
            
        _logger.info("Contexto SSL legacy creado exitosamente")
        return context
        
    except Exception as e:
        _logger.error(f"Error creando contexto SSL legacy: {str(e)}")
        return None

def patch_ssl_for_legacy():
    """Parchear SSL para permitir conexiones legacy"""
    try:
        configure_ssl_environment()
        
        ssl._create_default_https_context = ssl._create_unverified_context
        
        _logger.info("SSL parcheado para compatibilidad legacy")
        
    except Exception as e:
        _logger.error(f"Error parcheando SSL: {str(e)}")

patch_ssl_for_legacy()
