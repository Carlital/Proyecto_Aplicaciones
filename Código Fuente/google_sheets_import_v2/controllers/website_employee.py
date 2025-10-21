from odoo import http
from odoo.http import request

class WebsiteEmployee(http.Controller):

    @http.route(['/docente/<string:cedula>'], type='http', auth="public", website=True)
    def empleado_perfil(self, cedula, **kw):
        empleado = request.env['hr.employee'].sudo().search([('identification_id', '=', cedula)], limit=1)
        if not empleado:
            return request.render('website.404')

        # Construir enlace seguro de descarga desde adjunto si existe
        cv_download_href = None
        try:
            cv_doc = request.env['cv.document'].sudo().search([('employee_id', '=', empleado.id)], order='write_date desc', limit=1)
            if cv_doc and getattr(cv_doc, 'cv_attachment_id', False):
                att = cv_doc.cv_attachment_id.sudo()
                token = getattr(att, 'access_token', None)
                if not token:
                    # Generar token si el modelo lo soporta
                    try:
                        gen = request.env['ir.attachment']._generate_access_token() if hasattr(request.env['ir.attachment'], '_generate_access_token') else None
                        if gen:
                            att.write({'access_token': gen})
                            token = gen
                    except Exception:
                        token = None
                base = '/web/content/%s?download=1' % att.id
                if token:
                    base += '&access_token=%s' % token
                cv_download_href = base
        except Exception:
            pass

        return request.render('google_sheets_import.perfil_docente_template', {
            'empleado': empleado,
            'cv_download_href': cv_download_href,
        })
