# -*- coding: utf-8 -*-
{
    "name": "Snippet Lista Docentes",
    "version": "1.0",
    "summary": "Snippet para mostrar lista de docentes con imagen y enlace",
    "category": "Website",
    "author": "Odoo Specialist",
    "depends": ["website", "hr"],
    "data": [
        "views/snippet_template.xml",
        "views/snippet_tabs_verticales.xml",
        "views/snippet_tabs_horizontales.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "docente_snippet/static/src/js/snippet_docente_filter.js",
            "docente_snippet/static/src/css/docente_list.css",
            "docente_snippet/static/src/css/tabs_verticales.css",
            "docente_snippet/static/src/css/tabs_horizontales.css",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False 
}
