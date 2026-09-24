# F08.2 — Worker, Redis, ASR y audio efímero

## Estado

**Fase cerrada.**

Base de la fase: `126c3dfdb51c723546fbb9a4eb9cb91e4b293083` en la rama `re-refactor`.

Commit inicial F08.2: `cde76e82c3c9babb4a75f7ee7a7d31882c7322c9`.

La serie correctiva funcional culmina en
`341f45dbdb40d4bf8f7081804dcb57bae98d045c`.

GitHub Actions run #40 (`35890743980`) finalizó correctamente con **8/8 jobs verdes**,
incluido el nuevo gate `worker-smoke`.

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

El backend conserva el original privado como fuente recuperable y entrega a
`homex_nlp.asr.AsrService` una copia descartable con permisos `0600`. El servicio ASR
elimina esa copia en su `finally`, pero el original sólo se elimina después de que la
transcripción quedó confirmada en PostgreSQL.

El orden efectivo es:

```text
audio original privado
→ copia descartable ASR
→ transcripción obtenida
→ texto_transcrito confirmado en PostgreSQL
→ eliminación del original
→ NLP
```

De esta forma, un crash después de ASR pero antes del commit de la transcripción conserva
el original y puede recuperarse mediante reconciliación. Si el commit ya ocurrió y el
proceso muere antes de borrar el original, el reintento usa el texto persistido y la
limpieza lo elimina posteriormente.

Un fallo ASR conserva temporalmente el original y el intento se cierra en `ERROR`; el
archivo puede expirar según `HOMEX_AUDIO_TTL_SECONDS`. La limpieza nunca elimina por TTL
el único audio de un intento `PENDIENTE`/`PROCESANDO` que todavía no posee
`texto_transcrito`. Sí elimina copias ASR, archivos sin intento, archivos terminales o
archivos cuyo texto ya fue persistido.

`texto_normalizado` no se rellena artificialmente con el original.

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

## Evidencia final

- casos específicos F08.2 presentes en la suite: **15**;
- suite PostgreSQL completa: `133 passed in 51.44s`;
- concurrencia: `11 passed, 122 deselected in 7.57s`;
- Ruff: `All checks passed!`;
- formato: `169 files already formatted`;
- Django check: correcto;
- `makemigrations --check --dry-run`: sin cambios;
- OpenAPI regenerado, validado y sin drift;
- PostgreSQL vacío y segunda migración no-op: correctos;
- worker runtime: `uv sync --locked --extra worker` + imports de Celery, Redis,
  faster-whisper y `homex_nlp.asr.AsrService`: correcto;
- GitHub Actions run #40: **8/8 jobs verdes**.

La suite específica cubre Redis indisponible, publicación y reconciliación del outbox,
crash entre ASR y persistencia sin pérdida del original, redelivery, entrega duplicada,
worker tardío, borrado inmediato tras ASR confirmado, expiración controlada tras fallo,
preservación del audio vivo aunque venza el TTL, huérfanos sin intento, reintento NLP desde
texto producido por una captura de audio, contrato multipart, replay idempotente y ausencia
de endpoint histórico.

## Límite deliberado

F08.2 valida las fronteras del broker y worker de forma determinista. La prueba de integración con PostgreSQL real, Redis real, worker real y el wheel fijado es el gate obligatorio de F08.4, tal como establece el plan maestro.


## Correctivo de cierre F08.2

El correctivo posterior al commit inicial añade estas garantías:

- el original de audio no se entrega directamente a `AsrService`;
- la transcripción se confirma en PostgreSQL antes de eliminar el original;
- un crash en la ventana ASR→persistencia conserva material recuperable;
- el limpiador consulta el estado del intento/captura antes de borrar un original vencido;
- Redis caído o una cola demorada no provocan pérdida del único audio pendiente;
- un fallo NLP posterior a ASR permite crear otro intento que reutiliza
  `texto_transcrito` sin volver a usar audio;
- OpenAPI separa el cuerpo JSON de texto del contrato multipart;
- CI incorpora un smoke específico que instala el extra `worker` y verifica imports de
  Celery, Redis, faster-whisper y la API pública ASR.

El correctivo quedó validado por GitHub Actions run #40 sobre
`341f45dbdb40d4bf8f7081804dcb57bae98d045c`. No quedan bloqueos conocidos dentro
del alcance de F08.2. La integración obligatoria con Redis real + worker real se mantiene,
según el Plan Maestro, como gate de F08.4.
