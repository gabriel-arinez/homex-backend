# F08.2 — Worker, Redis, ASR y audio efímero

## Estado

**Implementación local cerrada.**

Base de la fase: `126c3dfdb51c723546fbb9a4eb9cb91e4b293083` en la rama `re-refactor`.

La validación remota de GitHub Actions corresponde al commit que publique el responsable del repositorio.

## Objetivo y autoridad

Celery y Redis transportan identificadores de trabajo. PostgreSQL conserva la captura, el intento y el outbox y continúa siendo la fuente de verdad. Una caída de Redis no elimina el trabajo: el outbox permanece sin publicar y el publicador vuelve a encontrarlo.

La fase no cambia las reglas comerciales ni convierte la salida NLP en datos confirmados. `items_ia` conserva una propuesta inmutable; la revisión humana pertenece a F08.3.

## Recepción de capturas

`POST /api/v1/capturas/` acepta exactamente una entrada:

- `texto`, mediante JSON o formulario; o
- `audio`, mediante `multipart/form-data`.

Ambas variantes exigen `clave_idempotencia`, `proforma` y el detalle opcional. El audio admite `.wav`, `.mp3`, `.m4a`, `.ogg` y `.webm`, MIME `audio/*`, contenido no vacío y un máximo configurable de 25 MB.

La idempotencia del audio usa SHA-256 del contenido. Un replay compatible devuelve la captura y el intento originales sin crear otro archivo. Las reglas T09 de actor, proforma y detalle siguen aplicándose.

No existe campo de audio en `capturas`, tabla histórica de audio ni endpoint para descargarlo.

## Audio efímero privado

El archivo se escribe en `HOMEX_AUDIO_TEMP_ROOT`:

- directorio con modo `0700`;
- archivo con modo `0600`;
- escritura exclusiva a `.part` y reemplazo atómico;
- ubicación separada del storage persistente y declarada fuera de backups;
- rutas locales excluidas por `.gitignore`.

`homex_nlp.asr.AsrService` elimina el archivo en un bloque `finally` inmediatamente después del intento ASR, tanto si concluye como si falla. Si el proceso muere de forma abrupta antes de ejecutar ese bloque, la tarea independiente `capturas.limpiar_audio_temporal` elimina huérfanos cuyo `mtime` supera `HOMEX_AUDIO_TTL_SECONDS`.

Una vez transcrito, `capturas.texto_transcrito` se persiste antes de ejecutar NLP. Una recuperación posterior usa ese texto y no vuelve a requerir el audio. `texto_normalizado` no se rellena artificialmente con el original.

## ASR

El worker consume la API pública `homex_nlp.asr.AsrService`. El adapter local `TranscriptorFasterWhisper` carga `faster-whisper==1.2.1` de forma diferida.

El modelo debe existir previamente en `HOMEX_ASR_MODEL_PATH`; el worker no descarga pesos. También se configuran `HOMEX_ASR_DEVICE` y `HOMEX_ASR_COMPUTE_TYPE`. La dependencia pesada está aislada en el extra `worker`, mientras Celery forma parte del runtime base.

Instalación del worker:

```bash
uv sync --locked --extra worker
```

## Pipeline e inmutabilidad

`capturas.procesar_intento` realiza:

1. bloqueo del intento y transición `PENDIENTE → PROCESANDO`;
2. ASR sólo cuando no existe `texto_transcrito`;
3. persistencia inmediata de la transcripción;
4. ejecución del adapter `RULES_ONLY` fijado en F08.0;
5. cierre `FINALIZADO` con versiones, latencias, labels y `resultado_raw`;
6. creación de, como máximo, un `ItemIA`;
7. cierre de la captura como `COMPLETADA`.

Los errores seguros de `homex-nlp` se persisten con su código. Los errores inesperados se registran como `PIPELINE_ERROR` sin filtrar detalles internos.

Un intento `FINALIZADO` o `ERROR` se devuelve como no-op. Un intento ya `PROCESANDO` tampoco se ejecuta en paralelo. La protección física T07 de F08.1 impide modificar o borrar intentos terminales e `items_ia`.

## Outbox, redelivery y recuperación

`capturas.publicar_outbox` bloquea cada fila pendiente, publica únicamente `intento_id` y `clave_unica`, y marca `publicado_at` sólo después de que el broker acepte el mensaje. Si Redis falla, incrementa el contador de publicación y deja el trabajo pendiente.

Las tareas usan:

- `acks_late=True`;
- `reject_on_worker_lost=True`;
- `worker_prefetch_multiplier=1`;
- resultados deshabilitados.

Una caída después de publicar puede producir redelivery. La clave de tarea es la `clave_unica` del outbox y el pipeline es idempotente frente a estados terminales.

`capturas.reconciliar_outbox` recupera trabajos publicados que superaron `HOMEX_OUTBOX_RECONCILE_SECONDS`. Bajo bloqueos `FOR UPDATE`, devuelve un intento estancado de `PROCESANDO` a `PENDIENTE` y vuelve a habilitar su outbox. De este modo un crash se recupera de forma explícita, mientras una entrega duplicada ordinaria no lanza dos pipelines simultáneos.

## Operación

Procesos previstos:

```bash
uv run celery -A config worker --loglevel=INFO
uv run celery -A config beat --loglevel=INFO
```

Comandos manuales equivalentes para operación y diagnóstico:

```bash
uv run python manage.py publicar_outbox_capturas
uv run python manage.py reconciliar_outbox_capturas
uv run python manage.py limpiar_audio_temporal
```

Celery Beat programa publicación cada 5 segundos, reconciliación cada minuto y limpieza de audio cada 15 minutos. Los umbrales de recuperación y retención siguen siendo configurables y son independientes de esas frecuencias.

## Archivos principales

- `config/celery.py` y `config/settings/base.py`;
- `apps/capturas/audio.py`;
- `apps/capturas/asr.py`;
- `apps/capturas/pipeline.py`;
- `apps/capturas/outbox.py`;
- `apps/capturas/tasks.py`;
- `apps/capturas/management/commands/`;
- `apps/capturas/api/serializers.py` y `views.py`;
- `tests/integration/test_f082_worker_audio.py`;
- `docs/openapi.yaml`.

## Migraciones

F08.2 no modifica el esquema. Reutiliza las garantías físicas de F08.1.

Se validó toda la cadena desde una PostgreSQL vacía y una segunda ejecución de `migrate` concluyó con `No migrations to apply`.

## Evidencia local final

- pruebas específicas F08.2: `12 passed`;
- suite PostgreSQL completa: `130 passed`;
- concurrencia: `11 passed, 119 deselected`;
- `uv sync --locked --extra dev --extra worker`: correcto;
- Ruff: correcto;
- formato: `169 files already formatted`;
- Django check: correcto;
- `makemigrations --check --dry-run`: sin cambios;
- OpenAPI regenerado, validado y sin drift;
- PostgreSQL vacío y segunda migración no-op: correctos;
- `git diff --check`: limpio.

La suite específica cubre Redis indisponible, publicación y reconciliación del outbox, crash recuperable después de persistir texto, redelivery, entrega duplicada, worker tardío, borrado de audio en éxito y error, expiración de huérfanos, contrato multipart, replay idempotente y ausencia de endpoint histórico.

## Límite deliberado

F08.2 valida las fronteras del broker y worker de forma determinista. La prueba de integración con PostgreSQL real, Redis real, worker real y el wheel fijado es el gate obligatorio de F08.4, tal como establece el plan maestro.
