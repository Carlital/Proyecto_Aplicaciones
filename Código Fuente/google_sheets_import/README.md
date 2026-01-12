Google Sheets Import – README técnico

Propósito
- Importar docentes desde una hoja pública/CSV institucional y dejarlos listos en Odoo con validación mínima, normalización y auditoría por ejecución.

Arquitectura (alto nivel)
- Este módulo consume CSVs públicos (URLs con output=csv) y realiza validaciones locales, normalización y upsert sobre `hr.employee`.
- Opcionalmente registra “lotes de importación” y “líneas” para auditoría y reintentos por fila.

Dependencias
- Odoo 17 (core): `base`, `hr` (usa `hr.employee`).
- Google Cloud (OAuth JSON/vars de entorno) para acceso a Sheets.

Flujo de importación
1) Admin/Editor abre “Importar desde Sheets”, define hoja/rango.
2) Validación mínima de cabeceras y unicidad por cédula (en lote y en Odoo).
3) Normalización ligera (acentos, mayúsculas, espacios, valores vacíos).
4) Upsert sobre `hr.employee` (crear/actualizar por cédula).
5) Estado inicial de registro: “Pendiente” o “Validado”.
6) Auditoría del proceso y export de resumen.

Acciones UI
- “Validar y simular”: muestra conteos por estado sin persistir cambios.
- “Ejecutar importación”: realiza upsert y genera lote (si está habilitado).
- “Exportar resumen”: CSV/PDF de resultados.

Campos esperados (extensión ligera de `hr.employee`)
- `hoja_origen`: string.
- `estado_importacion`: string (pendiente, validado, error).
- `ultima_importacion`: datetime.
- `usuario_que_importo`: string (usuario responsable).

Configuración
- Variables de entorno/ir.config_parameter:
  - `sheets.credentials.json` o ruta/secret equivalente.
  - `sheets.sheet_id` y `sheets.range` (si deseas valores por defecto).
  - `sheets.max_rows` (recomendado: ≤ 100 por ejecución).

Seguridad
- Tokens OAuth y credenciales en variables de entorno/secretos.
- Solo Admin/Editor puede importar; público no tiene acceso a estas vistas.

Auditoría y métricas (recomendado)
- Por lote: leídos, validados, con error, duplicados; duración total.
- Por fila: mensajes de validación, acciones tomadas, cédula afectada.

Desarrollo rápido
- Models: extensión `hr.employee` y (opcional) `gsi.batch` / `gsi.batch.line`.
- Wizards/Controllers: acción de importación, validación previa, export de resumen.
- Views: menú “Importar desde Sheets”, vista de lote, vista de líneas y botones.

Acceptance criteria (ejemplos)
- Al importar una fila con CÉDULA "123456789" (9 dígitos) el sistema normaliza a "0123456789" y crea/actualiza el empleado.
- Si el CSV contiene cédulas duplicadas en lote, la importación falla con mensaje claro.
- Tras una importación, se crea o actualiza un registro en google.sheets.dataset.version con hash_sha256 único.

