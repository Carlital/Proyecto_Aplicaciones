# -*- coding: utf-8 -*-
{
    'name': 'CV Importer con N8N',
    'version': '2.0',
    'summary': 'Procesamiento automatizado de CVs usando N8N',
    'description': '''
        Módulo para procesar automáticamente CVs de docentes usando N8N:
        - Subir archivos PDF de CVs
        - Enviar a N8N para conversión a texto plano
        - Extraer automáticamente información relevante
        - Llenar campos de empleados (presentación, docencia, proyectos, publicaciones)
        - Integración con páginas de docentes por cédula
    ''',
    'category': 'Human Resources',
    'author': 'Odoo Specialist',
    'depends': ['hr', 'website'],
    'external_dependencies': {
        'python': ['requests', 'urllib3', 'reportlab'],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/config_data.xml',
        'data/cv_config_data.xml',
        'views/cv_document_views.xml',
        'views/cv_config_views.xml',
        'views/cv_config_new_views.xml',
        'views/hr_employee_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
