# Integración backend + NLP v14 — laboratorio exclusivamente

Base backend: PR #37, `17285a1130c35182d51fc32de005a7265e9c228f`.
Fuente NLP: PR #30, `0f3ae5b3c406ad037bcb5b0e26de3f5aa2f0a7fe`.
La procedencia y reproducción del wheel se describen en `vendor/README.md`.
NLP 0.1.13, reglas v14; contratos 1.0/PRF04_2 intactos.

La proyección evita registrar dos veces la misma evidencia de color: `blanca`
y su normalización `blanco` no son un conflicto. Evidencias distintas siguen
pasando por el detector de conflictos. No se reescriben snapshots históricos.
Las regresiones usan el reproductor textual de captura 23 y las variantes
melamina/melamine y orales asociadas a 23/24; no acreditan haber consultado las
filas originales del laboratorio ni haber transcrito su audio.

## Entorno reproducible y separado

Ejecutar desde el worktree de esta entrega. Los nombres, puertos, broker, base,
raíces de audio y procesos deben ser exclusivos. Estos comandos NO requieren
parar ni reiniciar el laboratorio existente. Si un nombre/puerto está ocupado,
detener el procedimiento y elegir otro conjunto aislado. No usar `.env` de producción.

```bash
uv sync --locked --extra dev --extra worker
sha256sum --check vendor/homex_nlp-0.1.13.sha256
V14_DB_PASSWORD=$(uv run python -c 'import secrets; print(secrets.token_urlsafe(32))')
docker run -d --name homex-v14-integration-pg \
  -e POSTGRES_PASSWORD="$V14_DB_PASSWORD" -e POSTGRES_DB=homex_v14 \
  -p 127.0.0.1:25432:5432 postgres:17-alpine
docker run -d --name homex-v14-integration-redis \
  -p 127.0.0.1:26379:6379 redis:7.4-alpine
export DJANGO_SECRET_KEY="$(uv run python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export DATABASE_URL="postgresql://postgres:${V14_DB_PASSWORD}@127.0.0.1:25432/homex_v14"
export DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,testserver
export DJANGO_SETTINGS_MODULE=config.settings.integration
export CELERY_BROKER_URL=redis://127.0.0.1:26379/0
export HOMEX_AUDIO_TEMP_ROOT="$(mktemp -d /tmp/homex-v14-audio.XXXXXX)"
export HOMEX_MEDIA_ROOT="$(mktemp -d /tmp/homex-v14-media.XXXXXX)"
export HOMEX_ASR_DEVICE=cpu HOMEX_ASR_COMPUTE_TYPE=int8
# Indicar un modelo local faster-whisper verificado; no usar una ruta de audio.
export HOMEX_ASR_MODEL_PATH=/ruta/aislada/al/modelo/faster-whisper
uv run python manage.py migrate --noinput
uv run celery -A config worker --pool=solo --loglevel=INFO \
  --hostname=v14-isolated@%h > /tmp/v14-worker.log 2>&1 &
V14_WORKER_PID=$!
uv run python manage.py runserver 127.0.0.1:28000 --noreload \
  > /tmp/v14-api.log 2>&1 &
V14_API_PID=$!
uv run python scripts/verificar_integracion_f084.py
```

Este gate prueba PostgreSQL, Redis, publicación outbox y Celery reales con texto.
No mide ASR. La suite completa cubre permisos, API, historial, revisión, limpieza
ASR y concurrencia; ASR simulado en tests no equivale a grabación real.

## E2E con voz humana real

Crear un vendedor exclusivamente en esta base (roles/catálogos mediante los
mismos mecanismos administrativos del proyecto). Obtener su JWT en
`POST /api/v1/auth/token/` usando credenciales locales. Consultar OpenAPI si se
necesita el payload de autenticación. Mantener el token sólo en una variable:
`read -rs V14_TOKEN`.

Grabar con micrófono real, por ejemplo con el grabador del sistema, el texto:
«Necesito un escritorio de melamina blanca, de un metro veinte de ancho,
60 centímetros de profundidad y 75 centímetros de alto».
No sustituir con TTS. Guardar temporalmente WAV/WebM compatible con ASR;
registrar consentimiento y transcripción humana de referencia separada.

