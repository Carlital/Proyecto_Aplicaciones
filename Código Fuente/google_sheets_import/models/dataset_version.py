import hashlib
import json
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class GoogleSheetsDatasetVersion(models.Model):
    _name = 'google.sheets.dataset.version'
    _description = 'Versiones de Datasets Google Sheets'
    _order = 'import_datetime desc'
    _rec_name = 'name'

    name = fields.Char(required=True, index=True, help="Etiqueta legible (auto si se deja vacío).")
    sheet_url = fields.Char(required=True)
    sheet_gid = fields.Char(string="GID / Worksheet")
    import_datetime = fields.Datetime(default=lambda self: fields.Datetime.now(), index=True)
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user, readonly=True)
    row_count = fields.Integer()
    hash_sha256 = fields.Char(readonly=True, index=True)
    json_schema = fields.Text(help="Opcional: estructura inferida / encabezados.")
    meta_json = fields.Text(help="Metadata adicional (JSON).")
    notes = fields.Text()

    _sql_constraints = [
        ('uniq_hash', 'unique(hash_sha256)', 'Ya existe un registro con el mismo hash (contenido idéntico).')
    ]

    @api.model
    def _compute_rows_hash(self, raw_rows):
        # raw_rows puede ser lista de dicts o listas.
        normalized = []
        for r in raw_rows:
            if isinstance(r, dict):
                # orden estable de claves para hash consistente
                normalized.append({k: r[k] for k in sorted(r.keys())})
            else:
                normalized.append(r)
        blob = json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode('utf-8')
        return hashlib.sha256(blob).hexdigest(), blob

    @api.model
    def create_version_from_import(self, sheet_url, sheet_gid=None, raw_rows=None, meta=None):
        raw_rows = raw_rows or []
        if not sheet_url:
            raise ValidationError(_("sheet_url es requerido para crear una versión de dataset."))
        h, blob = self._compute_rows_hash(raw_rows)
        existing = self.search([('hash_sha256', '=', h)], limit=1)
        if existing:
            # actualizar import_datetime si ya existe
            existing.sudo().write({'import_datetime': fields.Datetime.now(), 'row_count': len(raw_rows)})
            return existing
        headers = []
        if raw_rows:
            sample = raw_rows[0]
            if isinstance(sample, dict):
                headers = sorted(sample.keys())
        record = self.create({
            'name': f"Import {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}",
            'sheet_url': sheet_url,
            'sheet_gid': sheet_gid,
            'row_count': len(raw_rows),
            'hash_sha256': h,
            'json_schema': json.dumps({'headers': headers}, ensure_ascii=False),
            'meta_json': json.dumps(meta or {}, ensure_ascii=False)
        })
        return record

    def action_view_rows_sample(self):
        self.ensure_one()
        if not self.meta_json:
            raise ValidationError(_("No hay metadata disponible."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Dataset Version'),
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
        }
