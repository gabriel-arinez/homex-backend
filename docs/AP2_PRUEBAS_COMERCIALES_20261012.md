# AP2 — Regresiones comerciales y autorización (12/10/2026)

## Línea base real antes de AP2

CI de `main` [38330824357](https://github.com/gabriel-arinez/homex-backend/actions/runs/38330824357): **13/13 jobs correctos**. `tests-postgresql`: **195 passed / 67.96 s**, `concurrency-postgresql`: **12 passed, 183 deselected / 7.97 s**. PostgreSQL 17 en servicio efímero de GitHub Actions. No se ha ejecutado sobre producción.

## Matriz priorizada decisión → evidencia

| Riesgo | Antes | Refuerzo AP2 | Criterio |
| --- | --- | --- | --- |
| Aprobación sin stock deja pedido o stock parcial (P0) | `test_f073_ventas.py` servicio | `test_ap2_regresion_comercial.py::test_ap2_aprobacion_api_sin_stock_revierte_todos_los_efectos` | HTTP 400 y **sin** pedido, OT, VENTA ni transición |
| Repetición de POST crea segunda venta (P0) | Doble aprobación de servicio/concurrencia | `test_ap2_doble_post_aprobacion_no_duplica_stock_ni_ot` | HTTP rechazo de repetición; exactamente una VENTA/OT |
| IDOR de listado/acción (P0) | Detalle y acciones con 404 | `test_ap2_listado_y_aprobacion_no_filtran_datos_entre_vendedores` | Vendedor solo ve sus filas; ajeno recibe 404; admin ve ambas; sin efectos |
| Cancelación con cobro emitido genera reversa (P0) | Reglas de recibo y reversa | `test_ap2_cancelacion_con_recibo_emitido_no_crea_reversa` | HTTP rechazo; recibo, estado, stock y reversas intactos |
| Transiciones/recibos/entrega (P1) | `test_f076_e2e.py`, `test_f074_cobros.py` | Regresión previa conservada | Recorrido JWT→cliente→catálogo→proforma→pedido→recibo→nota y cancelación elegible |
| Dos ventas o cancelaciones concurrentes (P0) | `test_f073_ventas.py` y `test_f074_concurrencia.py` | Gate `-m concurrency` conservado | Solo un pedido/venta/reversa, según caso |

## Validación

```bash
uv sync --locked --extra dev
uv run pytest -q tests/api/test_ap2_regresion_comercial.py
uv run pytest -ra
uv run pytest -ra -m concurrency
uv run ruff check .
uv run ruff format --check .
```

Pruebas de BD requieren `DATABASE_URL`, `DJANGO_SECRET_KEY` y `DJANGO_SETTINGS_MODULE=config.settings.test`, PostgreSQL 17 aislado y permisos de migración según CI. Mantener `uv.lock` y no usar SQLite como sustituto.

## Deuda separada para AP3–AP5

El contrato vigente utiliza `ENVIADA`, no el futuro `EN_REVISION`; no cambiar test esperado para simular implementación del rediseño. Pendientes funcionales: renovación de vigencia, nueva emisión, edición antes de aprobación, proforma `NO_CONCRETADA`, mutabilidad de proforma aprobada, nuevos snapshots y flujo UI de persistencia local/concurrencia. Son pruebas de aceptación de las próximas fases, **no** afirmaciones de cumplimiento actual. No se cambió SQL ni migración.
