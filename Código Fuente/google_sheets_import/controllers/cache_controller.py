import base64
import hashlib
from odoo import http
from odoo.http import request, Response

class GoogleSheetsCacheController(http.Controller):

    @http.route('/google_sheets_import/profile_image/<int:employee_id>', type='http', auth='public', methods=['GET'])
    def profile_image(self, employee_id, **kwargs):
        employee = request.env['hr.employee'].sudo().browse(employee_id)
        if not employee.exists() or not employee.image_1920:
            return Response(status=404)
        binary_b64 = employee.image_1920
        raw = base64.b64decode(binary_b64)
        etag = hashlib.sha256(raw).hexdigest()
        inm = request.httprequest.headers.get('If-None-Match')
        if inm == etag:
            return Response(status=304, headers=[('ETag', etag)])
        headers = [
            ('Content-Type', 'image/png'),
            ('Cache-Control', 'public, max-age=86400, immutable'),
            ('ETag', etag)
        ]
        return request.make_response(raw, headers)
