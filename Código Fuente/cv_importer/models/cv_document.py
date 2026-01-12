# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
import requests
import json
import traceback
from datetime import datetime, timedelta, date


_logger = logging.getLogger(__name__)

class CvDocument(models.Model):
    _name = 'cv.document'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Documento CV para procesamiento'
    _order = 'last_state_change asc'

    name = fields.Char(string='Nombre del Documento', required=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', required=True)
    cedula = fields.Char(string='Cédula', related='employee_id.identification_id', store=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('uploaded', 'Enviado a N8N'),
        ('processing', 'Procesando'),
        ('processed', 'Procesado'),
        ('error', 'Error'),
        ('coord_review', 'En revisión por coordinador'),
        ('published', 'Publicado'),
        ('rejected', 'Rechazado'),
    ], string='Estado', default='draft')


    x_coord_validation_notes = fields.Text(
        string='Observaciones del Coordinador',
        tracking=True
    )

    x_coord_validated_date = fields.Datetime(
        string='Fecha validación coordinador',
        readonly=True
    )

    x_coord_validated_by = fields.Many2one(
        'res.users',
        string='Validado por (Coordinador)',
        readonly=True
    )

    x_website_published = fields.Boolean(
        string='Publicado en Website',
        default=False,
        tracking=True
    )

    x_publication_date = fields.Datetime(
        string='Fecha de Publicación',
        readonly=True
    )

    # Botones de acción
    def action_submit_for_coord_review(self):
        """Docente solicita revisión y genera snapshot de historial."""
        self.ensure_one()
        if not self.env.user.has_group('google_sheets_import.group_docente'):
            return

        # Crear snapshot en historial (versión no publicada)
        self._create_history_snapshot(is_published=False, state='coord_review', coord_comment=False)
        self.state = 'coord_review'
        # Notificar a coordinadores de la misma facultad
        self._notify_coordinadores(_("Se solicita revisión del CV de %s") % self.employee_id.name)

    def action_coord_approve(self):
            """Coordinador aprueba y el CV se publica automáticamente"""
            self.ensure_one()

            if not self.env.user.has_group('google_sheets_import.group_coord_academico'):
                raise UserError(_("Solo un coordinador académico puede aprobar este CV."))

            if self.state != 'coord_review':
                raise UserError(_("Solo se pueden aprobar CV que están en revisión por coordinador."))

            now = fields.Datetime.now()
            self.write({
                'state': 'published',
                'x_coord_validated_date': now,
                'x_coord_validated_by': self.env.user.id,
                'x_website_published': True,
                'x_publication_date': now,
                'x_coord_validation_notes': False,
            })
            # Guardar versión aprobada en historial y marcar anteriores como no publicadas
            self._create_history_snapshot(is_published=True, state='published', coord_comment=False, mark_previous_unpublished=True)
            # Promover registros staging a publicados y despublicar los anteriores
            self._publish_staging_records()
            # Notificar al docente la aprobación
            self._notify_docente(_("Tu CV ha sido aprobado y publicado."))

    def action_coord_reject(self, comment=False):
            """Coordinador rechaza; mantiene el borrador para corrección."""
            self.ensure_one()
            if not self.env.user.has_group('google_sheets_import.group_coord_academico'):
                raise UserError(_("Solo un coordinador académico puede rechazar este CV."))

            comment = comment or self.x_coord_validation_notes
            self.write({
                'state': 'rejected',
                'x_coord_validation_notes': comment or _('Cambios requeridos por el coordinador.'),
                'x_website_published': self.x_website_published,  # la versión publicada sigue igual
            })
            # Guardar snapshot de rechazo (no publicado)
            self._create_history_snapshot(is_published=False, state='rejected', coord_comment=comment or False)
            # Notificar al docente con observación
            self._notify_docente(_("Tu CV fue rechazado. Observación: %s") % (comment or _('Cambios requeridos')))

    def action_view_history(self):
            """Ver historial de snapshots de este CV."""
            self.ensure_one()
            return {
                'type': 'ir.actions.act_window',
                'name': _('Historial de versiones'),
                'res_model': 'cv.document.history',
                'view_mode': 'tree,form',
                'domain': [('document_id', '=', self.id)],
                'context': {'default_document_id': self.id},
            }

    def action_unpublish(self):
            self.ensure_one()

            if not (self.env.user.has_group('google_sheets_import.group_coord_academico') or self.env.user.has_group('google_sheets_import.group_admin_institucional')):
                raise UserError(_("El coordinador académico y el administrador institucional pueden despublicar este perfil."))
            self.write({
                'x_website_published': False,
                'state': 'draft',
            })

    def action_open_webpage(self):
        """Botón para ver página pública"""
        self.ensure_one()
        ident = self.employee_id.identification_id or self.cedula
        if not ident:
            raise UserError(_("El empleado no tiene cédula registrada."))
        return {
            'type': 'ir.actions.act_url',
            'url': f'/docente/{ident}',
            'target': 'new',
        }


    start_time_espoch = fields.Float(
        string='Start Time Espoch',
        help='Momento en que se envió el CV a n8n (epoch segundos)'
    )

    normalized_processing_date = fields.Datetime(
        string="Normalized Processing Date",
        help="Timestamp when data was applied to normalized tables"
    )

    parsing_status = fields.Selection(
        [
            ("unparsed", "Unparsed"),
            ("parsing", "Parsing"),
            ("parsed", "Parsed"),
            ("applied", "Applied to Employee"),
            ("failed", "Failed"),
        ],
        string="Parsing Status",
        default="unparsed",
        help="Status of parsing extraction_response and applying to normalized tables."
    )

    parsing_error = fields.Text(
        string="Parsing Error",
        help="Last error message if parsing or applying failed."
    )

    parsing_date = fields.Datetime(
        string="Parsing Date",
        help="Timestamp when extraction_response was last parsed"
    )

    applied_date = fields.Datetime(
        string="Applied Date",
        help="Timestamp when parsed data was applied to normalized tables"
    )

    # Seguimiento N8N
    n8n_job_id = fields.Char(string='Job ID N8N')
    n8n_status = fields.Char(string='Estado N8N', help='Último estado reportado por n8n')
    n8n_last_callback = fields.Datetime(string='Último callback N8N')

    # Info de lote
    batch_token = fields.Char(string='Token de Lote', index=True, help='Identificador de lote (opcional)')
    batch_order = fields.Integer(string='Orden en Lote', default=0, index=True, help='Orden relativo en el lote (opcional)')

    n8n_webhook_url = fields.Char(
        string='URL Webhook N8N',
        compute='_compute_n8n_webhook_url',
        store=False,
        help='URL del webhook de N8N (configurado en CV Importer Config)'
    )

    status_message = fields.Text(string='Mensaje de Error')

    extraction_response = fields.Text(
        string='Respuesta de extracción (JSON)',
        help='Payload JSON completo devuelto por N8N con los datos extraídos del CV.'
    )

    cv_download_url = fields.Char(
        string='URL de Descarga CV',
        compute='_compute_cv_download_url',
        store=True
    )

    last_state_change = fields.Datetime(
        string='Último cambio de estado',
        tracking=True
    )

    # ===============================
    # Colecciones normalizadas (editables por docente)
    # ===============================

    cv_academic_degree_ids = fields.One2many(
        related='employee_id.cv_academic_degree_ids',
        string='Formación académica',
        readonly=False,
    )

    cv_work_experience_ids = fields.One2many(
        related='employee_id.cv_work_experience_ids',
        string='Experiencia laboral',
        readonly=False,
    )

    cv_materias_ids = fields.One2many(
        related='employee_id.cv_materias_ids',
        string='Materias',
        readonly=False,
    )

    cv_certification_ids = fields.One2many(
        related='employee_id.cv_certification_ids',
        string='Certificaciones',
        readonly=False,
    )

    cv_logros_ids = fields.One2many(
        related='employee_id.cv_logros_ids',
        string='Logros y reconocimientos',
        readonly=False,
    )

    cv_language_ids = fields.One2many(
        related='employee_id.cv_language_ids',
        string='Idiomas',
        readonly=False,
    )

    cv_project_ids = fields.One2many(
        related='employee_id.cv_project_ids',
        string='Proyectos',
        readonly=False,
    )

    cv_publication_ids = fields.One2many(
        related='employee_id.cv_publication_ids',
        string='Publicaciones',
        readonly=False,
    )

    cv_yearly_metrics_ids = fields.One2many(
        related='employee_id.cv_yearly_metrics_ids',
        string='Métricas anuales',
        readonly=False,
    )


    def action_check_import_status(self):
        """Mostrar un mensaje con el estado actual y refrescar la vista."""
        self.ensure_one()

        employee_label = self.employee_id.name or self.employee_name or self.cedula or _("empleado")

        state = self.state or "draft"
        if state == "processed":
            msg = _("El CV de %s ha sido procesado correctamente.") % employee_label
            notif_type = "success"
        elif state == "error":
            msg = _("Se produjo un error al procesar el CV de %s. Revisa el log o el detalle del documento.") % employee_label
            notif_type = "danger"
        elif state == "processing":
            msg = _("El CV de %s aún se está procesando.") % employee_label
            notif_type = "warning"
        else:
            msg = _("El CV de %s está en el estado: %s.") % (employee_label, state)
            notif_type = "info"

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Estado de importación"),
                "message": msg,
                "type": notif_type,  # success | warning | danger | info
                "sticky": False,
                # 👇 Esto hace que al cerrar la notificación se recargue la vista
                "next": {
                    "type": "ir.actions.client",
                    "tag": "reload",
                },
            },
        }


    def _normalize_text(self, texto):
        texto = str(texto or '')

        texto = texto.replace('\xa0', ' ').replace('\u200b', '')

        reemplazos = (
            ("á", "a"), ("é", "e"), ("í", "i"),
            ("ó", "o"), ("ú", "u"),
            ("Á", "A"), ("É", "E"), ("Í", "I"),
            ("Ó", "O"), ("Ú", "U"),
            ("ñ", "n"), ("Ñ", "N"),
        )
        for a, b in reemplazos:
            texto = texto.replace(a, b)

        texto = ''.join(ch for ch in texto if ch.isalnum() or ch.isspace())

        texto = ' '.join(texto.strip().split())
        return texto.lower()



    def _clean_carrera_label(self, raw):
        """
        Limpia textos de carrera quitando prefijos como:
        'Carrera de', 'Carrera en', 'Carrera '
        pero mantiene tildes/ñ para que luego _normalize_text se encargue.
        """
        txt = str(raw or '').strip()
        txt_lower = txt.lower()

        prefixes = [
            'carrera de ',
            'carrera en ',
            'carrera ',
        ]

        for p in prefixes:
            if txt_lower.startswith(p):
                # recortar usando la longitud del prefijo original
                txt = txt[len(p):].strip()
                break

        return txt

    def _find_best_carrera(self, carrera_index, carrera_key):
        if not carrera_key:
            return False

        if carrera_key in carrera_index:
            return carrera_index[carrera_key]

        key_tokens = set(carrera_key.split())
        if not key_tokens:
            return False

        best = None
        best_score = 0.0

        for k, carrera in carrera_index.items():
            tokens = set(k.split())
            if not tokens:
                continue
            inter = key_tokens & tokens
            union = key_tokens | tokens
            score = len(inter) / float(len(union)) if union else 0.0

            if score > best_score:
                best_score = score
                best = carrera

        # Umbral: puedes ajustarlo. 0.6 suele ser razonable
        if best and best_score >= 0.6:
            _logger.info(
                "MATCH DIFUSO carrera_key=%r -> '%s' (id=%s) score=%.2f",
                carrera_key, best.name, best.id, best_score
            )
            return best

        return False


    @api.depends('employee_id')
    def _compute_employee_collections(self):
        """
        No crea nada nuevo, solo refleja lo que ya está
        en hr.employee.* para este empleado.
        """
        for rec in self:
            emp = rec.employee_id
            if not emp:
                rec.cv_academic_degree_ids = False
                rec.cv_work_experience_ids = False
                rec.cv_materias_ids = False
                rec.cv_certification_ids = False
                rec.cv_logros_ids = False
                rec.cv_language_ids = False
                rec.cv_project_ids = False
                rec.cv_publication_ids = False
                rec.cv_yearly_metrics_ids = False
                continue

            rec.cv_academic_degree_ids = self.env['cv.academic.degree'].search([
                ('employee_id', '=', emp.id)
            ])
            rec.cv_work_experience_ids = self.env['cv.work.experience'].search([
                ('employee_id', '=', emp.id)
            ])
            rec.cv_materias_ids = self.env['cv.materias'].search([
                ('employee_id', '=', emp.id)
            ])
            rec.cv_certification_ids = self.env['cv.certification'].search([
                ('employee_id', '=', emp.id)
            ])
            rec.cv_logros_ids = self.env['cv.logros'].search([
                ('employee_id', '=', emp.id)
            ])
            rec.cv_language_ids = self.env['cv.language'].search([
                ('employee_id', '=', emp.id)
            ])
            rec.cv_project_ids = self.env['cv.project'].search([
                ('employee_id', '=', emp.id)
            ])
            rec.cv_publication_ids = self.env['cv.publication'].search([
                ('employee_id', '=', emp.id)
            ])
            rec.cv_yearly_metrics_ids = self.env['cv.yearly.metrics'].search([
                ('employee_id', '=', emp.id)
            ])

    @api.depends_context('company')
    def _compute_n8n_webhook_url(self):
        webhook_url = self.env['ir.config_parameter'].sudo().get_param(
            'cv_importer.n8n_webhook_url',
            'https://n8n.pruebasbidata.site/webhook/process-cv'
        )
        for record in self:
            record.n8n_webhook_url = webhook_url

    @api.depends('employee_id', 'employee_id.identification_id')
    def _compute_cv_download_url(self):
        for record in self:
            if record.employee_id and record.employee_id.identification_id:
                cedula = record.employee_id.identification_id.zfill(10)
                record.cv_download_url = f"https://hojavida.espoch.edu.ec/cv/{cedula}"
            else:
                record.cv_download_url = False

    @api.model
    def create(self, vals):
        if not vals.get('name') and vals.get('employee_id'):
            employee = self.env['hr.employee'].browse(vals['employee_id'])
            vals['name'] = f"CV - {employee.name}"
        if not vals.get('last_state_change') and vals.get('state'):
            vals['last_state_change'] = fields.Datetime.now()
        return super().create(vals)

    # ==========================
    # LÓGICA DE LOTES Y N8N
    # ==========================

    def _dispatch_next_in_batch(self):
        for rec in self.sudo():
            if not rec.batch_token:
                continue
            dom = [
                ('batch_token', '=', rec.batch_token),
                ('state', 'in', ['draft', 'uploaded']),
                ('id', '!=', rec.id),
            ]
            order = 'id'
            if rec.batch_order:
                dom.append(('batch_order', '>', rec.batch_order))
                order = 'batch_order,id'
            nxt = self.search(dom, order=order, limit=1)
            if not nxt:
                _logger.info(f"🧵 Lote {rec.batch_token}: no hay siguiente pendiente.")
                continue
            _logger.info(
                f"🧵 Lote {rec.batch_token}: despachando siguiente id={nxt.id} "
                f"emp={nxt.employee_id.name} (state={nxt.state})"
            )
            try:
                nxt.action_upload_to_n8n()
            except Exception as e:
                nxt.write({'state': 'error', 'status_message': f'Error al despachar siguiente del lote: {e}'})
                _logger.warning(f"⚠️ Error despachando siguiente del lote {rec.batch_token}: {e}")

    def action_upload_to_n8n(self):
        """Envía el CV a n8n con un reintento si no responde en 30s."""
        _logger.info("INICIANDO action_upload_to_n8n")
        ICP = self.env['ir.config_parameter'].sudo()
        verify_n8n = (ICP.get_param('cv_importer.n8n_verify_ssl', 'true') or '').lower() == 'true'
        timeout_seconds = 30

        for record in self:
            _logger.info(f"Procesando record: {record.id} - {record.employee_id.name}")
            cedula = record.cedula or record.employee_id.identification_id
            if not cedula:
                raise UserError(_('El empleado debe tener una cédula asignada'))

            base_url = ICP.get_param('web.base.url')
            callback_url = f"{base_url}/cv/callback"

            import uuid as _uuid
            import time as _time
            start_ts = _time.time()
            record.start_time_espoch = start_ts
            job_id = str(_uuid.uuid4())
            record.n8n_job_id = job_id

            payload = {
                'cedula': str(cedula),
                'employee_name': str(record.employee_id.name or ''),
                'odoo_callback_url': str(callback_url),
                'request_id': job_id,
                'timestamp': str(fields.Datetime.now().isoformat()),
                'start_time_espoch': start_ts,
                'start_time_iso': str(fields.Datetime.now().isoformat()),
                'batch_token': record.batch_token or '',
                'batch_order': int(record.batch_order or 0),
            }

            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'Odoo-CV-Importer/2.0',
                'Accept': 'application/json',
                'Cache-Control': 'no-cache'
            }

            success = False
            last_error = None
            for attempt in (1, 2):
                try:
                    _logger.info(f"Enviando a n8n intento {attempt} (timeout {timeout_seconds}s) para CV {record.id}")
                    response = requests.post(
                        record.n8n_webhook_url,
                        json=payload,
                        headers=headers,
                        timeout=timeout_seconds,
                        verify=verify_n8n
                    )
                    if response.status_code in [200, 201]:
                        success = True
                        break
                    last_error = f"HTTP {response.status_code}: {response.text}"
                except requests.exceptions.Timeout:
                    last_error = "Timeout tras 30s sin respuesta de n8n"
                    _logger.warning(f"Timeout n8n intento {attempt} para CV {record.id}")
                except Exception as e:
                    last_error = str(e)
                    _logger.error(f"Error enviando a n8n intento {attempt} para CV {record.id}: {e}")

            if success:
                record.state = 'uploaded'
                record.status_message = False
            else:
                record.state = 'error'
                record.status_message = _("n8n no pudo procesar tu CV en este momento. Intenta más tarde. Detalle: %s") % (last_error or 'Error desconocido')
                raise UserError(_("n8n no pudo procesar tu CV en este momento. Intenta más tarde."))

    def action_reset_to_draft(self):
        count = len(self)
        ICP = self.env['ir.config_parameter'].sudo()
        for record in self:
            record.write({
                'state': 'draft',
                'status_message': False,
                'normalized_processing_date': False,
                'parsing_status': 'unparsed',
                'parsing_error': False,
                'parsing_date': False,
                'applied_date': False,
                'n8n_job_id': False,
                'n8n_status': False,
                'n8n_last_callback': False,
                'batch_token': False,
                'batch_order': 0,

            })
            key = f'cv_importer.n8n_meta.{record.id}'
            ICP.set_param(key, '')
            _logger.info(f"Document {record.id} reset to draft for {record.employee_id.name}")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '✅ Reset Successful',
                'message': f'{count} document(s) reset to draft. Page will reload...',
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }
            }
        }

    # ==========================
    # HISTORIAL / VERSIONADO
    # ==========================

    def _serialize_normalized_data(self):
        """Recolecta datos normalizados en un diccionario simple para historial."""
        self.ensure_one()
        emp = self.employee_id
        data = {
            'employee_id': emp.id,
            'employee_name': emp.name,
            'timestamp': fields.Datetime.now().isoformat(),
        }

        def simple_list(records, fields_list):
            res = []
            for rec in records:
                item = {}
                for fname in fields_list:
                    val = rec[fname]
                    # Normalizar relacionales a ids para serializar
                    if isinstance(val, models.BaseModel):
                        val = val.id
                    # fechas a string
                    if isinstance(val, (datetime, date)):
                        item[fname] = val.isoformat()
                    else:
                        item[fname] = val
                res.append(item)
            return res

        data['academic_degrees'] = simple_list(
            self.env['cv.academic.degree'].sudo().search([('employee_id', '=', emp.id), ('active', '=', True)]),
            ['degree_title', 'degree_type', 'institution']
        )
        data['work_experience'] = simple_list(
            self.env['cv.work.experience'].sudo().search([('employee_id', '=', emp.id), ('active', '=', True)]),
            ['position', 'company', 'department', 'start_date', 'end_date', 'duration_months', 'responsibilities']
        )
        data['projects'] = simple_list(
            self.env['cv.project'].sudo().search([('employee_id', '=', emp.id), ('active', '=', True)]),
            ['project_title', 'project_code', 'project_type', 'institution', 'start_date', 'end_date']
        )
        data['publications'] = simple_list(
            self.env['cv.publication'].sudo().search([('employee_id', '=', emp.id), ('active', '=', True)]),
            ['title', 'publication_type', 'publication_year', 'indexing_database']
        )
        data['certifications'] = simple_list(
            self.env['cv.certification'].sudo().search([('employee_id', '=', emp.id), ('active', '=', True)]),
            ['certification_name', 'institution', 'duration_hours']
        )
        data['logros'] = simple_list(
            self.env['cv.logros'].sudo().search([('employee_id', '=', emp.id), ('active', '=', True)]),
            ['name', 'tipo', 'award_year']
        )
        data['idiomas'] = simple_list(
            self.env['cv.language'].sudo().search([('employee_id', '=', emp.id), ('active', '=', True)]),
            ['language_name', 'proficiency_level', 'writing_level', 'speaking_level']
        )
        data['materias'] = simple_list(
            self.env['cv.materias'].sudo().search([('employee_id', '=', emp.id), ('active', '=', True)]),
            ['asignatura', 'carrera_id']
        )
        return data

    def _create_history_snapshot(self, is_published=False, state='draft', coord_comment=False, mark_previous_unpublished=False):
        """Crea un snapshot en historial sin alterar la lógica existente."""
        self.ensure_one()
        Hist = self.env['cv.document.history'].sudo()

        version = 1 + (Hist.search_count([('document_id', '=', self.id)]) or 0)
        data_json = json.dumps(self._serialize_normalized_data(), ensure_ascii=False)

        if mark_previous_unpublished:
            Hist.search([('document_id', '=', self.id), ('is_published', '=', True)]).write({'is_published': False})

        # Desmarcar snapshot actual previo
        Hist.search([('document_id', '=', self.id), ('is_current', '=', True)]).write({'is_current': False})

        Hist.create({
            'document_id': self.id,
            'version': version,
            'state': state,
            'data_json': data_json,
            'coord_comment': coord_comment or '',
            'is_published': is_published,
            'is_current': True,
        })

    def _publish_staging_records(self):
        """Promueve todos los registros is_published=False a True y despublica los actuales."""
        self.ensure_one()
        emp_id = self.employee_id.id
        model_names = [
            'cv.academic.degree',
            'cv.work.experience',
            'cv.project',
            'cv.publication',
            'cv.certification',
            'cv.logros',
            'cv.language',
            'cv.materias',
        ]
        for model_name in model_names:
            Model = self.env[model_name].sudo()
            Model.search([('employee_id', '=', emp_id), ('is_published', '=', True)]).write({'is_published': False})
            Model.search([('employee_id', '=', emp_id), ('is_published', '=', False)]).write({'is_published': True})

    def write(self, vals):
        # Marcar fecha de cambio de estado si el estado cambia
        if 'state' in vals:
            vals = dict(vals)
            vals['last_state_change'] = fields.Datetime.now()
        return super().write(vals)

    # ==========================
    # NOTIFICACIONES
    # ==========================

    def _notify_coordinadores(self, message_body):
        """Notifica a coordinadores de la misma facultad del empleado."""
        self.ensure_one()
        fac = getattr(self.employee_id, 'facultad', False)
        partners = []
        _logger.info("Solicitud de revisión: CV %s, empleado %s, facultad empleado=%s", self.id, self.employee_id.id, fac and fac.name)
        if fac:
            coord_users = self.env['res.users'].sudo().search([
                ('groups_id', 'in', self.env.ref('google_sheets_import.group_coord_academico').id),
                ('partner_id', '!=', False),
            ])
            coord_users = coord_users.filtered(lambda u: getattr(u, 'facultad', False) and u.facultad.id == fac.id)
            for cu in coord_users:
                fac_name = getattr(cu, 'facultad', False) and cu.facultad.name or 'N/A'
                _logger.info("Coordinador candidato user=%s facultad=%s partner=%s", cu.id, fac_name, cu.partner_id.id)
            partners = coord_users.mapped('partner_id.id')
            _logger.info("Notificando coordinadores facultad %s: users=%s partners=%s", fac.name, coord_users.ids, partners)
        else:
            _logger.info("No se encontró facultad en empleado %s, no se notifican coordinadores.", self.employee_id.id)

        if partners:
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
            link = f"{base_url}/web#id={self.id}&model=cv.document&view_type=form"
            body = f"{message_body}<br/><a href=\"{link}\">{_('Abrir CV')}</a>"
            # Mensaje en el hilo del CV (campana/inbox)
            self.message_post(
                body=body,
                subtype_xmlid='mail.mt_comment',
                partner_ids=partners,
                message_type='comment',
            )
            # Mensaje en canal dedicado para que quede en Discuss
            self._post_to_cv_channel(fac, body, partners)
        else:
            _logger.info("No hay coordinadores con facultad coincidente para el CV %s.", self.id)

    def _notify_docente(self, message_body):
        """Notifica al docente dueño del CV."""
        self.ensure_one()
        partner = self.employee_id.user_id.partner_id
        if not partner:
            return
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        link = f"{base_url}/web#id={self.id}&model=cv.document&view_type=form"
        body = f"{message_body}<br/><a href=\"{link}\">{_('Abrir CV')}</a>"
        self.message_post(
            body=body,
            subtype_xmlid='mail.mt_comment',
            partner_ids=[partner.id],
            message_type='comment',
        )

    def _post_to_cv_channel(self, facultad, body, partner_ids):
        """Publica la notificación en un canal dedicado por facultad para que quede en Discuss."""
        try:
            Channel = self.env['discuss.channel'].sudo()
            name = facultad and f"CV Revisiones - {facultad.name}" or "CV Revisiones - Sin facultad"
            channel = Channel.search([('name', '=', name), ('channel_type', '=', 'channel')], limit=1)
            if not channel:
                channel = Channel.create({
                    'name': name,
                    'channel_type': 'channel',
                    'public': 'private',
                })

            # Agregar coordinadores (partners) y docente si existe partner
            doc_partner = self.employee_id.user_id.partner_id
            to_add = set(partner_ids or [])
            if doc_partner:
                to_add.add(doc_partner.id)

            if to_add:
                channel.write({'channel_partner_ids': [(4, pid) for pid in to_add]})
                channel.message_post(
                    body=body,
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment',
                )
        except Exception as e:
            _logger.warning("No se pudo publicar en canal de revisiones: %s", e)

    # ==========================
    # LIMPIEZA Y MAPEO DE DATOS
    # ==========================

    def _clean_raw_data(self, raw_data):
        """Normaliza claves del JSON de N8N a nombres internos en español."""

        def clean_list(items):
            if not items:
                return []
            return [item for item in items if item and isinstance(item, dict)]

        cleaned = {
            "educacion":      clean_list(raw_data.get("academic_degrees", [])),
            "experiencia":    clean_list(raw_data.get("work_experience", [])),
            "certificaciones":clean_list(raw_data.get("certifications", [])),
            "materias":       clean_list(raw_data.get("materias", [])),
            "proyectos":      clean_list(raw_data.get("proyectos", [])),
            "publicaciones":  clean_list(raw_data.get("publications", [])),
            "logros":         clean_list(raw_data.get("logros", [])),
            "idiomas":        clean_list(raw_data.get("languages", [])),
        }

        return cleaned

    # === helpers de conversión ===

    def _json_to_date(self, value):
        if not value:
            return False
        try:
            return fields.Date.to_date(value)
        except Exception:
            return False

    def _safe_int(self, value, default=-1):
        if value in (None, "", False):
            return default
        try:
            return int(value)
        except Exception:
            return default

    def _map_degree_type(self, raw_type):
        if not raw_type:
            return "no especificado"

        t = str(raw_type).strip().lower()

        valid = {
            "primaria",
            "secundaria",
            "tecnico",
            "tercer nivel",
            "cuarto nivel",
            "no especificado",
        }
        if t in valid:
            return t

        if "primaria" in t:
            return "primaria"
        if "secundaria" in t or "bachiller" in t:
            return "secundaria"
        if "tecnólogo" in t or "tecnologa" in t or "tecnologo" in t:
            return "tecnico"
        if "técnico" in t or "tecnico" in t:
            return "tecnico"
        if "doctor" in t or "doctorado" in t or "phd" in t:
            return "cuarto nivel"
        if "magíster" in t or "magister" in t or "máster" in t or "master" in t:
            return "cuarto nivel"
        if "ingenier" in t or "licenciad" in t:
            return "tercer nivel"

        return "no especificado"



    def _map_certification_type(self, raw_type):
        if not raw_type:
            return "other"
        t = str(raw_type).strip().lower()
        if "aprobación" in t:
            return "approve"
        if "desarrollo" in t or "profes" in t or "capacit" in t or "curso" in t or "taller" in t:
            return "professional_development"
        return "other"

    def _map_logro_tipo(self, raw_tipo):
        if not raw_tipo:
            return "other"
        t = str(raw_tipo).strip().lower()
        if "artist" in t:
            return "artistico"
        if "deport" in t:
            return "deportivo"
        if "acad" in t:
            return "academico"
        if "labor" in t:
            return "laboral"
        return "other"

    def _map_publication_type(self, raw_type):
        if not raw_type:
            return "other"
        t = str(raw_type).strip().lower()
        if "articul" in t:
            return "article"
        if "libro" in t or "book" in t:
            return "book"
        if "tesis" in t or "thesis" in t:
            return "thesis"
        if "congreso" in t or "conference" in t:
            return "congreso"
        return "other"

    def _map_publication_language(self, raw_lang):
        if not raw_lang:
            return "other"
        t = str(raw_lang).strip().lower()
        if t.startswith("es"):
            return "es"
        if t.startswith("en"):
            return "en"
        if t.startswith("pt"):
            return "pt"
        if t.startswith("fr"):
            return "fr"
        if t.startswith("de"):
            return "de"
        return "other"

    # ==========================
    # FASE 8: APLICAR A TABLAS cv.*
    # ==========================

    def _sanitize_nulls_for_model(self, Model, vals):
        clean = {}
        for field_name, value in vals.items():
            field = Model._fields.get(field_name)
            if not field:
                _logger.warning(f"Campo desconocido '{field_name}' en {Model._name}")
                continue  # ✅ Saltar campos desconocidos

            if value in (None, False, ''):
                if isinstance(field, (fields.Char, fields.Text)):
                    clean[field_name] = 'N/A'
                elif isinstance(field, (fields.Integer, fields.Float, fields.Monetary)):
                    clean[field_name] = -1
                else:
                    clean[field_name] = False
            else:
                clean[field_name] = value

        return clean

    def action_apply_parsed_data(self):
        self.ensure_one()
        if not self.employee_id:
            raise UserError(_('No hay empleado asociado al documento'))

        employee = self.employee_id
        log_lines = []

        try:
            self.parsing_status = "parsing"
            self.parsing_date = fields.Datetime.now()

            # 🔹 Verificar que haya algo en extraction_response
            if not getattr(self, "extraction_response", False):
                msg = "extraction_response vacío o no definido"
                _logger.warning(msg + f" en document {self.id}")
                self.parsing_status = "failed"
                self.parsing_error = msg
                return

            try:
                payload = json.loads(self.extraction_response)
            except Exception as e:
                msg = f"JSON inválido en extraction_response: {e}"
                _logger.error(msg)
                self.parsing_status = "failed"
                self.parsing_error = msg
                return

            raw = (
                payload.get("raw_extracted_data")
                or payload.get("output", {}).get("raw_extracted_data")
                or {}
            )
            additional = payload.get("additional_fields") or {}

            if not raw:
                _logger.warning("raw_extracted_data vacío en document %s", self.id)
                self.parsing_status = "failed"
                self.parsing_error = "raw_extracted_data vacío"
                return

            cleaned_data = self._clean_raw_data(raw)

            import_user = self.create_uid or self.env.user

            Degree       = self.env["cv.academic.degree"].with_user(import_user).sudo()
            WorkExp      = self.env["cv.work.experience"].with_user(import_user).sudo()
            Materias     = self.env["cv.materias"].with_user(import_user).sudo()
            Certif       = self.env["cv.certification"].with_user(import_user).sudo()
            Logro        = self.env["cv.logros"].with_user(import_user).sudo()
            Lang         = self.env["cv.language"].with_user(import_user).sudo()
            Project      = self.env["cv.project"].with_user(import_user).sudo()
            Pub          = self.env["cv.publication"].with_user(import_user).sudo()
            YearMetrics  = self.env["cv.yearly.metrics"].with_user(import_user).sudo()
            CarreraModel = self.env["carrera"].with_user(import_user).sudo()

            # Borrar registros previos SOLO de import
            Degree.search([("employee_id", "=", employee.id), ("source", "=", "import")]).unlink()
            WorkExp.search([("employee_id", "=", employee.id), ("source", "=", "import")]).unlink()
            Materias.search([("employee_id", "=", employee.id), ("source", "=", "import")]).unlink()
            Certif.search([("employee_id", "=", employee.id), ("source", "=", "import")]).unlink()
            Logro.search([("employee_id", "=", employee.id), ("source", "=", "import")]).unlink()
            Lang.search([("employee_id", "=", employee.id), ("source", "=", "import")]).unlink()
            Project.search([("employee_id", "=", employee.id), ("source", "=", "import")]).unlink()
            Pub.search([("employee_id", "=", employee.id), ("source", "=", "import")]).unlink()

            # === ACADEMIC DEGREES ===
            edu_list = cleaned_data.get("educacion") or []
            created = 0
            for d in edu_list:
                degree_title = d.get("degree_title") or d.get("titulo") or ""
                if not degree_title:
                    continue
                institution = d.get("institution") or d.get("institucion") or "N/A"
                degree_type_raw = d.get("degree_type") or d.get("nivel") or ""
                mapped_type = self._map_degree_type(degree_type_raw)
                vals = {
                    "employee_id": employee.id,
                    "degree_type": mapped_type,
                    "degree_title": degree_title,
                    "institution": institution,
                    "source": "import",
                }
                vals = self._sanitize_nulls_for_model(Degree, vals)
                Degree.create(vals)
                created += 1
            log_lines.append(f"Academic Degrees: {created} records created")

            # === WORK EXPERIENCE ===
            work_list = cleaned_data.get("experiencia") or []
            created = 0
            for w in work_list:
                position = w.get("position") or w.get("cargo") or ""
                if not position:
                    continue
                company = w.get("company") or w.get("institucion") or w.get("empresa") or "N/A"
                department = w.get("department")
                start_date = self._json_to_date(w.get("start_date") or w.get("fecha_inicio"))
                end_date = self._json_to_date(w.get("end_date") or w.get("fecha_fin"))
                responsibilities = w.get("responsibilities") or w.get("descripcion") or None
                vals = {
                    "employee_id": employee.id,
                    "position": position,
                    "company": company,
                    "department": department or False,
                    "start_date": start_date,
                    "end_date": end_date,
                    "responsibilities": responsibilities,
                    "source": "import",
                }
                vals = self._sanitize_nulls_for_model(WorkExp, vals)
                WorkExp.create(vals)
                created += 1
            log_lines.append(f"Work Experience: {created} records created")

            # === MATERIAS ===
            materias_list = cleaned_data.get("materias") or []

            created = 0
            skipped = 0
            Materias = self.env["cv.materias"].with_user(import_user).sudo()
            CarreraModel = self.env["carrera"].with_user(import_user).sudo()

            carrera_index = {}
            all_carreras = CarreraModel.search([])
            for c in all_carreras:
                key = self._normalize_text(c.name)
                carrera_index[key] = c
            

            for m in materias_list:
                asignatura = m.get("materia") or m.get("asignatura") or m.get("subject")
                if not asignatura:
                    continue

                carrera_id = False
                facultad_id = False
                carrera_nombre_raw = (m.get("carrera") or m.get("career") or "").strip()

                if carrera_nombre_raw:
                    carrera_clean = self._clean_carrera_label(carrera_nombre_raw)
                    carrera_key = self._normalize_text(carrera_clean)

                    carrera = self._find_best_carrera(carrera_index, carrera_key)

                    if not carrera:
                        carrera = CarreraModel.search(
                            [("name", "ilike", carrera_key)],
                            limit=1
                        )

                    if carrera and carrera.exists():
                        carrera_id = carrera.id

                        # Obtener facultad desde la carrera (si existe el campo)
                        try:
                            if (
                                hasattr(carrera, 'facultad_id')
                                and carrera.facultad_id
                                and carrera.facultad_id.exists()):
                                facultad_id = carrera.facultad_id.id
                        except Exception as e:
                            _logger.warning(
                                f"⚠️ Error obteniendo facultad de carrera '{carrera_nombre_raw}': {e}"
                            )

                    else:
                        _logger.warning(
                            f"⚠️ Carrera '{carrera_nombre_raw}' (normalizada='{carrera_key}') "
                            f"no encontrada en BD. Materia '{asignatura}' omitida."
                        )
                        skipped += 1
                        continue
                else:
                    _logger.warning(
                        f"⚠️ Materia '{asignatura}' sin carrera especificada. Omitida."
                    )
                    skipped += 1
                    continue
                
                # ✅ VALIDAR QUE TENGAMOS CARRERA VÁLIDA ANTES DE CREAR
                if not carrera_id or not isinstance(carrera_id, int):
                    _logger.warning(
                        f"⚠️ No se pudo vincular materia '{asignatura}' a carrera existente. Omitida."
                    )
                    skipped += 1
                    continue
                
                # ✅ CREAR MATERIA CON VALIDACIONES ROBUSTAS
                vals = {
                    "employee_id": employee.id,
                    "asignatura": asignatura,
                    "carrera_id": carrera_id,  # ✅ SIEMPRE UN ID VÁLIDO
                    "facultad_id": facultad_id or False,
                    "course_code": m.get("codigo_materia") or m.get("course_code") or "",
                    "source": "import",
                }
                
                # Sanitizar valores
                vals = self._sanitize_nulls_for_model(Materias, vals)
                
                # ✅ VALIDACIÓN FINAL DE TIPOS
                if not vals.get('carrera_id'):
                    _logger.warning(
                        f"⚠️ Sin carrera_id válido - Omitiendo materia '{asignatura}'"
                    )
                    skipped += 1
                    continue
                    
                try:
                    carrera_check = CarreraModel.browse(vals['carrera_id'])
                    if not carrera_check.exists():
                        _logger.error(
                            f"⛔ Carrera ID {vals['carrera_id']} NO EXISTE en BD - "
                            f"Omitiendo materia '{asignatura}'"
                        )
                        skipped += 1
                        continue
                except Exception as e:
                    _logger.error(f"Error verificando carrera_id={vals['carrera_id']}: {e}")
                    skipped += 1
                    continue

                try:
                    Materias.create(vals)
                    created += 1
                    _logger.info(f"Materia '{asignatura}' creada con carrera_id={vals['carrera_id']}")
                except Exception as e:
                    _logger.error(f"Error creando materia '{asignatura}': {e}")
                    skipped += 1
                    continue
                    
            log_lines.append(f"Materias: {created} created, {skipped} skipped (no matching career)")


            # === CERTIFICATIONS ===
            cert_list = cleaned_data.get("certificaciones") or []
            created = 0
            for c in cert_list:
                name = c.get("certification_name") or c.get("descripcion") or ""
                if not name:
                    continue
                inst = c.get("institution") or c.get("institucion") or "N/A"
                ctype_raw = c.get("certification_type") or c.get("tipo") or ""
                mapped_type = self._map_certification_type(ctype_raw)
                hours = self._safe_int(c.get("duration_hours"), default=None)
                days = self._safe_int(c.get("duration_days"), default=None)
                vals = {
                    "employee_id": employee.id,
                    "certification_type": mapped_type,
                    "certification_name": name,
                    "institution": inst,
                    "duration_hours": hours,
                    "duration_days": days,
                    "source": "import",
                }
                vals = self._sanitize_nulls_for_model(Certif, vals)
                Certif.create(vals)
                created += 1
            log_lines.append(f"Certifications: {created} records created")

            # === LOGROS ===
            logros_list = cleaned_data.get("logros") or []
            created = 0
            for lg in logros_list:
                desc = lg.get("descripcion") or lg.get("name") or ""
                if not desc:
                    continue
                tipo_raw = lg.get("tipo") or ""
                mapped_tipo = self._map_logro_tipo(tipo_raw)
                year_raw = lg.get("award_year") or lg.get("year") or ""
                year_int = None
                try:
                    year_int = int(year_raw) if year_raw else None
                except Exception:
                    year_int = None
                vals = {
                    "employee_id": employee.id,
                    "tipo": mapped_tipo,
                    "name": desc,
                    "awarding_institution": lg.get("institucion") or "N/A",
                    "award_year": year_int,
                    "source": "import",
                }
                vals = self._sanitize_nulls_for_model(Logro, vals)
                Logro.create(vals)
                created += 1
            log_lines.append(f"Logros: {created} records created")

            # === LANGUAGES ===
            lang_list = cleaned_data.get("idiomas") or []
            created = 0
            for lng in lang_list:
                lang_name = lng.get("language_name") or lng.get("idioma") or ""
                if not lang_name:
                    continue
                w = self._safe_int(lng.get("writing_level"), default=None)
                s = self._safe_int(lng.get("speaking_level"), default=None)
                vals = {
                    "employee_id": employee.id,
                    "language_name": lang_name,
                    "writing_level": w,
                    "speaking_level": s,
                    "source": "import",
                }
                vals = self._sanitize_nulls_for_model(Lang, vals)
                Lang.create(vals)
                created += 1
            log_lines.append(f"Languages: {created} records created")

            # === PROJECTS ===
            proj_list = cleaned_data.get("proyectos") or []
            created = 0
            for p in proj_list:
                title = p.get("project_title") or p.get("titulo") or ""
                if not title:
                    continue
                p_type = p.get("project_type") or "otro"
                selection_dict = dict(self.env["cv.project"]._fields["project_type"].selection)
                if p_type not in selection_dict:
                    p_type = "otro"
                vals = {
                    "employee_id": employee.id,
                    "project_title": title,
                    "project_code": p.get("project_code") or "",
                    "project_type": p_type,
                    "institution": p.get("institution") or "ESPOCH",
                    "start_date": self._json_to_date(p.get("start_date")),
                    "end_date": self._json_to_date(p.get("end_date")),
                    "source": "import",
                }
                vals = self._sanitize_nulls_for_model(Project, vals)
                Project.create(vals)
                created += 1
            log_lines.append(f"Projects: {created} records created")

            # === PUBLICATIONS ===
            pubs_list = cleaned_data.get("publicaciones") or []
            created = 0
            for pub in pubs_list:
                title = pub.get("title") or pub.get("titulo") or ""
                if not title:
                    continue
                ptype = self._map_publication_type(pub.get("publication_type"))
                year_int = self._safe_int(pub.get("publication_year"), default=None)
                pub_date = self._json_to_date(pub.get("publication_date"))
                is_indexed = bool(pub.get("is_indexed"))
                index_db = pub.get("indexing_database") or ""
                lang_sel = self._map_publication_language(pub.get("language"))
                vals = {
                    "employee_id": employee.id,
                    "publication_type": ptype,
                    "title": title,
                    "publication_year": year_int,
                    "publication_date": pub_date,
                    "is_indexed": is_indexed,
                    "indexing_database": index_db,
                    "language": lang_sel,
                    "source": "import",
                }
                vals = self._sanitize_nulls_for_model(Pub, vals)
                Pub.create(vals)
                created += 1
            log_lines.append(f"Publications: {created} records created")

            # === YEARLY METRICS ===
            try:
                current_year = date.today().year

                # --- PUBLICACIONES DEL AÑO ---
                pubs_year = 0
                for pub in pubs_list:
                    year_raw = pub.get("publication_year")
                    try:
                        year_int = int(year_raw) if year_raw else None
                    except:
                        year_int = None

                    if year_int == current_year:
                        pubs_year += 1

                # --- LOGROS DEL AÑO ---
                logros_year = 0
                for lg in logros_list:
                    year_raw = lg.get("year") or lg.get("award_year")
                    try:
                        year_int = int(year_raw) if year_raw else None
                    except:
                        year_int = None

                    if year_int == current_year:
                        logros_year += 1

                # --- HORAS DE CERTIFICACIONES DEL AÑO (OPCIONAL) ---
                cert_hours_year = 0
                for c in cert_list:
                    year_raw = c.get("year") or c.get("cert_year")
                    try:
                        year_int = int(year_raw) if year_raw else None
                    except:
                        year_int = None

                    if year_int == current_year:
                        cert_hours_year += self._safe_int(c.get("duration_hours"), default=0)

                existing = YearMetrics.search([
                    ("employee_id", "=", employee.id),
                    ("year", "=", current_year),
                ], limit=1)

                vals_metrics = {
                    "employee_id": employee.id,
                    "year": current_year,
                    "publications_count": pubs_year,
                    "logros_count": logros_year,
                    "computation_method": "semi_automatic",
                }

                if existing:
                    existing.write(vals_metrics)
                else:
                    YearMetrics.create(vals_metrics)

                log_lines.append(f"Yearly Metrics: updated for {current_year}")

            except Exception as e:
                _logger.warning(
                    "No se pudieron calcular Yearly Metrics para empleado %s: %s",
                    employee.id, e
                )

            # Finalizar status
            self.parsing_status = "applied"
            self.parsing_error = False
            self.applied_date = fields.Datetime.now()
            self.normalized_processing_date = fields.Datetime.now()

            _logger.info(
                "FASE 8 completada para CvDocument %s / empleado %s",
                self.id, employee.name
            )

        except Exception as e:
            msg = f"Error en FASE 8: {str(e)}"
            self.parsing_status = "failed"
            self.parsing_error = msg
            _logger.error(msg)
            _logger.error(f"Traceback: {traceback.format_exc()}")
            return

        # Al final del try principal, justo antes del _logger.info("FASE 8 completada ...")
        for line in log_lines:
            _logger.info("FASE 8 SUMMARY - %s", line)




    # ==========================
    # TEST N8N
    # ==========================

    def action_test_n8n_connection(self):
        for record in self:
            if not record.n8n_webhook_url:
                raise UserError(_('URL de webhook N8N no configurada'))

            try:
                test_payload = {
                    'test': True,
                    'message': 'Prueba de conexión desde Odoo',
                    'timestamp': fields.Datetime.now().isoformat(),
                }

                import time as _time
                record.start_time_espoch = _time.time()
                test_payload['start_time_espoch'] = record.start_time_espoch

                response = requests.post(
                    record.n8n_webhook_url,
                    json=test_payload,
                    timeout=10
                )

                if response.status_code in [200, 404]:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Conexión N8N',
                            'message': f'Conexión exitosa con N8N en: {record.n8n_webhook_url}',
                            'type': 'success'
                        }
                    }
                else:
                    raise UserError(f"Error de conexión: {response.status_code}")

            except requests.exceptions.ConnectionError:
                raise UserError(
                    f"No se pudo conectar con N8N.\n\n"
                    f"URL: {record.n8n_webhook_url}\n\n"
                    f"Verifica que:\n"
                    f"1. El servidor N8N esté ejecutándose\n"
                    f"2. La URL del webhook sea correcta\n"
                    f"3. No haya firewall bloqueando la conexión"
                )
            except requests.exceptions.Timeout:
                raise UserError(
                    "Timeout al conectar con N8N.\n\n"
                    "El servidor tardó demasiado en responder."
                )
            except Exception as e:
                raise UserError(f"Error inesperado: {str(e)}")


