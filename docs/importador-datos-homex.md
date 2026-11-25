# Importador integral de datos comerciales (`importar_datos_homex`)

El comando `importar_datos_homex` valida, normaliza, reproduce y audita paquetes maestros `HOMEX_DATA_MASTER` sin desactivar triggers ni alterar las marcas de auditoría reales. Por defecto opera en modo **no destructivo** (`--dry-run`).

## Ruta rápida (`homex_evaluacion`)

1. **Dry-run documental** (verifica manifiestos SHA-256, 71 incidencias pendientes e imágenes candidatas sin escribir en la base):

```bash
.venv/bin/python manage.py importar_datos_homex ~/Descargas/HOMEX_DATA_MASTER_v05.zip \
  --perfil documental \
  --reporte-json ~/Descargas/reporte_documental_v05.json
```

2. **Dry-run escenario** (simulación aislada con reloj comercial virtual al corte `2026-11-27`, sin persistir cambios):

```bash
.venv/bin/python manage.py importar_datos_homex ~/Descargas/HOMEX_DATA_MASTER_v05.zip \
  --perfil escenario \
  --fecha-corte 2026-11-27 \
  --simular-reloj-virtual \
  --reporte-json ~/Descargas/reporte_escenario_dry_run_v05.json
```

3. **Importación autorizada** (persiste solo si pasa validación, protección de entorno, triggers PostgreSQL y conciliación individual/global contra oráculos):

```bash
.venv/bin/python manage.py importar_datos_homex ~/Descargas/HOMEX_DATA_MASTER_v05.zip \
  --perfil escenario \
  --fecha-corte 2026-11-27 \
  --simular-reloj-virtual \
  --autorizar-importacion \
  --reporte-json ~/Descargas/reporte_escenario_import_v05.json
```

4. **Auditoría posterior** (solo lectura contra la base de datos):

```bash
.venv/bin/python manage.py importar_datos_homex ~/Descargas/HOMEX_DATA_MASTER_v05.zip \
  --perfil escenario \
  --fecha-corte 2026-11-27 \
  --auditar \
  --reporte-json ~/Descargas/reporte_auditoria_v05.json
```

## Argumentos principales

| Argumento | Descripción | Predeterminado |
|---|---|---|
| `paquete` | Ruta al `.zip` maestro o carpeta descomprimida | Obligatorio |
| `--perfil` | Perfil estricto: `documental` o `escenario` | Obligatorio |
| `--dry-run` | Ejecuta dentro de una transacción con rollback final | Activo por defecto |
| `--autorizar-importacion` | Confirma la transacción en PostgreSQL | Desactivado |
| `--fecha-corte` | Fecha límite `YYYY-MM-DD` para eventos cronológicos | Fecha local actual |
| `--simular-reloj-virtual` | Habilita `reloj_comercial_simulado` para eventos futuros | Desactivado |
| `--actor-username` / `--actor-id` | Actor administrativo para catálogos técnicos | `ana.huallpara` o primer `staff` |
| `--permitir-base-aislada` | Autoriza explícitamente una base aislada distinta de `homex_evaluacion` / `test_*` | Opcional |
| `--auditar` | Ejecuta únicamente la conciliación contra oráculos | Desactivado |
| `--reporte-json` | Guarda el reporte estructurado en disco | Opcional |

## Comportamiento de `dry-run`, secuencias, trazabilidad y fechas

