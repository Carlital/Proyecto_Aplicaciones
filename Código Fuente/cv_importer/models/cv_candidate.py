from odoo import models, fields, api
from odoo.exceptions import ValidationError

class CvCandidate(models.Model):
    _name = 'cv.candidate'
    _description = 'CV Candidate'

    name = fields.Char(string='Name', required=True)
    experience_years = fields.Integer(string='Years of Experience')

    @api.constrains('name')
    def _check_name_length(self):
        config = self.env['cv.config']
        for record in self:
            if record.name and (
                len(record.name) < config.MIN_NAME_LENGTH or 
                len(record.name) > config.MAX_NAME_LENGTH
            ):
                raise ValidationError(
                    f"Name must be between {config.MIN_NAME_LENGTH} and {config.MAX_NAME_LENGTH} characters"
                )

    @api.constrains('experience_years')
    def _check_experience_years(self):
        config = self.env['cv.config']
        for record in self:
            if record.experience_years is not None and (
                record.experience_years < config.MIN_EXPERIENCE_YEARS or
                record.experience_years > config.MAX_EXPERIENCE_YEARS
            ):
                raise ValidationError(
                    f"Experience years must be between {config.MIN_EXPERIENCE_YEARS} and {config.MAX_EXPERIENCE_YEARS}"
                )

    @api.model
    def import_cv_with_metrics(self, file_data, filename):
        """Importar CV con métricas de rendimiento"""
        import time
        start_time = time.time()
        file_size = len(file_data) if file_data else 0
        
        try:
            # ...existing import logic...
            candidate = self.import_cv(file_data, filename)
            
            # Registrar métrica exitosa
            self.env['cv.metrics'].record_import_metric(
                start_time=start_time,
                file_size=file_size,
                success=True,
                candidate_id=candidate.id if candidate else None
            )
            
            return candidate
            
        except Exception as e:
            # Registrar métrica de error
            self.env['cv.metrics'].record_import_metric(
                start_time=start_time,
                file_size=file_size,
                success=False,
                error_msg=str(e)
            )
            raise