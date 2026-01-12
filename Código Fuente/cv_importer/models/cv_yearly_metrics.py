from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CvYearlyMetrics(models.Model):
    _name = "cv.yearly.metrics"
    _description = "Yearly Academic Metrics"
    _order = "year desc, employee_id"
    _rec_name = "display_name"

    # Campo active para archivado
    active = fields.Boolean(
        string="Active",
        default=True,
        help="If unchecked, this metrics record will be archived"
    )

    # Relación con empleado
    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        required=True,
        ondelete="cascade",
        index=True,
        help="Employee for whom these metrics are calculated"
    )

    # Año de referencia
    year = fields.Integer(
        string="Year",
        required=True,
        index=True,
        help="Reference year for the aggregated metrics"
    )

    # === PUBLICACIONES ===
    publications_count = fields.Integer(
        string="Total Publications",
        default=0,
        help="Total number of publications in this year"
    )

    indexed_publications_count = fields.Integer(
        string="Indexed Publications",
        default=0,
        help="Number of publications indexed in Scopus/WoS"
    )

    # === PROYECTOS ===
    projects_count = fields.Integer(
        string="Total Projects",
        default=0,
        help="Total number of projects in this year"
    )

    # === DISTINCIONES / LOGROS ===
    logros_count = fields.Integer(
        string="Logros",
        default=0,
        help="Numero de logros o distinciones recibidas en este año"
    )

    # === EXPERIENCIA ===
    years_of_experience = fields.Integer(
        string="Years of Experience",
        help="Total years of professional experience as of this year"
    )

    years_in_academia = fields.Integer(
        string="Years in Academia",
        help="Years of academic experience as of this year"
    )

    # === METADATOS ===
    last_computed_date = fields.Datetime(
        string="Last Computed",
        readonly=True,
        help="Date and time when these metrics were last computed"
    )

    computation_method = fields.Selection(
        [
            ("manual", "Manual Entry"),
            ("semi_automatic", "Semi-Automatic"),
        ],
        string="Computation Method",
        default="manual",
        help="Method used to calculate these metrics"
    )

    # Campo computed para display
    display_name = fields.Char(
        string="Display Name",
        compute="_compute_display_name",
        store=True
    )

    # SQL Constraints adicionales
    _sql_constraints = [
        (
            "employee_year_unique",
            "UNIQUE(employee_id, year)",
            "There can be only one record per employee and year."
        ),
        (
            "check_year_range",
            "CHECK(year >= 1950 AND year <= EXTRACT(YEAR FROM CURRENT_DATE) + 1)",
            "Year must be between 1950 and next year."
        ),
        (
            "check_publications_non_negative",
            "CHECK(publications_count >= 0)",
            "Publication counts cannot be negative."
        ),
    ]

    # =========================================================
    # DISPLAY NAME
    # =========================================================
    @api.depends("employee_id", "year")
    def _compute_display_name(self):
        """Compute display name for the record."""
        for record in self:
            if record.employee_id and record.year:
                record.display_name = f"{record.employee_id.name} - {record.year}"
            else:
                record.display_name = "New Metrics Record"

    # =========================================================
    # CONSTRAINTS
    # =========================================================
    @api.constrains("year", "publications_count", "projects_count", "logros_count")
    def _check_yearly_metrics_constraints(self):
        """Validate yearly metrics data."""
        current_year = fields.Date.today().year
        for rec in self:
            if rec.year < 1950 or rec.year > current_year + 1:
                raise ValidationError(
                    _("Year must be between 1950 and current year + 1.\n"
                      f"Employee: {rec.employee_id.name}\n"
                      f"Year: {rec.year}")
                )

            if rec.publications_count < 0:
                raise ValidationError(_("Publication counts cannot be negative."))

            if rec.logros_count < 0:
                raise ValidationError(_("Logros count cannot be negative."))

    # =========================================================
    # CÓMPUTO AUTOMÁTICO POR AÑO (SOLO SI HAY DATOS)
    # =========================================================

    @api.model
    def _compute_metrics_for_employee(self, employee):
        """
        Calcula las métricas por año para un empleado específico,
        SOLO para los años en los que tenga publicaciones o logros.
        """
        Publication = self.env["cv.publication"]
        Achievement = self.env["cv.achievement"]  # ajusta el nombre del modelo si es distinto

        # ---------- PUBLICACIONES POR AÑO ----------
        pub_groups = Publication.read_group(
            domain=[("employee_id", "=", employee.id)],
            fields=["id", "year"],
            groupby=["year"],
        )
        # Publicaciones indexadas (ej. Scopus/WoS)
        indexed_groups = Publication.read_group(
            domain=[
                ("employee_id", "=", employee.id),
                ("is_indexed", "=", True),
            ],
            fields=["id", "year"],
            groupby=["year"],
        )

        pubs_by_year = {}
        for g in pub_groups:
            year = g["year"]
            total = g["year_count"] if "year_count" in g else g.get("id_count", 0)
            pubs_by_year[year] = {
                "total": total or 0,
                "indexed": 0,
            }

        for g in indexed_groups:
            year = g["year"]
            total_indexed = g["year_count"] if "year_count" in g else g.get("id_count", 0)
            if year not in pubs_by_year:
                pubs_by_year[year] = {"total": 0, "indexed": 0}
            pubs_by_year[year]["indexed"] = total_indexed or 0

        # ---------- LOGROS POR AÑO ----------
        logros_groups = Achievement.read_group(
            domain=[("employee_id", "=", employee.id)],
            fields=["id", "year"],
            groupby=["year"],
        )
        logros_by_year = {}
        for g in logros_groups:
            year = g["year"]
            total = g["year_count"] if "year_count" in g else g.get("id_count", 0)
            logros_by_year[year] = total or 0

        # ---------- AÑOS EN LOS QUE SÍ HAY ALGO ----------
        # Conjunto de años donde haya al menos una publicación o un logro
        years_with_data = set(pubs_by_year.keys()) | set(logros_by_year.keys())

        if not years_with_data:
            # No tiene nada, no creamos métricas
            return

        now = fields.Datetime.now()

        for year in years_with_data:
            pub_info = pubs_by_year.get(year, {"total": 0, "indexed": 0})
            total_pubs = pub_info["total"]
            indexed_pubs = pub_info["indexed"]
            total_logros = logros_by_year.get(year, 0)

            # Si este año no tiene NADA (por si acaso), lo saltamos
            if total_pubs <= 0 and total_logros <= 0:
                continue

            metrics = self.search([
                ("employee_id", "=", employee.id),
                ("year", "=", year),
            ], limit=1)

            vals = {
                "employee_id": employee.id,
                "year": year,
                "publications_count": total_pubs,
                "indexed_publications_count": indexed_pubs,
                "logros_count": total_logros,
                # projects_count puedes calcularlo luego si tienes modelo de proyectos
                "last_computed_date": now,
                "computation_method": "semi_automatic",
            }

            if metrics:
                metrics.write(vals)
            else:
                self.create(vals)

    @api.model
    def action_compute_all_yearly_metrics(self):
        """
        Acción para recalcular las métricas de TODOS los empleados.
        Solo se crean registros para años donde sí haya info
        (publicaciones o logros).
        """
        employees = self.env["hr.employee"].search([])
        for emp in employees:
            self._compute_metrics_for_employee(emp)
        return True
