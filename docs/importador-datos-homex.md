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

## Comportamiento de `dry-run`, secuencias y fechas de entrega

- **Secuencias PostgreSQL en `--dry-run`:** `nextval()` (`seq_proformas_numero`, `seq_recibos_numero`, `seq_notas_entrega_numero`, `seq_ordenes_trabajo_numero` e `IDENTITY`) es no transaccional en PostgreSQL. Al revertir un `--dry-run`, no quedan registros ni archivos persistentes en la base ni en `MEDIA_ROOT`, pero los contadores de secuencia quedan avanzados. **No reiniciar secuencias** en bases compartidas (`homex_evaluacion`).
- **Fechas de entrega:**
  - `OrdenTrabajo.fecha_entrega` almacena `fecha_entrega_programada` (incluyendo las 26 entregas programadas de diciembre 2026 [20] y enero 2027 [6]).
  - `NotaEntrega.fecha` almacena la fecha de emisión de la nota (`LISTO_ENTREGA`).
  - **Limitación del modelo:** `Pedido` no posee un campo `fecha_entrega_efectiva` para registrar por separado `fecha_entrega_simulada` al pasar a `ENTREGADO`. Se conserva en la traza de eventos del paquete y se propone agregar `fecha_entrega_efectiva` en `pedidos` solo si futuras consultas de reporte lo requieren.

## Protección de entorno, seguridad ZIP y recuperación

- **Protección de entorno:** `--autorizar-importacion` bloquea `config.settings.production` y bases no autorizadas (`homex_prod`, `homex_dev`, `postgres`, etc.). Sólo permite `homex_evaluacion`, bases de prueba (`test_*`, `homex_test*`, `homex_eval_*`, `homex_aislada*`) o la base indicada explícitamente con `--permitir-base-aislada`.
- **Seguridad ZIP y manifiestos:** `PaqueteMaestroHomex` rechaza *path traversal*, enlaces simbólicos, entradas duplicadas, colisiones de ruta normalizada, tamaños excesivos y archivos obligatorios sin cobertura en los manifiestos SHA-256.
- **Atomicidad integral:** si falla cualquier validación, trigger PostgreSQL o la conciliación final contra oráculos, `@transaction.atomic` revierte toda la ejecución sin dejar registros comerciales parciales.