```bash
V14_SESSION=$(uv run python -c 'import uuid; print(uuid.uuid4())')
V14_KEY=$(uv run python -c 'import uuid; print(uuid.uuid4())')
read -r V14_AUDIO  # ruta absoluta de la grabación efímera
curl --fail-with-body -sS http://127.0.0.1:28000/api/v1/capturas/asistidas/ \
  -H "Authorization: Bearer $V14_TOKEN" \
  -F "clave_idempotencia=$V14_KEY" -F "sesion_borrador=$V14_SESSION" \
  -F moneda_codigo=BOB -F "audio=@$V14_AUDIO" > /tmp/v14-recepcion.json
# El outbox debe publicarse: ejecutar una vez o periódicamente sólo en este entorno.
uv run python manage.py publicar_outbox_capturas
V14_CAPTURE=$(uv run python -c 'import json; print(json.load(open("/tmp/v14-recepcion.json"))["id"])')
curl --fail-with-body -sS \
  "http://127.0.0.1:28000/api/v1/capturas/asistidas/$V14_CAPTURE/" \
  -H "Authorization: Bearer $V14_TOKEN" > /tmp/v14-propuesta.json
```

Repetir GET hasta terminar. Verificar transcripción original, modelo ASR, motor
v14, resultado REQUIRES_REVIEW, tres dimensiones 120/60/75 cm (=1200/600/750 mm),
color/material editables y ausencia de MISSING_UNIT si el ASR conservó las unidades.
Si el ASR difiere, reportar WER contra la referencia real y las diferencias;
no exigir que NLP reconstruya palabras ausentes ni falsificar el resultado.

Verificar que captura/proyección no crearon detalle comercial. Preparar y revisar
manualmente un payload integral PRF-03 conforme a `docs/openapi.yaml`, incluyendo
precio unitario positivo, catálogos reales, `sesion_borrador=$V14_SESSION` y
`detalles[].captura_asistida_id=$V14_CAPTURE`. Guardarlo en `/tmp/v14-integral.json`.
Sólo después de la revisión humana:

```bash
curl --fail-with-body -sS http://127.0.0.1:28000/api/v1/proformas/integral/ \
  -H "Authorization: Bearer $V14_TOKEN" -H 'Content-Type: application/json' \
  --data-binary @/tmp/v14-integral.json > /tmp/v14-guardado.json
```

Repetir el mismo POST para verificar idempotencia. Comprobar RevisionAsistida,
vínculo único, original/snapshot inmutables, rechazo de otro vendedor, cantidades,
precio y diferencias humanas. Comprobar ausencia de archivos en la raíz temporal
del servidor. Eliminar la copia de grabación del cliente tras la prueba según la
política efímera; no incorporarla a Git, logs, artefactos CI ni backups.
Registrar latencias ASR/NLP/total y revisión humana separadas de WER.

Al finalizar, parar únicamente los PIDs propios (`kill "$V14_API_PID" "$V14_WORKER_PID"`)
y eliminar únicamente los contenedores propios con `docker rm -f
homex-v14-integration-pg homex-v14-integration-redis`. Nunca usar `compose down`
sobre stacks ajenos. El rollback consiste en descartar este entorno aislado.

## Comandos de verificación de la entrega

Usar únicamente la base aislada anterior y no ejecutar dos procesos pytest
contra el mismo nombre de base de pruebas. Django crea `test_<nombre>`.

```bash
export DJANGO_SETTINGS_MODULE=config.settings.test
uv run pytest -q tests/unit/test_prf04_nlp* tests/unit/test_f080_contrato_nlp.py \
  tests/integration/test_prf04* tests/api/test_prf04*
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py spectacular --file /tmp/v14-openapi.yaml --validate
diff -u docs/openapi.yaml /tmp/v14-openapi.yaml
uv build --out-dir /tmp/backend-v14-dist
uv audit --locked
git diff --check
```

El CI conserva sus gates de ASR sintético, frontend fijado y despliegue en
servicios efímeros; añade build e integridad del wheel. No sustituye la validación
con voz humana real. No hay cambio de frontend ni corpus en esta entrega.

## Resultados locales (27-10-2026)

- Suite final backend: **401 passed**, 124.32 s, PostgreSQL 17 aislado.
- Focalizadas iniciales: **135 passed**; API/proyección finales: **29 passed**.
- NLP del commit exacto: **64 passed** (medidas v14 + consumidor backend).
- Gate real F08.4: `f084-real-ok`, PostgreSQL + Redis + Celery + wheel operativo.
- Ruff check/format, check Django, migraciones sin cambios y OpenAPI sin drift: OK.
- `uv build`: wheel/sdist backend; wheel NLP reproducido dos veces con mismo hash.
- `uv audit --locked`: 103 paquetes sin vulnerabilidades conocidas.
- Imports reales Celery/Redis/faster-whisper/AsrService: OK.
- La documentación genera credenciales efímeras; Gitleaks 8.24.3: sin hallazgos.

El CI del SHA final y sus enlaces se registran en el PR draft; un resultado de
un SHA anterior no se presenta como validación final. Bloqueo de aceptación de
voz humana: falta una grabación real autorizada y la ejecución/revisión del
recorrido descrito arriba. No se ha accedido al micrófono ni a los audios/filas
originales 23/24. Esta limitación no bloqueó las correcciones ni pruebas de código.
