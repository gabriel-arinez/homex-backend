# PRF-04 — verificación y reproducción

Estado: implementación integrada en PR de borrador; **no constituye cierre T0–T6**.
No se ha fusionado ni desplegado. Los gates pendientes se explicitan al final.

## Evidencia local

- NLP: 77 pruebas; cuatro corpus y DocBin válidos (380/101/97/97). Wheel 0.1.1 reproducible, sin audios ni pesos; `ExtractionResult` 1.0, `RULES_ONLY`, `prf04-rules-v2`.
- Backend: 296 pruebas PostgreSQL, incluidas regresiones, permisos históricos, inmutabilidad y concurrencia. Upgrade/rollback/upgrade de capturas 0008↔0009 con una captura legada conserva texto y proforma.
- Frontend: 136 pruebas unitarias/componentes, 78 E2E UI; cuatro integraciones reales con API/PostgreSQL/Redis/Celery/ASR/NLP, incluida captura mediante MediaRecorder real de Chromium.
- Captura asistida: cero escrituras comerciales al dictar/agregar localmente, guardado integral único, reapertura y asociación de evidencia. Audio temporal restante: cero. Latencia de una captura sintética: 2753 ms, sin extrapolación de capacidad.
- NER experimental: 262 train / 62 dev / 56 test. Mejor candidato elegido en dev; test de spans P/R/F1 micro y macro 1.0 contra las anotaciones de la fuente. **No acredita semántica, productividad ni generalización de dictados reales.** Pesos fuera del repositorio; no promovidos.
- B/C incluyen ensamblado semántico offline y comparación de JSON/relaciones: B obtuvo 61/62 JSON exactos en dev; C, 51/62. Las 62 salidas por variante pasan contrato. Falta evaluación de dominio independiente/productividad; `RULES_ONLY` permanece operativo.
- Los 675 ejemplos fueron autorizados por el usuario como fuente el 21-10-2026. Se conserva la procedencia previa individual; expected declara revisión técnica desde anotaciones, no gold humano. El inventario previo conserva hashes/conteos de fuentes retiradas y Git su contenido.

Resultados NLP detallados: `PRF_04_NER_DEV.json`, `PRF_04_NER_TEST.json`,
`PRF_04_COMPARACION_DEV.json`, `PRF_04_EVALUACION_ESTRUCTURADA_DEV.json`, `PRF_04_MODELO_MANIFIESTO.json` e inventario en el
repo NLP. Evidencia de ejecución: `PRF_04_VERIFICACION_LOCAL.json` en backend.
El WER publicado allí corresponde exclusivamente al fixture **sintético**;
`wer_vendedores=null` es una medición pendiente, no cero.

## Verificaciones locales por repositorio

NLP:

```bash
cd /home/gabriel/HOMEX/homex-nlp
uv sync --locked --extra dev --extra asr --python 3.11.15
make check docbin-check distribution-check backend-consumer-check
make f10-check
uv audit --locked
git diff --check
```

Backend (con PostgreSQL de pruebas y permiso CREATEDB; nunca apuntar a producción):

```bash
cd /home/gabriel/HOMEX/homex-backend
uv sync --locked --extra dev --extra worker
export DATABASE_URL=postgresql://postgres:prf04-test-only@127.0.0.1:55404/homex_prf04
export DJANGO_SECRET_KEY=prf04-isolated-test-only-secret-at-least-thirty-two
export DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,testserver
export DJANGO_SETTINGS_MODULE=config.settings.test
make check lint format schema
uv run pytest -ra
uv run pytest -ra -m concurrency
uv audit --locked
git diff --check
```

Ejecutar las suites PostgreSQL **secuencialmente**: dos procesos pytest con el
mismo DATABASE_URL comparten el nombre de base test y pueden interferirse.

Frontend:

```bash
cd /home/gabriel/HOMEX/homex-frontend
npm ci
npm run api:generate
npx prettier --write src/generated/api
npm run contract:check
npm run backend:check -- ../homex-backend
npm run type-check
npm run lint:check
npm run format:check
npm run test:unit -- --run
npm run build
npm run test:e2e
npm audit --audit-level=moderate
git diff --check
```

## Stack integral aislado

Requiere Docker, libespeak-ng.so.1, Node 24 y el modelo ASR local. Los puertos
55404/56404/18004/4174 deben estar libres. No se usan servicios productivos.

