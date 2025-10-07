# Mejoras de Mantenibilidad

## Branding Parametrizable
- Ajustar en: Ajustes > General Settings > Google Sheets Import - Branding.
- Modelo editable: google.sheets.branding (para múltiples variantes futuras).
- Variables CSS dinámicas: --gs-brand-primary / --gs-brand-secondary.

## Versionado Dataset
Use en código tras importar:
self.env['google.sheets.dataset.version'].create_version_from_import(
    sheet_url=sheet_url,
    sheet_gid=gid,
    raw_rows=rows,
    meta={'origen': 'cron'}
)

Evita duplicados por hash (sha256 del contenido normalizado).

## Cache HTTP (Nginx)
Ejemplo snippet:

location ~* ^/google_sheets_import/profile_image/ {
    proxy_pass http://odoo:8069;
    proxy_set_header Host $host;
    add_header Cache-Control "public, max-age=86400, immutable";
}

(Odoo ya devuelve ETag y 304.)

## Extender
- Añadir más campos de marca (tipografía) al modelo google.sheets.branding.
- Añadir política de expiración configurable vía ir.config_parameter.
