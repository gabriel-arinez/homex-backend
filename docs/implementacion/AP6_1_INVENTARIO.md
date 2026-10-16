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

No fue necesaria una migración: los datos y restricciones físicas ya satisfacen AP6.1. La corrección es aditiva y de lectura sobre el contrato de movimientos.

## Contrato añadido

`GET /api/v1/movimientos-stock/` conserva su carácter de sólo lectura y añade:

- `producto_resumen.unidad_stock_info`, para interpretar la cantidad sin inferencias;
- `pedido_relacionado`, que devuelve el pedido directo o el pedido de la `VENTA` original cuando el registro es una reversa;
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

La evidencia CI remota se añadirá después de publicar el commit.

## Límite explícito

La creación administrativa de ajustes no forma parte de AP6.1 mientras no exista una decisión sobre capacidad autorizada, catálogo de motivos y contrato de API. El historial ya puede consultarlos si son creados por los mecanismos autorizados del backend.