```bash
docker run --rm -d --name homex-prf04-pg -p 127.0.0.1:55404:5432 \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=prf04-test-only \
  -e POSTGRES_DB=homex_prf04 --tmpfs /var/lib/postgresql/data postgres:17-alpine
docker run --rm -d --name homex-prf04-redis -p 127.0.0.1:56404:6379 \
  redis:7-alpine redis-server --save '' --appendonly no
cat > /tmp/homex-prf04-repro.env <<'EOF'
export DATABASE_URL=postgresql://postgres:prf04-test-only@127.0.0.1:55404/homex_prf04
export DJANGO_SECRET_KEY=prf04-isolated-test-only-secret-at-least-thirty-two
export DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,testserver
export DJANGO_SETTINGS_MODULE=config.settings.integration
export CORS_ALLOWED_ORIGINS=http://127.0.0.1:4174
export CELERY_BROKER_URL=redis://127.0.0.1:56404/0
export HOMEX_ASR_MODEL_PATH=/home/gabriel/modelos/faster-whisper-small
export HOMEX_ASR_COMPUTE_TYPE=int8
export HOMEX_AUDIO_TEMP_ROOT=/tmp/homex-prf04-audio
export OMP_NUM_THREADS=2
EOF
source /tmp/homex-prf04-repro.env
cd /home/gabriel/HOMEX/homex-backend
uv run python manage.py migrate --noinput
uv run python scripts/preparar_integracion_frontend_f09.py
uv run python scripts/generar_audio_sintetico_prf04.py
uv run python scripts/generar_audio_sintetico_prf04.py \
  --output /tmp/homex-fe08-dictado.wav \
  --texto 'Tres mesas de oficina, de melamina de dieciocho milimetros. Total cien bolivianos.'
```

En tres terminales del backend, cargar el mismo `/tmp/homex-prf04-repro.env` y ejecutar:

```bash
# Terminal 1
source /tmp/homex-prf04-repro.env
uv run python manage.py runserver 127.0.0.1:18004 --noreload
# Terminal 2
source /tmp/homex-prf04-repro.env
uv run celery -A config worker --pool=solo --concurrency=1 --hostname=prf04-test --loglevel=INFO
# Terminal 3: publica el outbox con la planificación existente
source /tmp/homex-prf04-repro.env
uv run celery -A config beat --loglevel=INFO
```

En frontend:

```bash
cd /home/gabriel/HOMEX/homex-frontend
npx playwright install chromium
FE08_AUDIO_FIXTURE=/tmp/homex-fe08-dictado.wav \
HOMEX_PRF04_AUDIO=/tmp/homex-prf04-dictado.wav \
HOMEX_INTEGRATION_API_URL=http://127.0.0.1:18004 npm run test:integration
```

Al terminar, detener los tres procesos y los dos contenedores descartables;
eliminar los WAV sintéticos de `/tmp`. No incorporar audio ni pesos a Git.

## Entrenamiento y evaluación reproducibles

```bash
cd /home/gabriel/HOMEX/homex-nlp
PRF04_TRAIN_ROOT=$(mktemp -d)
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 uv run python -m training.train_prf04 \
  --epochs 10 --destination "$PRF04_TRAIN_ROOT/run"
uv run python -m training.compare_prf04 "$PRF04_TRAIN_ROOT/run/model-dev-best" \
  "$PRF04_TRAIN_ROOT/comparacion-dev.json"
uv run python -m training.evaluate_structured_prf04 "$PRF04_TRAIN_ROOT/run/model-dev-best" \
  "$PRF04_TRAIN_ROOT/estructurado-dev.json"
uv run python -m training.evaluate_ner "$PRF04_TRAIN_ROOT/run/model-dev-best" \
  /tmp/homex-docbin-prf04/muebles_pedido/test.spacy \
  --output "$PRF04_TRAIN_ROOT/ner-test.json"
```

No usar los resultados test para ajustar el candidato. Los números publicados
corresponden a la fuente/partición/manifiestos registrados, sin promoción.

## Gates que impiden declarar PRF-04 terminado

1. Revisión de dominio de expected y enriquecimiento revisado de habla natural,
   negativos y rectificaciones; no basta el chequeo formal de los 675 ejemplos.
2. Validación independiente del ensamblado B/C con casos de habla natural,
   negativos y referencias revisadas de dominio; dev preanotado no acredita promoción.
3. WER y productividad/correcciones con sesiones autorizadas de vendedores y
   umbrales fijados según baseline real; no reemplazarlos por audio sintético.
4. Verificación final de CI y revalidación post-merge en main, sólo cuando los
   gates previos permitan integrar. Los PR permanecen en borrador.
