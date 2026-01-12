CV Importer – README técnico

Propósito
- Orquestar la extracción, validación y publicación del CV de cada docente sin bloquear Odoo.
- Integrarse con n8n para descargar/parsear el PDF y devolver datos ya estructurados por callback.

Arquitectura (alto nivel)
- Odoo 17 (este módulo) expone servicios internos y un endpoint privado de callback.
- n8n realiza el trabajo pesado (descarga PDF, extracción, limpieza, score). Odoo solo inicia y recibe resultados.
- Website Odoo publica/actualiza la página del docente cuando el estado queda “Validado”.

Dependencias
- Odoo 17 (core): `base`, `hr` (usa `hr.employee`).
- Opcionales: `website` (para publicar perfiles), `queue_job` (OCA) si decides colas nativas.

Estados y flujo
1) Selección de docentes válidos (con cédula) → encolado por registro.
2) Llamada HTTP a n8n para iniciar extracción (asincrónico).
3) n8n responde al endpoint `/cv/callback` con datos ya estructurados.
4) Control de calidad simple (checks + score) y transición de estado:
   - pendiente → en_proceso → validado | error.
5) Si “Validado”, se actualiza Website.

Interfaz pública (Odoo controllers)
- `POST /cv/callback` (privado):
  - Entrada: JSON con referencia, cédula y bloques (educación, experiencia, etc.) ya limpios.
  - Comportamiento: idempotencia por referencia; ejecuta `compute_quality` y `apply_quality`.
  - Respuesta: 200 con `ref_id` y estado final.

Servicios internos
- `programar_extraccion(employee_id)` → crea/encola línea por docente.
- `iniciar_extraccion(line)` → POST a n8n con `ref_id`, cédula y `callback_url`.
- `compute_quality(payload)` → {passed, score, reasons[]}.
- `apply_quality(result)` → setea estado y, si procede, publica Website.

Campos esperados (extensión ligera de `hr.employee`)
- `estado_cv`: string (pendiente, en_proceso, validado, error).
- `puntaje_cv`: float (0..1) – opcional.
- `ultima_actualizacion_cv`: datetime.
- `fuente_cv`: string/URL – opcional.

Configuración
- Variables de entorno/ir.config_parameter:
  - `cv.n8n.endpoint` → URL base de n8n.
  - `cv.callback.secret` → secreto/HMAC para validar callbacks (opcional pero recomendado).
  - `cv.quality.threshold` → umbral de score (default 0.6).

Seguridad
- Todo el tráfico externo bajo HTTPS (terminación vía proxy/Nginx).
- Endpoint de callback protegido por token/HMAC y rate‑limit.
- Solo Admin/Editor pueden iniciar procesos y publicar.

Ejecución y tareas programadas
- Cron sugerido: “Despachar pendientes” cada N minutos (si no usas `queue_job`).
- Reintentos: manejar en n8n; Odoo registra `retries` y permite “Reintentar” manual.

Auditoría y métricas (recomendado)
- Por registro: estado, timestamps, score, razones de calidad, duración.
- Por lote (si implementas modelos de lote): totales por estado, errores y tiempos.

Desarrollo rápido
- Models: extensión `hr.employee` y (opcional) `cvi.batch` / `cvi.batch.line`.
- Controllers: `cv/callback`.
- Views: menú “Procesamiento de CV”, lista por estado, botón “Reintentar”, pestaña “CV” en el empleado.

