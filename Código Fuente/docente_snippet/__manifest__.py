# -*- coding: utf-8 -*-
{
    "name": "Snippet Lista Docentes",
    "version": "1.0",
    "summary": "Snippet para mostrar lista de docentes con imagen y enlace",
    "category": "Website",
    "author": "Carla Lomas",
    'depends': ['website', 'hr', 'google_sheets_import'],
    "data": [
        "views/snippet_template.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "docente_snippet/static/src/js/snippet_docente_filter.js",
            "docente_snippet/static/src/css/docente_list.css",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False 
}
