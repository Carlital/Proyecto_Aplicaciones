# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class CvCertification(models.Model):
    _name = "cv.certification"
    _description = "Certification"
    _order = "certification_name"
    _rec_name = "certification_name"

    active = fields.Boolean(
        string="Active",
        default=True,
        help="If unchecked, this certification will be archived and hidden from most views"
    )

    is_published = fields.Boolean(
        string="Published",
        default=True,
        help="Published to website/public profile. Draft edits should set this to False."
    )

    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        required=True,
        ondelete="cascade",
        index=True,
        help="Employee who participated in this certification"
    )

    certification_type = fields.Selection(
        [
            ("approve", "Aprobación"),
            ("professional_development", "Desarrollo Profesional"),
            ("other", "Otro"),
        ],
        string="Certification Type",
        required=True,
        default="approve",
        index=True,
        help="Type or category of certification activity"
    )

    certification_name = fields.Char(
        string="Certification Name",
        required=True,
        size=500,
        index=True,
        help="Name of the course, certification activity"
    )

    certification_code = fields.Char(
        string="Certification Code",
        size=100,
        help="Official code or identifier of the certification (if applicable)"
    )

    institution = fields.Char(
        string="Institution",
        required=True,
        size=255,
        index=True,
        help="Institution or organization that delivered the certification"
    )

    duration_hours = fields.Integer(
        string="Duration (hours)",
        help="Total duration in hours (can be computed or entered manually)"
    )

    duration_days = fields.Integer(
        string="Duration (days)",
        help="Duration in days (computed from dates)"
    )

    source = fields.Selection(
        [
            ("manual", "Manual"),
            ("import", "Import"),
        ],
        string="Source",
        required=True,
        default="manual",
        help="Indicates how this certification record was created"
    )

    _sql_constraints = [
        (
            "check_duration_hours_range",
            "CHECK(duration_hours IS NULL OR duration_hours >= -1)",
            "Duration (hours) must be -1 (dummy), NULL or greater than zero.",
        ),
        (
            "check_duration_days_range",
            "CHECK(duration_days IS NULL OR duration_days >= -1)",
            "Duration (days) must be -1 (dummy), NULL or greater than zero.",
        ),
    ]

    # ============= NORMALIZACIÓN SOLO PARA SOURCE=MANUAL =============

    def _normalize_nulls_to_dummy(self, vals):
        """
        Convierte vacíos/None -> -1 SOLO cuando el registro es manual.
        Para source='import' no toca nada (eso ya lo hace CvDocument).
        """
        # Determinar source efectivo
        source = vals.get("source")
        if not source and self:
            # en write, si no viene en vals, uso el source del primer record
            source = self[0].source

        # Si es import, no tocamos nada
        if source and source != "manual":
            return vals

        # Solo para manual
        for field_name in ["duration_hours", "duration_days"]:
            if field_name in vals and vals[field_name] in (None, ""):
                vals[field_name] = -1
        return vals

    @api.model
    def create(self, vals):
        vals = self._normalize_nulls_to_dummy(dict(vals))
        return super().create(vals)

    def write(self, vals):
        vals = self._normalize_nulls_to_dummy(dict(vals))
        return super().write(vals)

    # ============= VALIDACIONES =============

    @api.constrains("duration_hours")
    def _check_duration_hours_valid(self):
        """Validate that duration_hours is positive for real values."""
        for record in self:
            # -1 o None = dummy/sin dato → no se valida rango
            if record.duration_hours in (None, -1):
                continue

            if record.duration_hours <= 0:
                raise ValidationError(
                    _("Duration (hours) must be greater than zero.\n"
                      f"Certification: {record.certification_name}\n"
                      f"Duration: {record.duration_hours}")
                )

    @api.constrains("duration_days")
    def _check_duration_days_valid(self):
        """Validate that duration_days is positive for real values."""
        for record in self:
            if record.duration_days in (None, -1):
                continue

            if record.duration_days <= 0:
                raise ValidationError(
                    _("Duration (days) must be greater than zero.\n"
                      f"Certification: {record.certification_name}\n"
                      f"Duration: {record.duration_days}")
                )

    def name_get(self):
        result = []
        for record in self:
            name = record.certification_name
            if len(name) > 80:
                name = name[:77] + "..."
            result.append((record.id, name))
        return result
