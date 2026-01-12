from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CvAcademicDegree(models.Model):
    _name = "cv.academic.degree"
    _description = "Academic Degree"

    employee_id = fields.Many2one(
        "hr.employee",
        required=True,
        ondelete="cascade",
        string="Employee",
    )

    active = fields.Boolean(
        string="Active",
        default=True,
        help="If unchecked, this materias activity will be archived"
    )

    is_published = fields.Boolean(
        string="Published",
        default=True,
        help="Published to website/public profile. Draft edits should set this to False."
    )

    degree_type = fields.Selection(
        selection=[
            ("primaria", "Primaria"),
            ("secundaria", "Educación Secundaria"),
            ("tecnico", "Técnico Superior"),
            ("tercer nivel", "Tercer Nivel"),
            ("cuarto nivel", "Cuarto Nivel"),
            ("no especificado", "No Especificado"),
        ],
        required=True,
        string="Degree Type",
    )

    degree_title = fields.Char(
        required=True,
        string="Degree Title",
    )

    institution = fields.Char(
        required=True,
        string="Institution",
    )

    source = fields.Selection(
        [
            ("manual", "Manual"),
            ("import", "Import"),
        ],
        default="manual",
        required=True,
        string="Source",
    )

    # NORMALIZACIÓN SOLO MANUAL

    def _normalize_manual_dummies(self, vals):
        source = vals.get("source")
        if not source and self:
            source = self[0].source

        if source and source != "manual":
            return vals

        sanitized = dict(vals)

        if "degree_title" in sanitized:
            if not (sanitized["degree_title"] or "").strip():
                sanitized["degree_title"] = "N/A"

        if "institution" in sanitized:
            if not (sanitized["institution"] or "").strip():
                sanitized["institution"] = "N/A"

        if "degree_type" in sanitized:
            if not sanitized["degree_type"]:
                sanitized["degree_type"] = "no especificado"

        return sanitized

    @api.model
    def create(self, vals):
        vals = self._normalize_manual_dummies(vals)
        return super().create(vals)

    def write(self, vals):
        vals = self._normalize_manual_dummies(vals)
        return super().write(vals)
