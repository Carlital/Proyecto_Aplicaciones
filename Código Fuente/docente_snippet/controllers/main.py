from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class DocenteSnippetController(http.Controller):

    @http.route('/docente_snippet/filtro_docentes', type='json', auth='public', website=True)
    def filtro_docentes(self, carrera_id=None, nombre=None, page=1, limit=10):
        domain = []
        offset = (int(page) - 1) * limit

        try:
            carrera_id_int = int(carrera_id)
            domain.append(('x_carrera', '=', carrera_id_int))
        except (ValueError, TypeError):
            _logger.warning("[DocenteSnippet] carrera_id no es un número válido: %s", carrera_id)

        if nombre:
            domain.append(('name', 'ilike', nombre))

        try:
            empleados_total = request.env['hr.employee'].sudo().search_count(domain)
            empleados = request.env['hr.employee'].sudo().search(domain, offset=offset, limit=limit)
        except Exception as e:
            _logger.error("Error ejecutando búsqueda de empleados: %s", e)
            raise

        html_resultado = ''
        for emp in empleados:
            img_url = f"/web/image/hr.employee/{emp.id}/image_1920"
            docente_url = f"/docente/{emp.identification_id}" if emp.identification_id else '#'
            correo = emp.work_email or emp.private_email or ''
            html_resultado += f'''
                <div class="col-md-12 mb-3">
                    <div class="d-flex align-items-center border rounded p-2">
                        <img src="{img_url}" class="rounded" style="height:60px;width:60px;object-fit:cover;" alt=""/>
                        <div class="ps-3">
                            <div><strong>{emp.name}</strong></div>
                            <div class="text-muted" style="font-size:0.9em;">{correo}</div>
                        </div>
                        <div class="ms-auto">
                            <a href="{docente_url}" target="_blank" rel="noopener noreferrer">
                                <i class="fa fa-link" style="font-size:24px;color:#00aaff;"></i>
                            </a>
                        </div>
                    </div>
                </div>
            '''

        pagination_html = '<nav><ul class="pagination justify-content-center">'
        total_pages = -(-empleados_total // limit)
        for p in range(1, total_pages + 1):
            active = ' active' if p == int(page) else ''
            pagination_html += f'<li class="page-item{active}"><a class="page-link docente-page" href="#" data-page="{p}">{p}</a></li>'
        pagination_html += '</ul></nav>'

        return {
            'html': html_resultado,
            'pagination': pagination_html
        }