class HrEmployeeCV(models.Model):
    _inherit = 'hr.employee'

    cv_document_ids = fields.One2many('cv.document', 'employee_id', string='Documentos CV')
    cv_document_count = fields.Integer(
        string='Cantidad de CVs',
        compute='_compute_cv_document_count'
    )

    @api.depends('cv_document_ids')
    def _compute_cv_document_count(self):
        for employee in self:
            employee.cv_document_count = len(employee.cv_document_ids)

    def action_view_cv_documents(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'CVs de {self.name}',
            'res_model': 'cv.document',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id}
        }

    def action_create_cv_document(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Nuevo CV para {self.name}',
            'res_model': 'cv.document',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_employee_id': self.id}
        }

    def action_download_cv_auto(self):
        self = self.sudo()
        self.ensure_one()
        employee = self

        if not (self.env.user.has_group('google_sheets_import.group_coord_academico')
                or self.env.user.has_group('google_sheets_import.group_admin_institucional')):
            if employee.user_id and employee.user_id.id != self.env.user.id:
                raise UserError(_('Solo puedes descargar el CV de tu propio perfil.'))

        if not employee.identification_id:
            raise UserError(_('El empleado debe tener una cédula para descargar el CV automáticamente'))

        cv_env = self.env['cv.document'].sudo()

        existing_cv = cv_env.search([
            ('employee_id', '=', employee.id)
        ], limit=1)

        if existing_cv:
            existing_cv.write({'batch_token': False, 'batch_order': 0})
            existing_cv.action_reset_to_draft()
            existing_cv.action_upload_to_n8n()
            return {
                'type': 'ir.actions.act_window',
                'name': f'CV actualizado para {employee.name}',
                'res_model': 'cv.document',
                'res_id': existing_cv.id,
                'view_mode': 'form',
                'target': 'current'
            }
        else:
            cv_doc = cv_env.create({
                'employee_id': employee.id,
                'name': f'CV - {employee.name}',
                'batch_token': False,
                'batch_order': 0,
            })
            cv_doc.action_upload_to_n8n()
            return {
                'type': 'ir.actions.act_window',
                'name': f'CV descargado para {employee.name}',
                'res_model': 'cv.document',
                'res_id': cv_doc.id,
                'view_mode': 'form',
                'target': 'current'
            }


class CvDocumentHistory(models.Model):
    _name = 'cv.document.history'
    _description = 'Historial de versiones de CV'
    _order = 'create_date desc, version desc'

    document_id = fields.Many2one('cv.document', string='Documento CV', required=True, ondelete='cascade')
    version = fields.Integer(string='Versión', default=1)
    state = fields.Char(string='Estado en el momento del snapshot')
    data_json = fields.Text(string='Datos normalizados (JSON)')
    coord_comment = fields.Text(string='Comentario coordinador')
    is_published = fields.Boolean(string='Publicado', default=False)
    is_current = fields.Boolean(string='Último snapshot', default=True)
