from odoo import models, fields, api
from datetime import datetime
import re

class CvTypoCatalog(models.Model):
    _name = "cv.typo.catalog"
    _description = "Catálogo de Typos Frecuentes (Staging)"
    _rec_name = "typo"
    _order = "total desc, last_seen desc"

    typo = fields.Char(required=True, index=True)
    total = fields.Integer(default=0)
    last_seen = fields.Datetime()
    last_cedula = fields.Char()
    sample = fields.Char()  # ejemplo corto

    _sql_constraints = [
        ("typo_unique", "unique(typo)", "El typo ya existe en el catálogo.")
    ]

    @api.model
    def upsert_typo(self, typo, cedula=None, sample=None):
        typo = (typo or "").strip().lower()
        if not typo:
            return False
        rec = self.search([("typo", "=", typo)], limit=1)
        now = fields.Datetime.now()
        if rec:
            rec.write({
                "total": rec.total + 1,
                "last_seen": now,
                "last_cedula": cedula or rec.last_cedula,
                "sample": sample or rec.sample,
            })
        else:
            self.create({
                "typo": typo,
                "total": 1,
                "last_seen": now,
                "last_cedula": cedula,
                "sample": sample,
            })
        return True

    @api.model
    def extract_candidates(self, raw_extracted_data):
        """
        Heurística ligera (NO IA) para detectar candidatos a typo en campos manuales.
        """
        x = raw_extracted_data or {}
        texts = []

        # Campos manuales típicos
        for c in x.get("certifications", []):
            texts += [c.get("certification_name"), c.get("institution")]
        for l in x.get("logros", []):
            texts += [l.get("descripcion")]
        for m in x.get("materias", []):
            texts += [m.get("asignatura"), m.get("carrera")]
        for d in x.get("academic_degrees", []):
            texts += [d.get("degree_title"), d.get("institution")]

        blob = " ".join([t for t in texts if t])
        tokens = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3,}", blob)

        # patrones comunes (puedes ir ampliando con tu evidencia)
        patterns = [
            r"confrence", r"hardenning", r"avanado", r"aprobacion",
            r"tecnologias", r"investigacion", r"pequenas"
        ]

        candidates = []
        for tok in tokens:
            t = tok.lower()
            if len(t) >= 24:
                candidates.append(tok)
                continue
            if re.search(r"([a-záéíóúñ])\1\1", t):
                candidates.append(tok)
                continue
            if any(re.search(p, t) for p in patterns):
                candidates.append(tok)
                continue

        # devuelve únicos (máx 30 para no cargar)
        uniq = []
        seen = set()
        for c in candidates:
            k = c.lower()
            if k in seen:
                continue
            seen.add(k)
            uniq.append(c)
            if len(uniq) >= 30:
                break
        return uniq