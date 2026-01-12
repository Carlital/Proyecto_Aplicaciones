from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import date


class CvPublication(models.Model):
    _name = "cv.publication"
    _description = "Scientific Publication"
    _order = "publication_year desc, title"
    _rec_name = "title"

    active = fields.Boolean(
        string="Active",
        default=True,
        help="If unchecked, this publication will be archived and hidden from most views"
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
        help="Employee who authored or co-authored this publication"
    )

    publication_type = fields.Selection(
        [
            ("article", "Artículo"),
            ("book", "Libro"),
            ("thesis", "Tesis"),
            ("congreso", "Congreso"),
            ("other", "Otro"),
        ],
        string="Publication Type",
        required=True,
        help="Type of scientific publication"
    )

    title = fields.Char(
        string="Title",
        required=True,
        size=500,
        index=True,
        help="Full title of the publication"
    )

    publication_year = fields.Integer(
        string="Publication Year",
        required=False,
        index=True,
        help="Year when the publication was released"
    )

    publication_date = fields.Date(
        string="Publication Date",
        help="Exact publication date (if available)"
    )

    is_indexed = fields.Boolean(
        string="Indexed in Database",
        default=False,
        help="True if the publication is indexed in Scopus, WoS, etc."
    )

    indexing_database = fields.Char(
        string="Indexing Database",
        size=255,
        help="Database where the publication is indexed (e.g., Scopus, Web of Science, Scielo, Latindex)"
    )

    language = fields.Selection(
        [
            ("es", "Español"),
            ("en", "Inglés"),
            ("pt", "Portugués"),
            ("fr", "Francés"),
            ("de", "Alemán"),
            ("other", "Otro"),
        ],
        string="Idioma",
        default="other",
        help="Idioma de la publicación"
    )

    source = fields.Selection(
        [
            ("manual", "Manual"),
            ("import", "N8N Import"),
        ],
        string="Source",
        default="manual",
        required=True,
        help="Origin of this publication record"
    )

    citation_age_years = fields.Integer(
        string="Years Since Publication",
        compute="_compute_citation_age_years",
        store=False,
        help="Number of years since publication"
    )

    _sql_constraints = [
        (
            "check_publication_year_valid",
            "CHECK(publication_year IS NULL OR publication_year = -1 OR "
            "(publication_year >= 1900 AND publication_year <= EXTRACT(YEAR FROM CURRENT_DATE) + 1))",
            "Publication year must be between 1900 and next year, or -1 for unknown.",
        ),
    ]


    def _normalize_nulls_to_dummy(self, vals):
        source = vals.get("source")
        if not source and self:
            source = self[0].source

        if source and source != "manual":
            return vals

        if "publication_year" in vals and vals["publication_year"] in (None, ""):
            vals["publication_year"] = -1

        return vals

    @api.model
    def create(self, vals):
        vals = self._normalize_nulls_to_dummy(dict(vals))
        return super().create(vals)

    def write(self, vals):
        vals = self._normalize_nulls_to_dummy(dict(vals))
        return super().write(vals)


    @api.depends("publication_year")
    def _compute_citation_age_years(self):
        """Calculate years since publication (ignora dummy -1)."""
        current_year = date.today().year
        for record in self:
            if record.publication_year and record.publication_year > 0:
                record.citation_age_years = current_year - record.publication_year
            else:
                record.citation_age_years = 0

    @api.constrains("publication_year")
    def _check_publication_year_range(self):
        """Validate publication year is within reasonable range."""
        current_year = date.today().year
        for record in self:
            if record.publication_year in (None, -1):
                continue

            if record.publication_year < 1900 or record.publication_year > current_year + 1:
                raise ValidationError(
                    _("Publication year must be between 1900 and %(next_year)s.\n"
                      "Current value: %(year)s\n"
                      "Title: %(title)s") % {
                        'next_year': current_year + 1,
                        'year': record.publication_year,
                        'title': record.title
                    }
                )

    def name_get(self):
        """Override name_get to show title + year (solo si año real > 0)."""
        result = []
        for record in self:
            name = record.title
            if record.publication_year and record.publication_year > 0:
                name = f"[{record.publication_year}] {name}"
            if len(name) > 80:
                name = name[:77] + "..."
            result.append((record.id, name))
        return result
