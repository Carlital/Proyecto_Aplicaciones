from odoo import http
from odoo.http import request

class WebsiteEmployee(http.Controller):

    @http.route(['/docente/<string:cedula>'], type='http', auth="public", website=True)
    def empleado_perfil(self, cedula, **kw):
        empleado = request.env['hr.employee'].sudo().search([('identification_id', '=', cedula)], limit=1)
        if not empleado:
            return request.render('website.404')

        return request.render('google_sheets_import.perfil_docente_template', {
            'empleado': empleado
        })
