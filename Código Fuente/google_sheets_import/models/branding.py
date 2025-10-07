from odoo import models, fields, api

class GoogleSheetsBranding(models.Model):
    _name = 'google.sheets.branding'
    _description = 'Branding Institucional Google Sheets Import'
    _order = 'create_date desc'

    name = fields.Char(required=True, default="Tema Institucional")
    active = fields.Boolean(default=True)
    primary_color = fields.Char(default="#004b8d", help="Color principal (hex).")
    secondary_color = fields.Char(default="#f2a900", help="Color secundario (hex).")
    logo = fields.Binary(attachment=True)
    stylesheet_css = fields.Text(help="CSS adicional (sin <style>).")
    notes = fields.Text()

    @api.model
    def get_active_branding(self):
        rec = self.search([('active', '=', True)], limit=1)
        return rec or self.env[self._name]
