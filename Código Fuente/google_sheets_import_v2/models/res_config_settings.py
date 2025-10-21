from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    gs_brand_primary_color = fields.Char(string="Color primario (Sheets Import)")
    gs_brand_secondary_color = fields.Char(string="Color secundario (Sheets Import)")
    gs_brand_stylesheet = fields.Text(string="CSS adicional (Sheets Import)")

    def set_values(self):
        super().set_values()
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('google_sheets_import.primary_color', self.gs_brand_primary_color or '')
        params.set_param('google_sheets_import.secondary_color', self.gs_brand_secondary_color or '')
        params.set_param('google_sheets_import.stylesheet', self.gs_brand_stylesheet or '')

    @api.model
    def get_values(self):
        res = super().get_values()
        params = self.env['ir.config_parameter'].sudo()
        res.update(
            gs_brand_primary_color=params.get_param('google_sheets_import.primary_color', default="#004b8d"),
            gs_brand_secondary_color=params.get_param('google_sheets_import.secondary_color', default="#f2a900"),
            gs_brand_stylesheet=params.get_param('google_sheets_import.stylesheet', default=""),
        )
        return res
