from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class WebsiteEmployeeCV(http.Controller):
    def _apply_security_headers(self, response):
        csp = (
            "default-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'self'; "
            "form-action 'self';"
        )
        response.headers['Content-Security-Policy'] = csp
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        return response

    def _render_404(self):
        template = request.env.ref('website.404', raise_if_not_found=False)
        if template:
            resp = request.render('website.404')
        else:
            resp = request.make_response("Página no disponible", status=404)
        return self._apply_security_headers(resp)

    @http.route(['/docente/<string:cedula>'], type='http', auth="public", website=True)
    def empleado_perfil_cv(self, cedula, **kw):
       
        empleado = request.env['hr.employee'].sudo().search([
            ('identification_id', '=', cedula)
        ], limit=1)

        if not empleado:
            return self._render_404()

        cv_publicado = request.env['cv.document'].sudo().search([
            ('employee_id', '=', empleado.id),
            ('state', '=', 'published'),
            ('x_website_published', '=', True),
        ], limit=1)

        if not cv_publicado:
            return self._render_404()

        titulos = request.env['cv.academic.degree'].sudo().search([
            ('employee_id', '=', empleado.id),
            ('active', '=', True),
            ('is_published', '=', True),
        ], order='degree_type desc, degree_title')

        degree_order = {
            'cuarto nivel': 4,
            'tercer nivel': 3,
            'tecnico': 2,
            'secundaria': 1,
            'primaria': 0,
            'no especificado': -1,
        }

        titulos_sorted = sorted(
            titulos,
            key=lambda t: degree_order.get(t.degree_type, -1),
            reverse=True
        )

        experiencia = request.env['cv.work.experience'].sudo().search([
            ('employee_id', '=', empleado.id),
            ('active', '=', True),
            ('is_published', '=', True),
        ], order='start_date desc')

        total_months = sum(exp.duration_months or 0 for exp in experiencia)
        experience_years = total_months // 12

        materias = request.env['cv.materias'].sudo().search([
            ('employee_id', '=', empleado.id),
            ('active', '=', True),
            ('is_published', '=', True),
        ], order='asignatura')

        materias_por_carrera = {}
        for m in materias:
            nombre = (
                m.carrera_id.name
                if m.carrera_id and m.carrera_id.exists()
                else "General"
            )
            materias_por_carrera.setdefault(nombre, []).append(m)

        certificaciones = request.env['cv.certification'].sudo().search([
            ('employee_id', '=', empleado.id),
            ('active', '=', True),
            ('is_published', '=', True),
        ], order='institution, certification_name')

        certificaciones_por_institucion = {}
        for c in certificaciones:
            inst = c.institution or "Institución no especificada"
            certificaciones_por_institucion.setdefault(inst, []).append(c)

        publicaciones = request.env['cv.publication'].sudo().search([
            ('employee_id', '=', empleado.id),
            ('active', '=', True),
            ('is_published', '=', True),
        ], order="publication_year desc, title")

        publicaciones_por_tipo = {
            'article': publicaciones.filtered(lambda p: p.publication_type == 'article'),
            'conference': publicaciones.filtered(lambda p: p.publication_type == 'conference'),
            'book': publicaciones.filtered(lambda p: p.publication_type == 'book'),
            'thesis': publicaciones.filtered(lambda p: p.publication_type == 'thesis'),
            'other': publicaciones.filtered(lambda p: p.publication_type == 'other'),
        }

        logros = request.env['cv.logros'].sudo().search([
            ('employee_id', '=', empleado.id),
            ('active', '=', True),
            ('is_published', '=', True),
        ])

        logros_por_tipo = {}
        for l in logros:
            logros_por_tipo.setdefault(l.tipo or "other", []).append(l)

        idiomas = request.env['cv.language'].sudo().search([
            ('employee_id', '=', empleado.id),
            ('active', '=', True),
            ('is_published', '=', True),
        ])

        cv_document = request.env['cv.document'].sudo().search([
            ('employee_id', '=', empleado.id),
            ('state', '=', 'processed')
        ], limit=1)

        cv_download_href = cv_document.cv_download_url if cv_document else None

        total_publicaciones = len(publicaciones)
        total_proyectos = request.env['cv.project'].sudo().search_count([
            ('employee_id', '=', empleado.id),
            ('active', '=', True),
            ('is_published', '=', True),
        ])

        presentacion = self._generar_presentacion_docente(
            empleado=empleado,
            titulos=titulos_sorted,
            experiencia_anios=experience_years,
            total_publicaciones=total_publicaciones,
            total_proyectos=total_proyectos,
        )

        template = 'cv_importer.employee_profile_base'
        alt = request.env.ref('cv_importer.perfil_docente_template', raise_if_not_found=False)
        if alt:
            template = 'cv_importer.perfil_docente_template'

        resp = request.render(template, {
            'empleado': empleado,
            'cv_download_href': cv_download_href,

            'titulos_academicos': titulos_sorted,
            'materias': materias,
            'materias_por_carrera': materias_por_carrera,

            'experiencia_laboral': experiencia,
            'experience_years': experience_years,
            'certificaciones': certificaciones,
            'certificaciones_por_institucion': certificaciones_por_institucion,

            'proyectos': request.env['cv.project'].sudo().search([
                ('employee_id', '=', empleado.id),
                ('active', '=', True),
                ('is_published', '=', True),
            ]),

            'publicaciones': publicaciones,
            'publicaciones_por_tipo': publicaciones_por_tipo,

            'logros': logros,
            'logros_por_tipo': logros_por_tipo,

            'idiomas': idiomas,

            'total_publicaciones': total_publicaciones,
            'total_proyectos': total_proyectos,
            'total_certificaciones': len(certificaciones),
            'total_logros': len(logros),

            'presentacion_generada': presentacion,
        })

        return self._apply_security_headers(resp)

    def _generar_presentacion_docente(
        self, empleado, titulos, experiencia_anios, total_publicaciones, total_proyectos
    ):
        try:
            titulo = "Profesional"
            if titulos:
                t = titulos[0]
                if t.degree_type == 'cuarto nivel':
                    titulo = t.degree_title or "Magíster"
                elif t.degree_type == 'tercer nivel':
                    titulo = t.degree_title or "Ingeniero"

            partes = [f"Soy {empleado.name}, {titulo}"]

            if empleado.job_title:
                partes.append(f"actualmente desempeñándome como {empleado.job_title}")

            try:
                if empleado.facultad and empleado.facultad.exists():
                    partes.append(f"en la facultad de {empleado.facultad.name}")
            except Exception as e:
                _logger.warning(f"Error accediendo a facultad en presentación: {e}")

            if experiencia_anios > 0:
                partes.append(f"Con {experiencia_anios} años de experiencia profesional")

            esp = set()
            for p in request.env['cv.project'].sudo().search([
                ('employee_id', '=', empleado.id)
            ], limit=3):
                if p.project_type == 'investigacion_e_innovacion':
                    esp.add("investigación e innovación")
                elif p.project_type == 'vinculacion':
                    esp.add("vinculación con la sociedad")

            if esp:
                partes.append("especializado en " + ", ".join(list(esp)[:2]))

            logros = []
            if total_publicaciones > 0:
                logros.append(f"{total_publicaciones} publicaciones científicas")
            if total_proyectos > 0:
                logros.append(f"{total_proyectos} proyectos de investigación")

            if logros:
                partes.append("He contribuido con " + " y ".join(logros))

            partes.append(
                "Mi compromiso es la excelencia académica y la formación integral de profesionales competentes"
            )

            return ". ".join(partes) + "."
        except Exception as e:
            _logger.error(f"Error presentacion: {e}")
            return f"Soy {empleado.name}, docente comprometido con la excelencia académica."