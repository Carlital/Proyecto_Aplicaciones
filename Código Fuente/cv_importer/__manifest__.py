# -*- coding: utf-8 -*-
{
    'name': 'Importador de CV',
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
    'category': 'Recursos Humanos',
    'depends': ['base', 'hr','website', 'web','bus', 'google_sheets_import','mail'],
    'data': [
        'security/cv_groups.xml',
        'security/ir.model.access.csv',
        'security/cv_security.xml',
        'data/cv_config_data.xml',
        'data/config_data.xml',
        'views/cv_config_views.xml',
        'views/cv_document_views.xml',
        'views/cv_academic_degree_views.xml',
        'views/cv_metrics_views.xml',
        'report/cv_reports.xml',
        'views/hr_employee_cv_academic_views.xml',
        'views/cv_work_experience_views.xml',
        'views/hr_employee_cv_work_experience_views.xml',
        'views/cv_publication_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_employee_cv_publication_views.xml',
        'views/website_employee_templates_1.xml',
        'views/website_employee_templates.xml',
        'data/cv_cron.xml',
    ],
    'test': [
        'tests/test_cv_parser.py',
    ],
    'assets': {
        'web.assets_backend': [
            'cv_importer/static/src/js/cv_importer_bus_listener.esm.js',
        ],       
        'web.assets_frontend': [
            'cv_importer/static/src/css/perfil_docente.css',
            'cv_importer/static/src/js/docencia_formatter.js',
            'cv_importer/static/src/js/subject_toggle.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}

