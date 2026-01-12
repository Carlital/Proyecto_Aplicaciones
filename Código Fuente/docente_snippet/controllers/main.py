from odoo import http
from odoo.http import request
import logging
import base64

_logger = logging.getLogger(__name__)

class DocenteSnippetController(http.Controller):

    @http.route('/docente_snippet/imagen/<int:employee_id>', type='http', auth='public', website=True)
    def get_employee_image(self, employee_id, **kwargs):
        """Ruta pública para obtener imágenes de empleados"""
        try:
            employee = request.env['hr.employee'].sudo().browse(employee_id)
            if employee.exists() and employee.image_1920:
                image_data = base64.b64decode(employee.image_1920)
                headers = [
                    ('Content-Type', 'image/png'),
                    ('Content-Length', len(image_data)),
                    ('Cache-Control', 'public, max-age=604800'),
                ]
                return request.make_response(image_data, headers)
            else:
                # Retornar imagen placeholder si no existe
                return request.redirect('/web/static/img/placeholder.png')
        except Exception as e:
            _logger.error(f"Error al obtener imagen del empleado {employee_id}: {e}")
            return request.redirect('/web/static/img/placeholder.png')

    @http.route('/docente_snippet/filtro_docentes', type='json', auth='user', website=True)
    def filtro_docentes(self, carrera_id=None, nombre=None, page=1, limit=10):

        try:
            grupo_docente = request.env.ref('google_sheets_import.group_docente')
        except Exception as e:
            _logger.error("No se encontró el grupo 'google_sheets_import.group_docente': %s", e)
            return {
                'html': '<div class="alert alert-warning">Error: Grupo de docentes no encontrado</div>',
                'pagination': ''
            }

        domain = [
            ('user_id', '!=', False),  
            ('user_id.groups_id', 'in', [grupo_docente.id]),  
        ]
        
        offset = (int(page) - 1) * limit

        if carrera_id:
            try:
                carrera_id_int = int(carrera_id)
                domain.append(('carrera', '=', carrera_id_int))
            except (ValueError, TypeError):
                _logger.warning("[DocenteSnippet] carrera_id no es un número válido: %s", carrera_id)

        if nombre:
            domain.append(('name', 'ilike', nombre))

        try:
            # NO usar sudo() aquí - respetar las reglas de seguridad del usuario
            empleados_total = request.env['hr.employee'].search_count(domain)
            
            empleados = request.env['hr.employee'].search(
                domain, 
                offset=offset, 
                limit=limit,
                order='name asc'
            )
        except Exception as e:
            _logger.error("Error ejecutando búsqueda de empleados: %s", e)
            return {
                'html': '<div class="alert alert-danger">Error al cargar docentes</div>',
                'pagination': ''
            }

        html_resultado = ''
        if not empleados:
            html_resultado = '''
                <div class="col-12">
                    <div class="no-results">
                        <i class="fa fa-users"></i>
                        <h5 class="mt-3">No se encontraron docentes</h5>
                        <p class="text-muted">Intenta ajustar los filtros de búsqueda</p>
                    </div>
                </div>
            '''
        else:
            for emp in empleados:
                # Usar la ruta pública para las imágenes (esta ruta sí usa sudo internamente)
                img_url = f"/docente_snippet/imagen/{emp.id}"
                
                docente_url = f"/docente/{emp.identification_id}" if emp.identification_id else '#'
                correo = emp.work_email or emp.private_email or 'Sin correo'
                carrera_nombre = emp.carrera.name if emp.carrera else 'Sin carrera'
                
                btn_cv = f'''<a href="{emp.x_cv_url}" target="_blank" rel="noopener noreferrer" 
                           class="btn btn-cv" title="Ver CV">
                            <i class="fa fa-file-text"></i>
                        </a>''' if emp.x_cv_url else ''
                
                html_resultado += f'''
                    <div class="col-12">
                        <div class="docente-item">
                            <div class="docente-visual">
                                <img src="{img_url}" class="docente-avatar" alt="{emp.name}" onerror="this.src='/web/static/img/placeholder.png'"/>
                            </div>
                            <div class="docente-content">
                                <div class="docente-primary">
                                    <h5 class="docente-name">{emp.name}</h5>
                                    <span class="docente-badge">{carrera_nombre}</span>
                                </div>
                                <div class="docente-secondary">
                                    <i class="fa fa-envelope"></i> {correo}
                                </div>
                            </div>
                            <div class="docente-actions">
                                <a href="{docente_url}" target="_blank" rel="noopener noreferrer" 
                                   class="btn btn-profile">
                                    <i class="fa fa-user"></i> Ver Perfil
                                </a>
                                {btn_cv}
                            </div>
                        </div>
                    </div>
                '''

        pagination_html = ''
        if empleados_total > limit:
            total_pages = -(-empleados_total // limit)  
            current_page = int(page)
            
            pagination_html = '<ul class="pagination">'
            
            disabled_prev = ' disabled' if current_page <= 1 else ''
            pagination_html += f'''
                <li class="page-item{disabled_prev}">
                    <a class="page-link docente-page" href="#" data-page="{max(1, current_page - 1)}">
                        <i class="fa fa-chevron-left"></i> Anterior
                    </a>
                </li>
            '''
            
            start_page = max(1, current_page - 2)
            end_page = min(total_pages, current_page + 2)
            
            if start_page > 1:
                pagination_html += f'''
                    <li class="page-item">
                        <a class="page-link docente-page" href="#" data-page="1">1</a>
                    </li>
                '''
                if start_page > 2:
                    pagination_html += '<li class="page-item disabled"><span class="page-link">...</span></li>'
            
            for p in range(start_page, end_page + 1):
                active = ' active' if p == current_page else ''
                pagination_html += f'''
                    <li class="page-item{active}">
                        <a class="page-link docente-page" href="#" data-page="{p}">{p}</a>
                    </li>
                '''
            
            if end_page < total_pages:
                if end_page < total_pages - 1:
                    pagination_html += '<li class="page-item disabled"><span class="page-link">...</span></li>'
                pagination_html += f'''
                    <li class="page-item">
                        <a class="page-link docente-page" href="#" data-page="{total_pages}">{total_pages}</a>
                    </li>
                '''
            
            disabled_next = ' disabled' if current_page >= total_pages else ''
            pagination_html += f'''
                <li class="page-item{disabled_next}">
                    <a class="page-link docente-page" href="#" data-page="{min(total_pages, current_page + 1)}">
                        Siguiente <i class="fa fa-chevron-right"></i>
                    </a>
                </li>
            '''
            
            pagination_html += '</ul>'

        return {
            'html': html_resultado,
            'pagination': pagination_html
        }