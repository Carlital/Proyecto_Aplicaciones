# -*- coding: utf-8 -*-
{
    'name': 'CV Importer',
    'version': '17.0.1.0',
    'description': '''
        Módulo para importación segura de CVs desde ESPOCH.
        - Control de acceso por usuario
        - Validación de datos
        - Registro de auditoría
        - Cache de datos
    ''',
    'author': 'Carla Lomas',
    'license': 'LGPL-3',
    'category': 'Human Resources',
    'depends': ['base', 'hr'],
    'data': [
        'security/ir.model.access.csv',
        'security/cv_security.xml',
        'views/cv_config_views.xml',
        'views/cv_document_views.xml',
        'views/hr_employee_views.xml',
        'views/cv_metrics_views.xml',
        'data/cv_config_data.xml',
        'data/config_data.xml',
    ],
    'test': [
        'tests/test_cv_parser.py',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

