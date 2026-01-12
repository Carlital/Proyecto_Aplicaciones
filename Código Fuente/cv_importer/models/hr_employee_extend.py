# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class HrEmployeeExtend(models.Model):
    _inherit = 'hr.employee'

    # Permitir que docentes/admin institucionales consulten la cédula sin requerir grupo RRHH
    identification_id = fields.Char(
        groups="hr.group_hr_user,google_sheets_import.group_admin_institucional,google_sheets_import.group_docente"
    )

    # ============================================================
    # 1) TÍTULOS ACADÉMICOS
    # ============================================================

    cv_academic_degree_ids = fields.One2many(
        'cv.academic.degree',
        'employee_id',
        string='Academic Degrees',
        help='Normalized list of academic degrees obtained by this employee',
    )

    cv_academic_degree_count = fields.Integer(
        string='# Degrees',
        compute='_compute_cv_academic_degree_count',
        store=False,
    )



    @api.depends('cv_academic_degree_ids')
    def _compute_cv_academic_degree_count(self):
        """Count the number of academic degrees."""
        for record in self:
            try:
                record.cv_academic_degree_count = len(record.cv_academic_degree_ids)
            except Exception:
                # durante instalación / actualización, la tabla puede no existir
                record.cv_academic_degree_count = 0

    def action_view_academic_degrees(self):
        self.ensure_one()
        return {
            'name': f'Academic Degrees - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'cv.academic.degree',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {
                'default_employee_id': self.id,
                'default_source': 'manual',
            },
            'target': 'current',
        }

    # ============================================================
    # 2) EXPERIENCIA LABORAL
    # ============================================================

    cv_work_experience_ids = fields.One2many(
        'cv.work.experience',
        'employee_id',
        string='Work Experience',
        help='Normalized list of work experience and positions held by this employee',
    )

    cv_work_experience_count = fields.Integer(
        string='# Positions',
        compute='_compute_cv_work_experience_count',
        store=False,
    )

    cv_total_experience_months = fields.Integer(
        string='Total Experience (months)',
        compute='_compute_cv_total_experience',
        store=False,
        help='Sum of all work experience durations',
    )

    @api.depends('cv_work_experience_ids')
    def _compute_cv_work_experience_count(self):
        """Count the number of work experience records."""
        for record in self:
            try:
                record.cv_work_experience_count = len(record.cv_work_experience_ids)
            except Exception:
                record.cv_work_experience_count = 0

    @api.depends('cv_work_experience_ids.duration_months')
    def _compute_cv_total_experience(self):
        """Calculate total work experience in months."""
        for record in self:
            try:
                record.cv_total_experience_months = sum(
                    record.cv_work_experience_ids.mapped('duration_months')
                )
            except Exception:
                record.cv_total_experience_months = 0

    def action_view_work_experience(self):
        self.ensure_one()
        return {
            'name': f'Work Experience - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'cv.work.experience',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {
                'default_employee_id': self.id,
                'default_source': 'manual',
            },
            'target': 'current',
        }

    # ============================================================
    # 3) PUBLICACIONES
    # ============================================================

    cv_publication_ids = fields.One2many(
        'cv.publication',
        'employee_id',
        string='Publications',
        help='Normalized list of scientific publications authored or co-authored by this employee',
    )

    cv_publication_count = fields.Integer(
        string='# Publications',
        compute='_compute_cv_publication_count',
        store=False,
        help='Total number of publications',
    )

    @api.depends('cv_publication_ids')
    def _compute_cv_publication_count(self):
        """Count the number of publications."""
        for record in self:
            try:
                record.cv_publication_count = len(record.cv_publication_ids)
            except Exception:
                record.cv_publication_count = 0

    def action_view_publications(self):
        self.ensure_one()
        return {
            'name': f'Publications - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'cv.publication',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {
                'default_employee_id': self.id,
                'default_source': 'manual',
            },
            'target': 'current',
        }

    # ============================================================
    # 4) PROYECTOS
    # ============================================================

    cv_project_ids = fields.One2many(
        'cv.project',
        'employee_id',
        string='Projects',
        help='Normalized list of research, development, and outreach projects',
    )

    cv_project_count = fields.Integer(
        string='# Projects',
        compute='_compute_cv_project_count',
        store=False,
        help='Total number of projects',
    )

    @api.depends('cv_project_ids')
    def _compute_cv_project_count(self):
        """Count the number of projects."""
        for record in self:
            try:
                record.cv_project_count = len(record.cv_project_ids)
            except Exception:
                record.cv_project_count = 0

    def action_view_projects(self):
        self.ensure_one()
        return {
            'name': f'Projects - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'cv.project',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {
                'default_employee_id': self.id,
                'default_source': 'manual',
            },
            'target': 'current',
        }

    # ============================================================
    # 5) CERTIFICACIONES / CAPACITACIONES
    # ============================================================

    cv_certification_ids = fields.One2many(
        'cv.certification',
        'employee_id',
        string='Certifications',
        help='Normalized list of certifications and continuous education',
    )

    cv_certification_count = fields.Integer(
        string='# Certifications',
        compute='_compute_cv_certification_count',
        store=False,
        help='Total number of certification records',
    )

    cv_total_certification_hours = fields.Integer(
        string='Total Certification Hours',
        compute='_compute_cv_total_certification_hours',
        store=False,
        help='Sum of duration_hours from all certification records',
    )

    @api.depends('cv_certification_ids')
    def _compute_cv_certification_count(self):
        """Count the number of certification records."""
        for record in self:
            try:
                record.cv_certification_count = len(record.cv_certification_ids)
            except Exception:
                record.cv_certification_count = 0

    @api.depends('cv_certification_ids.duration_hours')
    def _compute_cv_total_certification_hours(self):
        """Calculate total certification hours."""
        for record in self:
            try:
                total = 0
                for certification in record.cv_certification_ids:
                    if certification.duration_hours:
                        total += certification.duration_hours
                record.cv_total_certification_hours = total
            except Exception:
                record.cv_total_certification_hours = 0

    def action_view_certifications(self):
        self.ensure_one()
        return {
            'name': f'Certifications - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'cv.certification',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {
                'default_employee_id': self.id,
                'default_source': 'manual',
            },
            'target': 'current',
        }

    # ============================================================
    # 6) IDIOMAS
    # ============================================================

    cv_language_ids = fields.One2many(
        'cv.language',
        'employee_id',
        string='Languages',
        help='Normalized list of languages and proficiency levels',
    )

    language_count = fields.Integer(
        string='# Languages',
        compute='_compute_language_count',
        store=False,
        help='Number of languages known by the employee',
    )

    @api.depends('cv_language_ids')
    def _compute_language_count(self):
        """Count the number of languages."""
        for record in self:
            try:
                record.language_count = len(record.cv_language_ids)
            except Exception:
                record.language_count = 0

    def action_view_languages(self):
        self.ensure_one()
        return {
            'name': f'Languages - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'cv.language',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {
                'default_employee_id': self.id,
                'default_source': 'manual',
            },
            'target': 'current',
        }

    # ============================================================
    # 7) LOGROS / DISTINCIONES
    # ============================================================

    cv_logros_ids = fields.One2many(
        'cv.logros',
        'employee_id',
        string='Logros / Awards',
        help='Normalized list of awards, recognitions and logros',
    )

    cv_logros_count = fields.Integer(
        string='# Logros',
        compute='_compute_cv_logros_count',
        store=False,
        help='Number of logros received',
    )

    @api.depends('cv_logros_ids')
    def _compute_cv_logros_count(self):
        """Count the number of logros."""
        for record in self:
            try:
                record.cv_logros_count = len(record.cv_logros_ids)
            except Exception:
                record.cv_logros_count = 0

    def action_view_logros(self):
        self.ensure_one()
        return {
            'name': f'Logros - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'cv.logros',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {
                'default_employee_id': self.id,
                'default_source': 'manual',
            },
            'target': 'current',
        }

    # ============================================================
    # 8) DOCENCIA / MATERIAS
    # ============================================================

    cv_materias_ids = fields.One2many(
        'cv.materias',
        'employee_id',
        string='Materias',
        help='Normalized list of teaching activities (courses taught)',
    )

    cv_materias_count = fields.Integer(
        string='# Courses Taught',
        compute='_compute_cv_materias_count',
        store=False,
        help='Number of materias activities',
    )

    @api.depends('cv_materias_ids')
    def _compute_cv_materias_count(self):
        for record in self:
            try:
                record.cv_materias_count = len(record.cv_materias_ids)
            except Exception:
                record.cv_materias_count = 0

    def action_view_materias(self):
        self.ensure_one()
        return {
            'name': f'Materias - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'cv.materias',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {
                'default_employee_id': self.id,
                'default_source': 'manual',
            },
            'target': 'current',
        }

    # ============================================================
    # 9) MÉTRICAS ANUALES
    # ============================================================

    cv_yearly_metrics_ids = fields.One2many(
        'cv.yearly.metrics',
        'employee_id',
        string='Yearly Metrics',
        help='Annual aggregated metrics for academic performance tracking',
    )

    def action_view_yearly_metrics(self):
        self.ensure_one()
        return {
            'name': f'Yearly Metrics - {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'cv.yearly.metrics',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {
                'default_employee_id': self.id,
            },
            'target': 'current',
        }

    def action_recompute_yearly_metrics(self):
        # Placeholder para futura lógica de agregación anual
        for employee in self:
            _logger.info(f"Recompute yearly metrics for {employee.name} (not implemented yet)")
        return True

    # ============================================================
    # 10) HELPERS “OFICIALES” QUE USA cv.document
    #      (wrappers a tus helpers en español)
    # ============================================================

    # ----- Degrees -----

    def _apply_academic_degrees(self, degrees):
        """Wrapper oficial usado por cv.document → delega a _apply_educacion."""
        return self._apply_educacion(degrees)

    def _apply_educacion(self, educacion_list):
        """Crear cv.academic.degree desde lista de educación."""
        self.ensure_one()
        if not educacion_list or not isinstance(educacion_list, list):
            return 0

        created_count = 0

        for edu in educacion_list:
            if not isinstance(edu, dict):
                continue

            titulo = (edu.get("titulo") or "").strip()
            if not titulo or len(titulo) < 5:
                continue

            # Evitar duplicados por título
            existing = self.env["cv.academic.degree"].search([
                ("employee_id", "=", self.id),
                ("degree_title", "=ilike", titulo[:500]),
            ], limit=1)

            if existing:
                _logger.debug(f"   ⏭️  Degree already exists: {titulo[:50]}...")
                continue

            # Mapear nivel → selection de cv.academic.degree
            # Opciones válidas:
            #  primara / secundaria, / tecnico / tercer nivel / cuarto nivel / no especificado
            nivel_raw = (edu.get("nivel") or "").upper()
            degree_type = "no especificado"

            if "primar" in nivel_raw:
                degree_type = "primaria"
            elif "secund" in nivel_raw or "bachiller" in nivel_raw:
                degree_type = "secundaria"   # ⚠️ ojo que en tu modelo hay coma
            elif "tecn" in nivel_raw:
                degree_type = "tecnico"
            elif "tercer" in nivel_raw or "ingenier" in nivel_raw or "licenci" in nivel_raw:
                degree_type = "tercer nivel"
            elif "cuarto" in nivel_raw or "maestr" in nivel_raw or "master" in nivel_raw or "postgr" in nivel_raw:
                degree_type = "cuarto nivel"

            try:
                self.env["cv.academic.degree"].create({
                    "employee_id": self.id,
                    "degree_type": degree_type,
                    "degree_title": titulo[:500],
                    "institution": (edu.get("institucion") or "Unknown")[:255],
                    "source": "import",
                })
                created_count += 1
            except Exception as e:
                _logger.warning(f"   ⚠️ Error creating academic degree: {str(e)[:100]}")

        _logger.info(
            f"   📚 Educación: {created_count} created, {len(educacion_list) - created_count} skipped"
        )
        return created_count

    # ----- Experiencia -----

    def _apply_work_experience(self, experience):
        """Wrapper oficial usado por cv.document → delega a _apply_experiencia."""
        return self._apply_experiencia(experience)

    def _apply_experiencia(self, experiencia_list):
        self.ensure_one()
        if not experiencia_list or not isinstance(experiencia_list, list):
            return 0

        created_count = 0

        from datetime import date

        for exp in experiencia_list:
            if not isinstance(exp, dict):
                continue

            cargo = (exp.get("cargo") or "").strip()
            if not cargo or len(cargo) < 3:
                continue

            existing = self.env["cv.work.experience"].search([
                ("employee_id", "=", self.id),
                ("position", "=ilike", cargo[:255]),
            ], limit=1)

            if existing:
                continue

            fecha_inicio_str = (exp.get("fecha_inicio") or "").strip()
            fecha_fin_str = (exp.get("fecha_fin") or "").strip()
            start_date = None
            end_date = None

            if fecha_inicio_str:
                try:
                    if len(fecha_inicio_str) == 7:  # YYYY-MM
                        year, month = fecha_inicio_str.split("-")
                        start_date = date(int(year), int(month), 1)
                    elif len(fecha_inicio_str) == 4:  # YYYY
                        start_date = date(int(fecha_inicio_str), 1, 1)
                except Exception:
                    start_date = None

            if fecha_fin_str and "actual" not in fecha_fin_str.lower():
                try:
                    if len(fecha_fin_str) == 7:
                        year, month = fecha_fin_str.split("-")
                        end_date = date(int(year), int(month), 1)
                    elif len(fecha_fin_str) == 4:
                        end_date = date(int(fecha_fin_str), 12, 31)
                except Exception:
                    end_date = None

            if not start_date:
                continue

            try:
                self.env["cv.work.experience"].create({
                    "employee_id": self.id,
                    "position": cargo[:255],
                    "company": (exp.get("institucion") or "Unknown")[:255],
                    "start_date": start_date,
                    "end_date": end_date,
                    "responsibilities": (exp.get("descripcion") or "")[:1000],
                    "source": "import",
                })
                created_count += 1
            except Exception as e:
                _logger.warning(f"   ⚠️  Error creating experience: {str(e)[:100]}")

        _logger.info(
            f"   💼 Experiencia: {created_count} created, {len(experiencia_list) - created_count} skipped"
        )
        return created_count

    # ----- Certificaciones -----

    def _apply_certifications(self, certifications):
        """Wrapper oficial usado por cv.document → delega a _apply_certificaciones."""
        return self._apply_certificaciones(certifications)

    def _apply_certificaciones(self, certificaciones_list):
        self.ensure_one()
        if not certificaciones_list or not isinstance(certificaciones_list, list):
            return 0

        created_count = 0

        for cert in certificaciones_list:
            if not isinstance(cert, dict):
                continue

            nombre = (cert.get("descripcion") or "").strip()
            if not nombre or len(nombre) < 5:
                continue

            existing = self.env["cv.certification"].search([
                ("employee_id", "=", self.id),
                ("certification_name", "=ilike", nombre[:500]),
            ], limit=1)

            if existing:
                continue

            horas_str = (cert.get("horas") or "").strip()
            duration_hours = None
            if horas_str:
                try:
                    duration_hours = int(horas_str)
                except Exception:
                    duration_hours = None

            tipo_raw = (cert.get("tipo") or "").lower()
            # Opciones válidas en modelo: approve / professional_development / other
            if "aprob" in tipo_raw:
                certification_type = "approve"
            elif any(x in tipo_raw for x in ["desarrollo", "actualiz", "capacit", "formacion", "formación"]):
                certification_type = "professional_development"
            else:
                certification_type = "other"

            try:
                self.env["cv.certification"].create({
                    "employee_id": self.id,
                    "certification_name": nombre[:500],
                    "institution": (cert.get("institucion") or "Unknown")[:255],
                    "certification_type": certification_type,
                    "duration_hours": duration_hours,
                    "source": "import",
                })
                created_count += 1
            except Exception as e:
                _logger.warning(f"   ⚠️  Error creating certification: {str(e)[:100]}")

        _logger.info(
            f"   🎓 Certificaciones: {created_count} created, {len(certificaciones_list) - created_count} skipped"
        )
        return created_count

    # ----- Materias -----

    def _apply_materias(self, materias_list):
        self.ensure_one()
        if not materias_list or not isinstance(materias_list, list):
            return 0

        created_count = 0

        for mat in materias_list:
            if not isinstance(mat, dict):
                continue

            asignatura = (mat.get("asignatura") or mat.get("materia") or "").strip()
            if not asignatura or len(asignatura) < 3:
                continue

            existing = self.env["cv.materias"].search([
                ("employee_id", "=", self.id),
                ("asignatura", "=ilike", asignatura[:255]),
            ], limit=1)

            if existing:
                continue

            try:
                self.env["cv.materias"].create({
                    "employee_id": self.id,
                    "asignatura": asignatura[:255],
                    "source": "import",
                })
                created_count += 1
            except Exception as e:
                _logger.warning(f"   ⚠️  Error creating materias activity: {str(e)[:100]}")

        _logger.info(
            f"   👨‍🏫 Materias: {created_count} created, {len(materias_list) - created_count} skipped"
        )
        return created_count

    # ----- Proyectos -----

    def _apply_projects(self, projects):
        """Wrapper oficial usado por cv.document → delega a _apply_proyectos."""
        return self._apply_proyectos(projects)

    def _apply_proyectos(self, proyectos_list):
        self.ensure_one()
        if not proyectos_list or not isinstance(proyectos_list, list):
            return 0

        created_count = 0
        from datetime import date

        for proj in proyectos_list:
            if not isinstance(proj, dict):
                continue

            titulo = (proj.get("titulo") or "").strip()
            if not titulo or len(titulo) < 10:
                continue

            existing = self.env["cv.project"].search([
                ("employee_id", "=", self.id),
                ("project_title", "=ilike", titulo[:500]),
            ], limit=1)

            if existing:
                continue

            tipo_raw = (proj.get("tipo") or "").lower()
            # Opciones válidas en modelo:
            # investigacion_e_innovacion / vinculacion / servicio_comunitario / docencia / otro
            if any(x in tipo_raw for x in ["vincul", "vinculación"]):
                project_type = "vinculacion"
            elif any(x in tipo_raw for x in ["comunitar", "servicio"]):
                project_type = "servicio_comunitario"
            elif "docen" in tipo_raw:
                project_type = "docencia"
            elif any(x in tipo_raw for x in ["innovacion", "innovación", "investig"]):
                project_type = "investigacion_e_innovacion"
            else:
                project_type = "otro"

            start_str = (proj.get("fecha_inicio") or "").strip()
            end_str = (proj.get("fecha_fin") or "").strip()
            start_date = None
            end_date = None

            if start_str:
                try:
                    if len(start_str) == 4:
                        start_date = date(int(start_str), 1, 1)
                except Exception:
                    start_date = None

            if end_str and end_str.isdigit():
                try:
                    end_date = date(int(end_str), 12, 31)
                except Exception:
                    end_date = None

            if not start_date:
                continue

            try:
                self.env["cv.project"].create({
                    "employee_id": self.id,
                    "project_title": titulo[:500],
                    "project_type": project_type,
                    "start_date": start_date,
                    "end_date": end_date,
                    "source": "import",
                })
                created_count += 1
            except Exception as e:
                _logger.warning(f"   ⚠️  Error creating project: {str(e)[:100]}")

        _logger.info(
            f"   🔬 Proyectos: {created_count} created, {len(proyectos_list) - created_count} skipped"
        )
        return created_count

    # ----- Publicaciones -----

    def _apply_publications(self, publications):
        """Wrapper oficial usado por cv.document → delega a _apply_publicaciones."""
        return self._apply_publicaciones(publications)

    def _apply_publicaciones(self, publicaciones_list):
        self.ensure_one()
        if not publicaciones_list or not isinstance(publicaciones_list, list):
            return 0

        created_count = 0

        for pub in publicaciones_list:
            if not isinstance(pub, dict):
                continue

            titulo = (pub.get("titulo") or "").strip()
            if not titulo or len(titulo) < 10:
                continue

            existing = self.env["cv.publication"].search([
                ("employee_id", "=", self.id),
                ("title", "=ilike", titulo[:500]),
            ], limit=1)

            if existing:
                continue

            tipo_raw = (pub.get("tipo") or "").lower()
            # Opciones válidas: article / book / thesis / other
            if "libro" in tipo_raw:
                pub_type = "book"
            elif "tesis" in tipo_raw:
                pub_type = "thesis"
            elif any(x in tipo_raw for x in ["articulo", "artículo", "paper", "congreso", "conferencia", "capitulo", "capítulo"]):
                pub_type = "article"
            else:
                pub_type = "other"

            year_str = (pub.get("fecha") or "").strip()
            pub_year = None
            if year_str:
                try:
                    pub_year = int(year_str[:4])
                except Exception:
                    pub_year = None

            if not pub_year:
                continue

            try:
                self.env["cv.publication"].create({
                    "employee_id": self.id,
                    "publication_type": pub_type,
                    "title": titulo[:500],
                    "publication_year": pub_year,
                    "source": "import",
                })
                created_count += 1
            except Exception as e:
                _logger.warning(f"   ⚠️  Error creating publication: {str(e)[:100]}")

        _logger.info(
            f"   📄 Publicaciones: {created_count} created, {len(publicaciones_list) - created_count} skipped"
        )
        return created_count

    # ----- Logros -----

    def _apply_logros(self, logros_list):
        self.ensure_one()
        if not logros_list or not isinstance(logros_list, list):
            return 0

        created_count = 0

        current_year = fields.Date.today().year

        for logro in logros_list:
            if not isinstance(logro, dict):
                continue

            nombre = (logro.get("descripcion") or logro.get("nombre") or "").strip()
            if not nombre or len(nombre) < 10:
                continue

            existing = self.env["cv.logros"].search([
                ("employee_id", "=", self.id),
                ("name", "=ilike", nombre[:255]),
            ], limit=1)

            if existing:
                continue

            tipo_raw = (logro.get("tipo") or "").lower()
            # Opciones válidas: artistico / deportivo / academico / laboral / other
            if any(x in tipo_raw for x in ["arte", "artíst", "cultural"]):
                dist_type = "artistico"
            elif "deport" in tipo_raw:
                dist_type = "deportivo"
            elif any(x in tipo_raw for x in ["acad", "investig", "cientif"]):
                dist_type = "academico"
            elif any(x in tipo_raw for x in ["labor", "profes", "trabajo"]):
                dist_type = "laboral"
            else:
                dist_type = "other"

            try:
                self.env["cv.logros"].create({
                    "employee_id": self.id,
                    "name": nombre[:255],
                    "tipo": dist_type,
                    "awarding_institution": (logro.get("institucion") or "Unknown")[:255],
                    "award_year": current_year,
                    "source": "import",
                })
                created_count += 1
            except Exception as e:
                _logger.warning(f"   ⚠️  Error creating logro: {str(e)[:100]}")

        _logger.info(
            f"   🏆 Logros: {created_count} created, {len(logros_list) - created_count} skipped"
        )
        return created_count

    # ----- Idiomas -----

    def _apply_languages(self, languages):
        """Wrapper oficial usado por cv.document → delega a _apply_idiomas."""
        return self._apply_idiomas(languages)

    def _apply_idiomas(self, idiomas_list):
        self.ensure_one()
        if not idiomas_list or not isinstance(idiomas_list, list):
            return 0

        Language = self.env["cv.language"].sudo()
        created_count = 0

        # Mapeo nivel → porcentajes (igual que _onchange_proficiency_level)
        level_to_perc = {
            "native": {"w": 100, "s": 100},
            "C2":    {"w": 95,  "s": 95},
            "C1":    {"w": 85,  "s": 90},
            "B2":    {"w": 75,  "s": 80},
            "B1":    {"w": 65,  "s": 70},
            "A2":    {"w": 45,  "s": 50},
            "A1":    {"w": 25,  "s": 30},
        }

        def _level_from_percentages(w, s):
            """Replica _onchange_percentages_to_level de CvLanguage."""
            if w in (None, -1) or s in (None, -1):
                return None
            m = min(w, s)
            if m >= 98:
                return "native"
            elif m >= 95:
                return "C2"
            elif m >= 85:
                return "C1"
            elif m >= 75:
                return "B2"
            elif m >= 60:
                return "B1"
            elif m >= 45:
                return "A2"
            else:
                return "A1"

        def _parse_int(value):
            if value in (None, "", False):
                return None
            try:
                return int(value)
            except Exception:
                return None

        for lang in idiomas_list:
            if not isinstance(lang, dict):
                continue

            idioma = (lang.get("idioma") or lang.get("language_name") or "").strip()
            if not idioma or len(idioma) < 3:
                continue

            # Evitar duplicados para este empleado + idioma
            existing = Language.search([
                ("employee_id", "=", self.id),
                ("language_name", "=ilike", idioma),
            ], limit=1)
            if existing:
                continue

            # 1) Intentar obtener porcentajes del JSON
            w = _parse_int(lang.get("writing_level"))
            s = _parse_int(lang.get("speaking_level"))

            nivel = None

            if w is not None and s is not None:
                # Si tenemos ambos porcentajes, calculamos nivel igual que en el modelo
                nivel = _level_from_percentages(w, s)

            # 2) Si no hay porcentajes válidos, usar el texto para inferir nivel
            if not nivel:
                nivel_raw = (
                    (lang.get("hablado") or "").strip()
                    or (lang.get("escrito") or "").strip()
                    or (lang.get("nivel") or "").strip()
                ).lower()

                if "nativ" in nivel_raw or "materna" in nivel_raw:
                    nivel = "native"
                elif "c2" in nivel_raw:
                    nivel = "C2"
                elif "c1" in nivel_raw:
                    nivel = "C1"
                elif "b2" in nivel_raw or "intermedio alto" in nivel_raw:
                    nivel = "B2"
                elif "b1" in nivel_raw or "intermedio" in nivel_raw:
                    nivel = "B1"
                elif "a2" in nivel_raw or "básico" in nivel_raw or "basico" in nivel_raw:
                    nivel = "A2"
                elif "a1" in nivel_raw or "principiante" in nivel_raw:
                    nivel = "A1"
                else:
                    nivel = "B2"  # default razonable

            # 3) Si no tenemos porcentajes, asignarlos según el nivel (igual que onchange)
            if w is None or s is None:
                perc = level_to_perc.get(nivel, {"w": 75, "s": 80})
                if w is None:
                    w = perc["w"]
                if s is None:
                    s = perc["s"]

            try:
                Language.create({
                    "employee_id": self.id,
                    "language_name": idioma[:100],
                    "proficiency_level": nivel,
                    "writing_level": w,
                    "speaking_level": s,
                    "source": "import",
                })
                created_count += 1
            except Exception as e:
                _logger.warning(f"   ⚠️  Error creating language: {str(e)[:200]}")

        _logger.info(
            f"   🌐 Idiomas: {created_count} created, {len(idiomas_list) - created_count} skipped"
        )
        return created_count

    # ============================================================
    # 11) WRAPPERS _apply_parsed_* (para compatibilidad)
    # ============================================================

    def _apply_parsed_degrees(self, degrees):
        return self._apply_academic_degrees(degrees)

    def _apply_parsed_experience(self, experience):
        return self._apply_work_experience(experience)

    def _apply_parsed_publications(self, publications):
        return self._apply_publications(publications)

    def _apply_parsed_projects(self, projects):
        return self._apply_projects(projects)

    def _apply_parsed_certifications(self, certifications):
        return self._apply_certifications(certifications)

    def _apply_parsed_languages(self, languages):
        return self._apply_languages(languages)

    def _apply_parsed_logros(self, logros):
        return self._apply_logros(logros)

    def _apply_parsed_materias(self, materias):
        return self._apply_materias(materias)

    # ============================================================
    # 12) Cron: crear usuarios para docentes sin user_id
    # ============================================================
    @api.model
    def cron_create_docente_users(self):
        """
        Cron job para:
        1. Crear usuarios faltantes para empleados sin user_id
        2. Asignar grupo 'Internal User' a usuarios vinculados
        3. Actualizar cargo 'Docente' para empleados con usuario
        """
        docente_group = self.env.ref('google_sheets_import.group_docente', raise_if_not_found=False)
        group_user = self.env.ref('base.group_user', raise_if_not_found=False)
        
        if not docente_group or not group_user:
            _logger.warning("⚠️ Grupo docente o base.group_user no encontrado; cron omitido.")
            return False

        Users = self.env['res.users'].sudo()
        
        # CONTADORES
        created_users = 0
        updated_groups = 0
        updated_jobs = 0
        skipped = 0
        removed_from_group = 0
        errors = []

        # =================================================================
        # PARTE 1: Empleados que YA TIENEN usuario vinculado
        # =================================================================
        _logger.info("=" * 60)
        _logger.info("🔄 PARTE 1: Actualizando empleados con usuario existente")
        _logger.info("=" * 60)
        
        employees_with_user = self.search([
            ('user_id', '!=', False),
            ('active', '=', True),
        ])
        
        _logger.info(f"📊 Empleados con usuario encontrados: {len(employees_with_user)}")
        
        for emp in employees_with_user:
            user = emp.user_id
            
            # VALIDACIÓN CLAVE: ¿Tiene facultad?
            tiene_facultad = bool(emp.facultad)
            esta_en_grupo_docente = docente_group.id in user.groups_id.ids
            
            if tiene_facultad:
                # 1.1) Asegurar que tenga Internal User
                if group_user.id not in user.groups_id.ids:
                    try:
                        user.write({'groups_id': [(4, group_user.id)]})
                        _logger.info(f" Grupo Internal User agregado: {user.login}")
                        updated_groups += 1
                    except Exception as e:
                        error_msg = f"Error agregando grupo base a {user.login}: {str(e)}"
                        _logger.error(f"{error_msg}")
                        errors.append(error_msg)
                
                # 1.2) Asegurar que tenga grupo Docente (solo si tiene facultad)
                if not esta_en_grupo_docente:
                    try:
                        user.write({'groups_id': [(4, docente_group.id)]})
                        _logger.info(f"Grupo Docente agregado: {user.login} (Facultad: {emp.facultad.name})")
                        updated_groups += 1
                    except Exception as e:
                        error_msg = f"Error agregando grupo docente a {user.login}: {str(e)}"
                        _logger.error(f"{error_msg}")
                        errors.append(error_msg)
            
            else:
                # NO tiene facultad → remover del grupo docente si está
                if esta_en_grupo_docente:
                    try:
                        user.write({'groups_id': [(3, docente_group.id)]})  # (3, id) = remover
                        _logger.warning(f"Grupo Docente removido: {user.login} (SIN FACULTAD)")
                        removed_from_group += 1
                    except Exception as e:
                        error_msg = f"Error removiendo grupo docente de {user.login}: {str(e)}"
                        _logger.error(f"{error_msg}")
                        errors.append(error_msg)
            
            # 1.3) Actualizar cargo si no es Docente/Coordinador/Admin
            if emp.job_title not in ['Docente', 'Coordinador Académico', 'Administrador Institucional']:
                try:
                    emp._update_job_title_from_user()
                    _logger.info(f"Cargo actualizado: {emp.name} → {emp.job_title}")
                    updated_jobs += 1
                except Exception as e:
                    error_msg = f"Error actualizando cargo de {emp.name}: {str(e)}"
                    _logger.error(f"{error_msg}")
                    errors.append(error_msg)

        # =================================================================
        # PARTE 2: Empleados SIN usuario (crear nuevos)
        # =================================================================
        _logger.info("")
        _logger.info("=" * 60)
        _logger.info("PARTE 2: Creando usuarios para empleados sin user_id")
        _logger.info("=" * 60)
        
        employees_without_user = self.search([
            ('user_id', '=', False),
            ('active', '=', True),
            ('employee_type', '=', 'employee'),
        ])
        
        _logger.info(f"Empleados sin usuario encontrados: {len(employees_without_user)}")

        for emp in employees_without_user:
            # Determinar login (email o cédula)
            login_base = (emp.work_email or emp.identification_id or '').strip().lower()
            
            if not login_base:
                _logger.warning(f"Empleado {emp.name} sin email ni cédula; saltado")
                skipped += 1
                continue

            # 2.1) Verificar si ya existe usuario con ese login
            existing_user = Users.search([('login', '=', login_base)], limit=1)
            
            if existing_user:
                # Usuario ya existe, solo vincular
                _logger.info(f"Usuario existente encontrado para {emp.name}: {login_base}")
                
                try:
                    # Vincular empleado al usuario existente
                    emp.sudo().write({'user_id': existing_user.id})
                    
                    # Asegurar grupos
                    groups_to_add = []
                    if group_user.id not in existing_user.groups_id.ids:
                        groups_to_add.append(group_user.id)
                    if docente_group.id not in existing_user.groups_id.ids:
                        groups_to_add.append(docente_group.id)
                    
                    if groups_to_add:
                        existing_user.write({'groups_id': [(4, gid) for gid in groups_to_add]})
                        _logger.info(f"Grupos actualizados para usuario existente: {login_base}")
                    
                    # Actualizar cargo
                    emp._update_job_title_from_user()
                    
                    _logger.info(f"Empleado vinculado y cargo actualizado: {emp.name}")
                    updated_jobs += 1
                    
                except Exception as e:
                    error_msg = f"Error vinculando empleado {emp.name} a usuario existente: {str(e)}"
                    _logger.error(f"{error_msg}")
                    errors.append(error_msg)
                    
                continue

            # 2.2) No existe usuario, crear uno nuevo
            # Generar login único si es necesario
            login = login_base
            counter = 1
            while Users.search_count([('login', '=', login)]) > 0:
                login = f"{login_base}{counter}"
                counter += 1
                if counter > 100:  # Prevenir bucle infinito
                    _logger.error(f"No se pudo generar login único para {emp.name}")
                    skipped += 1
                    break
            
            if counter > 100:
                continue

            # Crear nuevo usuario
            try:
                user_vals = {
                    'name': emp.name or emp.display_name,
                    'login': login,
                    'email': emp.work_email or False,
                    'company_id': self.env.company.id,
                    'company_ids': [(6, 0, [self.env.company.id])],
                    'groups_id': [(6, 0, [docente_group.id, group_user.id])],
                }
                
                new_user = Users.with_context(no_reset_password=True).create(user_vals)
                
                # Vincular al empleado
                emp.sudo().write({'user_id': new_user.id})
                
                # Actualizar cargo
                emp._update_job_title_from_user()
                
                _logger.info(f"Nuevo usuario creado y vinculado: {login} → {emp.name}")
                created_users += 1
                
            except Exception as e:
                error_msg = f"Error creando usuario para {emp.name}: {str(e)}"
                _logger.error(f"{error_msg}")
                errors.append(error_msg)
                skipped += 1

        # =================================================================
        # REPORTE FINAL
        # =================================================================
        _logger.info("RESUMEN DEL CRON")
        _logger.info(f"Usuarios creados: {created_users}")
        _logger.info(f"Grupos actualizados: {updated_groups}")
        _logger.info(f"Cargos actualizados: {updated_jobs}")
        _logger.info(f"Saltados: {skipped}")
        _logger.info(f"Errores: {len(errors)}")
        
        if errors:
            _logger.error("=" * 60)
            _logger.error("ERRORES DETALLADOS:")
            for i, err in enumerate(errors, 1):
                _logger.error(f"  {i}. {err}")
        
        _logger.info("=" * 60)
        
        return True
    # ============================================================
    # 13) Salvaguarda de acceso: docentes solo ven su registro
    # ============================================================
    @api.model
    def search(self, args=None, offset=0, limit=None, order=None):
        args = list(args or [])

        ctx_uid = self._context.get('uid') or self.env.uid
        user = self.env['res.users'].browse(ctx_uid)
        args = list(args or [])

        is_docente = user.has_group('google_sheets_import.group_docente')
        has_broader_access = (
            user.has_group('google_sheets_import.group_admin_institucional')
            or user.has_group('google_sheets_import.group_coord_academico')
            or user.has_group('base.group_system')
            or user.has_group('base.group_erp_manager')
        )

        if is_docente and not has_broader_access:
            args.append(('user_id', '=', user.id))

        return super().search(args, offset=offset, limit=limit, order=order)

    # ============================================================
    # 14) ASIGNACIÓN AUTOMÁTICA DE CARGO SEGÚN GRUPO
    # ============================================================

    @api.model
    def create(self, vals):
        """Al crear empleado, asignar cargo según grupo del usuario si aplica"""
        employee = super(HrEmployeeExtend, self).create(vals)
        if employee.user_id:
            employee._update_job_title_from_user()
        return employee

    def write(self, vals):
        """Al actualizar empleado, revisar si cambió el usuario"""
        result = super(HrEmployeeExtend, self).write(vals)
        if 'user_id' in vals:
            for employee in self:
                if employee.user_id:
                    employee._update_job_title_from_user()
        return result

    def _update_job_title_from_user(self):
        """Asignar cargo automáticamente según el grupo del usuario vinculado"""
        self.ensure_one()
        
        if not self.user_id:
            return
        
        user = self.user_id
        
        # Determinar cargo según grupos (orden de prioridad)
        if user.has_group('google_sheets_import.group_admin_institucional'):
            new_title = 'Administrador Institucional'
        elif user.has_group('google_sheets_import.group_coord_academico'):
            new_title = 'Coordinador Académico'
        elif user.has_group('google_sheets_import.group_docente'):
            new_title = 'Docente'
        else:
            return  # No actualizar si no tiene ninguno de estos grupos
        
        # Solo actualizar si cambió o está vacío
        if not self.job_title or self.job_title != new_title:
            _logger.info(f"Cargo actualizado automáticamente: {self.name} → {new_title}")
            self.job_title = new_title