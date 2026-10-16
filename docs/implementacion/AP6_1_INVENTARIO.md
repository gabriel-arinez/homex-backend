# AP6.1 — Integridad operativa del inventario

## Alcance y diagnóstico

La revisión se ejecutó desde `origin/main` en una base PostgreSQL 17 aislada. No se utilizó ni modificó `homex-prod`. Las migraciones Django vigentes son la fuente operativa; el SQL histórico no se modificó.

| Prioridad | Regla auditada | Autoridad | Resultado |
|---|---|---|---|
| P0 | Stock sólo cambia mediante movimientos | PostgreSQL | Ya protegido por triggers; regresión conservada. |
| P0 | `VENTA` y `REVERSA_VENTA` exactas, únicas y concurrentes | PostgreSQL + servicio transaccional | Ya implementado con bloqueo de filas y referencia única. |
| P0 | `M2` admite decimales; `PIEZA`, `JUEGO` y `BARRA` exigen enteros | PostgreSQL | Ya implementado. `CAJA` permanece sólo como legado y no se convirtió. |
| P0 | Aprobar descuenta; cancelar restituye; recibos/notas bloquean cancelación | PostgreSQL + dominio | Ya implementado y cubierto por pruebas de integración/concurrencia. |
| P1 | Demanda pendiente no reserva stock | consulta de dominio | Sólo considera `EN_REVISION`/`ENVIADA`; aprobar la retira y materializa la venta. |
| P1 | Historial operativo legible | API | Corregido: unidad, responsable y pedido derivado para reversas. |
| P1 | Filtro de movimientos por pedido | API | Corregido: incluye venta directa y reversa referida a esa venta. |
| P2 | Ajustes manuales desde UI | decisión comercial pendiente | No se añadió: no existe contrato aprobado para motivos, permisos ni operación. |

La primera entrega no necesitó migraciones. La auditoría independiente posterior incorporó la migración aditiva `movimientos_stock.0005_ap61_proteger_stock_runtime`, que refuerza privilegios de ejecución sin reescribir datos ni modificar migraciones publicadas.

## Contrato añadido

`GET /api/v1/movimientos-stock/` conserva su carácter de sólo lectura y añade:

- `producto_resumen.unidad_stock_info`, para interpretar la cantidad sin inferencias;
- `pedido_relacionado`, que devuelve el pedido directo o, **únicamente en `REVERSA_VENTA`**, el pedido de la venta original; los `AJUSTE` referenciados no heredan un pedido;
- `responsable`, con `id`, `username` y `display_name`, o `null` para operaciones de sistema.

El campo físico `pedido` de una reversa sigue siendo `NULL`. No se duplicó información en PostgreSQL y `movimiento_referencia` continúa siendo la relación autoritativa.

## Preservación histórica

- no se renombró ni eliminó `CAJA`;
- no se infirió conversión histórica `CAJA → M2`;
- no se recalcularon totales ni cantidades heredadas;
- no se editaron migraciones publicadas;
- no se modificaron estados, permisos comerciales ni reglas de cancelación;
- los movimientos permanecen inmutables y el endpoint no admite escritura.

## Evidencia

La regresión AP6 vigente demuestra pisos decimales, venta/reversa exactas, restricciones de unidades, variantes, ciclos catálogo/mueble/mixto, bloqueos de cancelación y concurrencia. AP6.1 añade una prueba API que cancela un pedido y comprueba que la reversa aparece al filtrar por ese pedido con referencia, unidad y responsable correctos.

Resultados locales antes de publicar la rama:

- suite PostgreSQL completa: **248 passed**;
- concurrencia: **13 passed, 235 deselected**;
- regresión consolidada AP6/AP6.1: **29 passed**;
- Ruff y formato: correctos;
- `manage.py check`: correcto;
- `makemigrations --check --dry-run`: sin cambios;
- OpenAPI regenerado y sin drift;
- migración desde PostgreSQL vacío: correcta;
- segunda ejecución de `migrate`: no-op;
- `git diff --check`: limpio.

Evidencia remota:

- commit funcional: `708e872c9fac6f1e947b389c5a6ceaf3de74e90a`;
- commit coordinado actual: `2d2d6e3cf71d6c823095f9cf2dc4c7a166248676`;
- frontend fijado: `f36da69dbab479e4c6248cfc1bf9960a241329c0`;
- GitHub Actions PR run `38835336547`, intento 2: **todos los jobs verdes**, incluida la integración real frontend/backend.

El primer intento se canceló porque `uv sync` quedó bloqueado en el runner; el segundo intento del
mismo SHA terminó correctamente sin cambios de código.

## Cierre de observaciones de auditoría independiente (AP6.1)

### P1 — Permisos de stock en PostgreSQL

El control anterior dependía también de la variable de sesión
`homex.stock_update_context`; una cuenta runtime con permiso de
`UPDATE(productos.stock)` podía fijarla mediante SQL. La corrección separa
la facultad real de escritura:

- migración aditiva `movimientos_stock.0005_ap61_proteger_stock_runtime`:
  `fn_actualizar_stock_desde_movimiento()` pasa a `SECURITY DEFINER`
  con `search_path = pg_catalog, public, pg_temp`, manteniendo la validación
  original de movimientos y las restricciones contra stock negativo;
- `docs/sql/privilegios_runtime.sql` revoca `UPDATE` de tabla en
  `productos`, revoca explícitamente `UPDATE(stock)`, y otorga
  `UPDATE` sólo a las demás columnas existentes. El script comprueba que
  el rol runtime no conserve el permiso de stock por otra vía;
- el procedimiento de verificación de privilegios ensaya una
  `CARGA_INICIAL` legítima (debe actualizar stock), una edición de
  metadatos (debe funcionar), y un `UPDATE productos SET stock=...`
  incluso tras configurar manualmente la variable de sesión
  (debe ser rechazado por falta de privilegios).

**Orden de implementación:** migraciones como migrador → aplicación
de privilegios de runtime como migrador → validación del runtime.
No desplegar sólo la revocación de privilegios sin migrar previamente la
función privilegiada. El rol runtime no debe ser dueño de la tabla/función,
superusuario ni heredar privilegios del migrador. El rollback de la
migración no revierte el endurecimiento de seguridad.

### P2 — Semántica del pedido de ajustes referenciados

Un `AJUSTE` puede referenciar una `VENTA` como evidencia de inventario;
esto **no lo convierte** en un movimiento de ese pedido. Por tanto,
`pedido_relacionado` sólo se deriva de `movimiento_referencia` cuando el
tipo del movimiento es `REVERSA_VENTA`. El filtro `pedido` utiliza
la misma condición. Se añadió una regresión que verifica el
`AJUSTE` referenciado, su responsable `null`, la reversa y la lista
filtrada. Otra regresión comprueba `M2` decimal y su unidad.

### Alcance de las nuevas evidencias

Las pruebas de credenciales/DDL del entorno de CI son ensayos en PostgreSQL
descartable; no implican acceso ni cambios a `homex-prod`. Los resultados
de las pruebas previas consignados arriba pertenecen a la primera
entrega y no sustituyen la validación posterior de este complemento.

## Límite explícito

La creación administrativa de ajustes no forma parte de AP6.1 mientras no exista una decisión sobre capacidad autorizada, catálogo de motivos y contrato de API. El historial ya puede consultarlos si son creados por los mecanismos autorizados del backend.
