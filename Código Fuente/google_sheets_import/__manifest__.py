{
    'name': 'Google Sheets Employee Import',
    'version': '17.0.0.0',
    'description': '''
        Módulo para importación de datos de empleados desde Google Sheets.
        Características:
        - Importación segura de datos
        - Control de acceso por usuario
        - Validación de datos
        - Registro de auditoría
    ''',
    'author': 'Carla Lomas',
    'license': 'LGPL-3',
    'category': 'Human Resources',
    'depends': ['base', 'hr', 'website', 'web'], 
    'external_dependencies': {
        'python': ['requests'],
    },
    'data': [
        'security/employee_security.xml',
        'security/ir.model.access.csv',
        'security/cv_rules.xml',
        'views/employee_import_view.xml',
        'views/employee_cedulas_button.xml',
        'views/facultad_carrera.xml',
        'views/website_employee_templates.xml',
        'views/branding_settings_views.xml',
        'views/dataset_version_views.xml',
        'views/identification_fix_wizard_view.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'google_sheets_import/static/src/css/perfil_docente.css',
            'google_sheets_import/static/src/js/docencia_formatter.js',
            'google_sheets_import/static/src/scss/branding.scss',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,  
}