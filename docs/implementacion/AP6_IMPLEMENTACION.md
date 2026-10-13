# AP6.0 — Implementación comercial y preparación AP3–AP5

## Alcance y fuentes

La implementación parte de las decisiones 6.0.1–6.0.20 del informe de cierre del 13-10-2026.
`homex_bd_final_v3.sql` se trató como referencia histórica; las migraciones Django nuevas son la
fuente operativa. No se desplegó ni modificó `homex-prod` y no se promovió D07 RC2.

## Matriz verificable

| Prioridad | Decisiones | Implementación | Evidencia |
|---|---|---|---|
| P0 | 6.0.1, 6.0.2, 6.0.3, 6.0.16 | Unidades `M2`, `BARRA`, `JUEGO`; cantidades/stock/movimientos `numeric(14,4)`; enteros salvo M2 | migraciones `catalogo.0008`, `proformas.0005/0006`, `movimientos_stock.0004`; tests AP6 |
| P0 | 6.0.6 | Nuevas líneas exclusivamente `PRECIO_UNITARIO`; precio y descuento explícitos; totales protegidos por PostgreSQL | `proformas.0006`, servicios y OpenAPI |
| P0 | 6.0.8, 6.0.10, 6.0.11 | Familias y variantes; unicidad de producto por proforma; familia pendiente hasta aprobación | constraint parcial, trigger de aprobación y API de familias |
| P0 | 6.0.13, 6.0.19 | OT única; catálogo resumido; detalle técnico sólo de muebles; acceso explícito `JEFE_TALLER` | permiso `taller.operar`, serializer OT y pruebas API |
| P0 | 6.0.14, 6.0.20 | Catálogo salta producción; mixto/mueble la requiere; cancelación conserva proforma aprobada y reversa única | transición/guards PostgreSQL y pruebas concurrentes |
| P1 | 6.0.4, 6.0.5, 6.0.9 | Ficha flexible v2 por componentes, original y advertencias; admite “a elección” | modelo/serializer de especificación y validación JSON |
| P1 | 6.0.7, 6.0.12, 6.0.17, 6.0.18 | Proformas separadas, sin servicios, sin maestro para muebles y sin importar NER | contrato API/importador y pruebas de regresión |
| P1 | AP3 | `BORRADOR`, `EN_REVISION`, `APROBADA`, `NO_CONCRETADA`; reapertura `NO_CONCRETADA → EN_REVISION`; legados aceptados sin renombrarlos | datos de catálogo, acciones y compatibilidad de transición |
| P1 | AP4–AP5 | clientes existentes; editor mixto; familia pendiente y características flexibles | OpenAPI y consumidor frontend generado |

## Preservación histórica

Se restauró el respaldo `homex-20261009T051913Z` en PostgreSQL aislado. Inventario previo: 0
productos, 1 proforma, 1 detalle, 0 movimientos, 0 pedidos. El detalle histórico era `PIEZA`, modo
`TOTAL_NEGOCIADO`, total Bs 1.800. Tras aplicar AP6 conservó exactamente modo y total. No había
registros `CAJA`; por ello no se ejecutó ni se infirió conversión CAJA→M2. `CAJA` permanece válido
para referencias históricas. Los reportes están en
`~/Descargas/ap6-preflight-20261013/`.

## Integridad y concurrencia

PostgreSQL bloquea proforma/producto durante aprobación, salida y reversa. Una venta decimal usa la
cantidad exacta; una única `REVERSA_VENTA` referencia su venta original. El pedido no puede forzar
cancelación si existen recibos emitidos o una entrega incompatible. La proforma aprobada sigue como
antecedente inmutable.

## Contratos y seguridad

El backend ya no sustituye el precio/descuento declarado por el vendedor al seleccionar catálogo.
`OrdenTrabajoSerializer` no expone precios ni totales y sólo incluye ficha técnica en muebles a
medida. `JEFE_TALLER` recibe `taller.operar`; los vendedores conservan el acceso operativo previsto.
HITL acepta únicamente precio unitario y nunca aprueba automáticamente la proforma.

## Límites honestos

- No se clasificaron `NA9118`/`NA9174` ni se inventaron SKU, equivalencias, precios o stock.
- NLP v1 continúa extrayendo una propuesta de un mueble; la adaptación comercial v2 ocurre en HITL.
- No se añadió edición posterior de especificaciones aprobadas ni servicios comerciales.
- La promoción/despliegue productivo y el piloto permanecen fuera de AP6.

## Correcciones de auditoría posteriores a la implementación inicial

- Migraciones nuevas `proformas.0007_ap6_unidades_redondeo` y
  `proformas.0008_ap6_caja_historica_stock` y
  `proformas.0009_ap6_inmutabilidad_unidad_stock`: la unidad de cada línea seleccionada
  debe coincidir exactamente con `Producto.unidad_stock`. Así, un zócalo en BARRA no puede
  descontarse como PIEZA; se evita cualquier conversión implícita de cantidades. Además, no
  se puede cambiar la unidad o categoría de productos que ya registran stock, movimientos o
  líneas de proforma históricas; cambiar una variante todavía no utilizada y sin existencias sí
  permanece permitido.
- El bruto de cada línea se redondea a dos decimales en PostgreSQL y el subtotal se suma desde
  `total + descuento` de las líneas. El total de la proforma coincide con la suma de sus líneas,
  incluso para fracciones `M2` con precios de un céntimo. La escritura directa de
  `proformas_detalle.total` vuelve a calcular el importe.
- `EspecificacionMuebleSerializer` valida componentes V2 con nombre y tipos de atributos;
  las advertencias son textos. No se exige decidir colores marcados «a elección» antes de producir.
- Tanto el serializador de OT como su HTML controlan el acceso por rol. El jefe de taller recibe
  las especificaciones de los muebles a medida; el catálogo sólo aparece resumido y sin precios.
  El vendedor ve los ítems, no fichas técnicas reservadas al taller.
- `tests/integration/test_ap6_correcciones.py` cubre las reglas anteriores con Django y
  PostgreSQL. En el gate `postgres-migrations`, `scripts/ap6_legacy_caja_fixture.py` inserta,
  ANTES de AP6, un piso histórico con 5 CAJA, movimiento inicial y proforma
  `TOTAL_NEGOCIADO` de Bs 1.800; después de migrar verifica unidades, inventario, equivalencia
  histórica y totales. También registra movimientos de ajuste negativos y positivos en CAJA
  histórica, devolviendo el saldo a su valor original; los pisos nuevos continúan exigiendo M2. Este caso es un fixture sintético, no evidencia de que el respaldo real
  contenga registros CAJA ni permiso para convertir CAJA a M2.
