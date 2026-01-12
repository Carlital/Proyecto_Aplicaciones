from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import date
from dateutil.relativedelta import relativedelta


class CvWorkExperience(models.Model):
    _name = "cv.work.experience"
    _description = "Work Experience"
    _order = "start_date desc, end_date desc"
    _rec_name = "position"

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
        string="Employee",
        required=True,
        ondelete="cascade",
        index=True,
        help="Employee who held this position"
    )

    position = fields.Char(
        string="Position",
        required=True,
        size=255,
        help="Job title or position name (e.g., 'Profesor Titular', 'Investigador Senior')"
    )

    company = fields.Char(
        string="Company / Institution",
        required=True,
        size=255,
        index=True,
        help="Name of the organization or institution"
    )

    department = fields.Char(
        string="Department",
        size=255,
        help="Department, faculty, or division within the organization"
    )

    start_date = fields.Date(
        string="Start Date",
        required=False,
        help="Date when the position started"
    )

    end_date = fields.Date(
        string="End Date",
        help="Date when the position ended (leave empty if current)"
    )

    responsibilities = fields.Text(
        string="Responsibilities / Achievements",
        help="Description of main responsibilities, projects, or achievements in this role"
    )

    duration_months = fields.Integer(
        string="Duration (months)",
        compute="_compute_duration_months",
        store=True,
        help="Duration of employment in months (computed from dates). "
             "Value -1 is used as dummy when dates are unknown."
    )

    source = fields.Selection(
        [
            ("manual", "Manual"),
            ("import", "Import"),
        ],
        string="Source",
        default="manual",
        required=True,
        help="Origin of this data record"
    )

    display_period = fields.Char(
        string="Period",
        compute="_compute_display_period",
        store=True,
        help="Formatted display of the employment period"
    )

    _sql_constraints = [
        (
            "check_start_year_reasonable",
            "CHECK(start_date IS NULL OR EXTRACT(YEAR FROM start_date) >= 1950)",
            "Start year must be 1950 or later.",
        ),
        (
            "check_duration_months_range",
            "CHECK(duration_months IS NULL OR duration_months >= -1)",
            "Duration (months) must be -1 (dummy), NULL or zero/positive.",
        ),
    ]


    @api.depends("start_date", "end_date")
    def _compute_duration_months(self):
        for record in self:
            if not record.start_date:
                record.duration_months = -1
                continue

            if not record.end_date:
                end = date.today()
            else:
                end = record.end_date

            delta = relativedelta(end, record.start_date)
            record.duration_months = delta.years * 12 + delta.months

    @api.depends("start_date", "end_date")
    def _compute_display_period(self):
        """Compute a formatted string for the employment period."""
        for record in self:
            if not record.start_date:
                record.display_period = "N/A"
                continue

            start_str = record.start_date.strftime("%m/%Y")

            if record.end_date:
                end_str = record.end_date.strftime("%m/%Y")
            else:
                end_str = "Present"

            record.display_period = f"{start_str} - {end_str}"


    @api.constrains("start_date", "end_date")
    def _check_date_validity(self):
        """Validate that end_date is after start_date."""
        for record in self:
            if record.start_date and record.end_date:
                if record.end_date < record.start_date:
                    raise ValidationError(
                        _("End date cannot be earlier than start date.\n"
                          f"Position: {record.position}\n"
                          f"Company: {record.company}\n"
                          f"Start: {record.start_date}\n"
                          f"End: {record.end_date}")
                    )

    @api.constrains("start_date")
    def _check_start_date_reasonable(self):
        """Validate that start_date is not too far in the past."""
        for record in self:
            if record.start_date and record.start_date.year < 1950:
                raise ValidationError(
                    _("Start date seems unrealistic (before 1950).\n"
                      f"Position: {record.position}\n"
                      f"Start Date: {record.start_date}")
                )

    def name_get(self):
        """Override name_get to show position + company."""
        result = []
        for record in self:
            name = f"{record.position}"
            if record.company:
                name += f" @ {record.company}"
            if record.display_period:
                name += f" ({record.display_period})"
            result.append((record.id, name))
        return result
