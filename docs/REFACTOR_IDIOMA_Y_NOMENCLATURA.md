# Refactor de idioma y nomenclatura

## Alcance completado

Refactor transversal posterior a F07.6 y previo a F08. El dominio comercial de HOMEX queda expresado en español; se conservan en inglés únicamente los identificadores que pertenecen a Django, DRF, Python, JWT, OpenAPI y `accounts.User`.

## Dominio comercial

Las apps son `catalogo`, `clientes`, `proformas`, `pedidos`, `movimientos_stock`, `ordenes_trabajo`, `recibos`, `notas_entrega`, `documentos` y `capturas`. No permanecen aliases ni importaciones de las apps comerciales anteriores.

Los modelos y relaciones comerciales usan el vocabulario del negocio: `ConceptoCatalogo`, `ValorCatalogo`, `Producto`, `ProductoSilla`, `ProductoPiso`, `DescuentoProducto`, `Cliente`, `Proforma`, `DetalleProforma`, `EspecificacionMueble`, `Pedido`, `TransicionEstadoPedido`, `MovimientoStock`, `OrdenTrabajo`, `Recibo` y `NotaEntrega`.

Los atributos, servicios y contratos de API comerciales fueron traducidos, por ejemplo `estado`, `fecha`, `numero`, `cliente`, `vendedor`, `proforma`, `producto`, `cantidad`, `precio_unitario`, `pago_actual` y `tipo_pago`. Las rutas son `/api/v1/proformas/`, `/api/v1/recibos/` y `/api/v1/notas-entrega/`.

## Migraciones e integridad

Las migraciones comerciales fueron reconstruidas bajo labels en español. Se preservan las secuencias para documentos comerciales y los triggers PostgreSQL que impiden cambios directos de stock, aplican movimientos de inventario y protegen la evidencia de recibos.

El esquema administrado por Django sustituye a los SQL temporales de etapas anteriores; el archivo SQL v3 se mantiene como referencia funcional del diseño, no como una segunda fuente ejecutable.

## Validación

- `python manage.py check`: correcto.
- `python manage.py makemigrations --check --dry-run`: sin cambios.
- Suite SQLite: `17 passed, 3 skipped`.
- Suite PostgreSQL real de concurrencia y triggers: `3 passed`.

Con esto, F08 puede comenzar sobre una base de dominio y persistencia consistente.
