from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

import logging

_logger = logging.getLogger(__name__)

class CvMaterias(models.Model):
    _name = "cv.materias"
    _description = "Materias"
    _order = "carrera_id, asignatura"

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

    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee / Instructor",
        required=True,
        ondelete="cascade",
        index=True,
        help="Employee who taught this course"
    )

    asignatura = fields.Char(
        string="Course Name",
        required=True,
        index=True,
        help="Full name of the course or subject"
    )

    course_code = fields.Char(
        string="Course Code",
        help="Official course code (e.g., CS-101, MAT-202)"
    )

    carrera_id = fields.Many2one(
        "carrera",
        string="Carrera / Programa",
        required=False,
        ondelete='restrict',
        index=True,
        help="Academic program or career to which the course belongs"
    )

    facultad_id = fields.Many2one(
        "facultad",
        string="Facultad / Escuela",
        required=False,
        ondelete='restrict',
        help="Faculty or school (auto-filled from career)"
    )

    carrera_nombre = fields.Char(
        string='Nombre Carrera',
        compute='_compute_carrera_nombre',
        store=True
    )

    _sql_constraints = [
        ('unique_employee_asignatura_carrera',
         'UNIQUE(employee_id, asignatura, carrera_id)',
         'Ya existe esta materia para este empleado en esta carrera')
    ]
    
    @api.depends('carrera_id', 'carrera_id.name')
    def _compute_carrera_nombre(self):
        for record in self:
            try:
                if record.carrera_id and record.carrera_id.exists():
                    record.carrera_nombre = record.carrera_id.name
                else:
                    record.carrera_nombre = 'Sin carrera'
            except Exception as e:
                _logger.warning(f"Error computando carrera_nombre para materia {record.id}: {e}")
                record.carrera_nombre = 'Error'
    

    source = fields.Selection(
        [
            ("manual", "Manual"),
            ("import", "Import"),
        ],
        string="Source",
        required=True,
        default="manual",
        help="Origin of this materias activity record"
    )

    def _normalize_nulls_for_manual(self, vals):
        source = vals.get("source")
        if not source and self:
            source = self[0].source

        if source and source != "manual":
            return vals

        text_fields = ["asignatura", "course_code"]
        for field_name in text_fields:
            if field_name in vals and vals[field_name] in (None, ""):
                vals[field_name] = "N/A"

        return vals

    @api.model
    def create(self, vals):
        vals = self._normalize_nulls_for_manual(dict(vals))
        return super().create(vals)

    def write(self, vals):
        vals = self._normalize_nulls_for_manual(dict(vals))
        return super().write(vals)

    def name_get(self):
        """Override name_get to show course name (trimmed)."""
        result = []
        for record in self:
            name = record.asignatura
            if len(name) > 80:
                name = name[:77] + "..."
            result.append((record.id, name))
        return result
