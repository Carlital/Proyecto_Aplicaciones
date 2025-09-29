{
    'name': 'Google Sheets Employee Import',
    'version': '17.0.0.0',
    'description': '',
    'author': 'Carla Lomas',
    'license': 'LGPL-3',
    'category': 'Human Resources',
    'depends': ['base', 'hr', 'website'],
    'data': [
        'security/ir.model.access.csv',
        'views/employee_import_view.xml',
        'views/employee_cedulas_button.xml',
        'views/facultad_carrera.xml',
        'views/website_employee_templates.xml'
    ],
    'assets': {
        'web.assets_frontend': [
            'google_sheets_import/static/src/css/perfil_docente.css',
            'google_sheets_import/static/src/js/docencia_formatter.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': True,
}