- **Secuencias PostgreSQL en `--dry-run`:** `nextval()` (`seq_proformas_numero`, `seq_recibos_numero`, `seq_notas_entrega_numero`, `seq_ordenes_trabajo_numero` e `IDENTITY`) es no transaccional en PostgreSQL. Al revertir un `--dry-run`, no quedan registros ni archivos persistentes en la base ni en `MEDIA_ROOT` (las imágenes cargadas en disco dentro de una transacción revertida o fallida también se limpian vía `transaction.on_commit`), pero los contadores de secuencia quedan avanzados. **No reiniciar secuencias** en bases compartidas (`homex_evaluacion`).
- **Trazabilidad persistente e idempotencia (`v06`):** `importacion_procedencia` (`RegistroProcedenciaImportacion`) almacena `(perfil, entidad, source_id)` con `objeto_id` y `metadata_json`, sin contaminar campos comerciales (`observaciones`) con marcadores `[HOMEX_IMPORT]` y exponiendo `sku_comercial` en `Producto.sku`.
- **Fechas comerciales vs. auditoría real:**
  - `Proforma.fecha` y `Proforma.ultima_actividad_comercial` reflejan la cronología comercial simulada (`fecha_hora_simulada`), preservando `creado_en` y `actualizado_en` reales.
  - `OrdenTrabajo.fecha_entrega` almacena `fecha_entrega_programada` (incluyendo las 26 entregas programadas de diciembre 2026 [20] y enero 2027 [6]).
  - `NotaEntrega.fecha` almacena la fecha de emisión de la nota (`LISTO_ENTREGA`).
  - `Pedido.fecha_entrega_efectiva` almacena la fecha efectiva de entrega al pasar a `ENTREGADO`.
  - `MovimientoStock.fecha` refleja `fecha_hora_simulada` (propagada a PostgreSQL con el GUC transaccional `homex.fecha_comercial_simulada`), conservando `MovimientoStock.registrado_en` con `CURRENT_TIMESTAMP`.
- **Imágenes de referencia (`v06`):** incorpora las 18 imágenes autorizadas vía `reemplazar_imagen_principal`, verificando SHA-256 y manteniendo las 5 imágenes pendientes sin asignar.

## Crear y poblar un entorno aislado `v06` (sin tocar `homex_evaluacion`)

```bash
# 1. Variables aisladas de almacenamiento, audio, broker Redis y entorno de evaluación
export HOMEX_MEDIA_ROOT=/var/lib/homex/v06-media
export HOMEX_AUDIO_TEMP_ROOT=/var/lib/homex/v06-audio-tmp
export CELERY_BROKER_URL=redis://127.0.0.1:6379/12
export HOMEX_ENTORNO_EVALUACION=true

# 2. Levantar PostgreSQL 16/17 aislado y migrar con homex_migrator
DATABASE_URL="postgresql://homex_migrator:<MIGRATOR_PASSWORD>@127.0.0.1:15437/homex_v06" \
  .venv/bin/python manage.py migrate --noinput

# 3. Crear rol runtime sin UPDATE(productos.stock) y los 4 usuarios comerciales
#    (ana.huallpara con is_staff=True y is_superuser=False;
#     alvaro.huallpa y rodrigo.ramos en ENCARGADO_TIENDA; antonio.flores en JEFE_TALLER)

# 4. Dry-run v06 al corte completo (2026-11-27)
DATABASE_URL="postgresql://homex_runtime:<RUNTIME_PASSWORD>@127.0.0.1:15437/homex_v06" \
  .venv/bin/python manage.py importar_datos_homex ~/Descargas/HOMEX_DATA_MASTER_v06.zip \
  --perfil escenario --fecha-corte 2026-11-27 --simular-reloj-virtual \
  --permitir-base-aislada homex_v06

# 5. Importación autorizada + idempotencia + auditoría
DATABASE_URL="postgresql://homex_runtime:<RUNTIME_PASSWORD>@127.0.0.1:15437/homex_v06" \
  .venv/bin/python manage.py importar_datos_homex ~/Descargas/HOMEX_DATA_MASTER_v06.zip \
  --perfil escenario --fecha-corte 2026-11-27 --simular-reloj-virtual \
  --autorizar-importacion --permitir-base-aislada homex_v06
```

## Protección de entorno, seguridad ZIP y recuperación

- **Protección de entorno:** `--autorizar-importacion` bloquea `config.settings.production` y bases no autorizadas (`homex_prod`, `homex_dev`, `postgres`, etc.). Sólo permite `homex_evaluacion`, bases de prueba (`test_*`, `homex_test*`, `homex_eval_*`, `homex_aislada*`) o la base indicada explícitamente con `--permitir-base-aislada`.
- **Seguridad ZIP y manifiestos:** `PaqueteMaestroHomex` rechaza *path traversal*, enlaces simbólicos, entradas duplicadas, colisiones de ruta normalizada, tamaños excesivos y archivos obligatorios sin cobertura en los manifiestos SHA-256.
- **Atomicidad integral:** si falla cualquier validación, trigger PostgreSQL o la conciliación final contra oráculos, `@transaction.atomic` revierte toda la ejecución sin dejar registros comerciales parciales.
