# Importador integral de datos comerciales (`importar_datos_homex`)

El comando `importar_datos_homex` valida, normaliza, reproduce y audita paquetes maestros `HOMEX_DATA_MASTER` sin desactivar triggers ni alterar las marcas de auditoría reales. Por defecto opera en modo **no destructivo** (`--dry-run`).

## Ruta rápida (`homex_evaluacion`)

1. **Dry-run documental** (verifica manifiestos SHA-256, 71 incidencias pendientes e imágenes candidatas sin escribir en la base):

```bash
uv run python manage.py importar_datos_homex ~/Descargas/HOMEX_DATA_MASTER_v04.zip \
  --perfil documental \
  --reporte-json /tmp/reporte_documental.json
```

2. **Dry-run escenario** (simulación aislada con reloj comercial virtual al corte `2026-11-27`, sin persistir cambios):

```bash
uv run python manage.py importar_datos_homex ~/Descargas/HOMEX_DATA_MASTER_v04.zip \
  --perfil escenario \
  --fecha-corte 2026-11-27 \
  --simular-reloj-virtual \
  --reporte-json /tmp/reporte_escenario_dry_run.json
```

3. **Importación autorizada** (persiste solo si pasa validación, triggers PostgreSQL y conciliación contra oráculos):

```bash
uv run python manage.py importar_datos_homex ~/Descargas/HOMEX_DATA_MASTER_v04.zip \
  --perfil escenario \
  --fecha-corte 2026-11-27 \
  --simular-reloj-virtual \
  --autorizar-importacion \
  --reporte-json /tmp/reporte_escenario_import.json
```

4. **Auditoría posterior** (solo lectura contra la base de datos):

```bash
uv run python manage.py importar_datos_homex ~/Descargas/HOMEX_DATA_MASTER_v04.zip \
  --perfil escenario \
  --fecha-corte 2026-11-27 \
  --auditar \
  --reporte-json /tmp/reporte_auditoria.json
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
| `--auditar` | Ejecuta únicamente la conciliación contra oráculos | Desactivado |
| `--reporte-json` | Guarda el reporte estructurado en disco | Opcional |

## Arquitectura y garantías

- **Seguridad ZIP y manifiestos**: `PaqueteMaestroHomex` bloquea *path traversal* (`..`, rutas absolutas, `\`), enlaces simbólicos y límites de tamaño; verifica SHA-256 de `manifiesto.json`, `manifiesto_resolucion.json` y `manifiesto_escenario.json`.
- **Reloj comercial aislado**: `apps/core/tiempo_comercial.py` usa un `ContextVar` para fechas comerciales (`Proforma.fecha`, `vigencia`, `Recibo.fecha`, `NotaEntrega.fecha`, `OrdenTrabajo.fecha_inicio`/`fecha_fin`) sin tocar el reloj del sistema ni alterar `creado_en` / `actualizado_en`.
- **Triggers y privilegios mínimos**: reutiliza `importar_catalogo` y los servicios de `proformas`, `pedidos`, `recibos` y `notas_entrega`; compatible con `homex_eval_runtime` (sin `UPDATE` sobre `productos.stock`).
- **Idempotencia**: claves UUID5 deterministas en `Proforma.clave_idempotencia`, `Recibo.clave_idempotencia`, `Producto.sku` y marcadores trazables `[HOMEX_IMPORT perfil=... source_id=...]` en `observaciones`.

## Recuperación ante errores

- Toda la ejecución corre dentro de `@transaction.atomic`. Ante cualquier error de validación, trigger PostgreSQL o discrepancia en la auditoría, la transacción completa se revierte sin dejar registros parciales.
- Si el paquete presenta inconsistencias (p. ej. clientes `EMPRESA` sin persona de contacto exigida por `fn_validar_cliente()`), el comando reporta los identificadores afectados y detiene la importación sin alterar los datos fuente.
