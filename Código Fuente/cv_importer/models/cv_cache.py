from odoo import models, fields

class CvCache(models.Model):
    _name = 'cv.cache'
    _description = 'Cache para datos de CV'

    cedula = fields.Char('Cédula', required=True, index=True)
    data = fields.Text('Datos CV', required=True)
    create_date = fields.Datetime('Fecha creación', readonly=True)
