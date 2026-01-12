{
    'name': 'Importacion de empleados desde Google Sheets',
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
    'category': 'Recursos Humanos',
    'depends': ['base', 'hr', 'website', 'web'], 
    'external_dependencies': {
        'python': ['requests', 'Pillow'],
    },
    'data': [
        'security/employee_security.xml',
        'security/ir.model.access.csv',
        'security/cv_rules.xml',
        'views/res_users_facultad_views.xml',
        'views/res_users_inherit_views.xml',
        'views/employee_import_view.xml',
        'views/employee_cedulas_button.xml',
        'views/facultad_carrera.xml',
        'views/dataset_version_views.xml',
        'views/identification_fix_wizard_view.xml',
        'views/coord_facultad_wizard_view.xml',
        'views/import_wizard_view.xml',
    ],

    'installable': True,
    'auto_install': False,
    'application': False,  
}
