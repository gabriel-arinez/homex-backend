# Mapa SQL v3 → modelos Django

La fuente operativa será Django mediante migraciones. `homex_bd_final_v3.sql` se
conserva únicamente como referencia estructural y de comportamiento.

## Referencia auditada

```text
7f49b40eeb186d27223dac7266e166a90e8d07fd77822cf7f09c1b175bbd6ce8  homex_bd_final_v3.sql
```

| App Django | Tabla SQL | Modelo esperado |
|---|---|---|
| catalogo | catalogo_conceptos | ConceptoCatalogo |
| catalogo | catalogo_valores | ValorCatalogo |
| catalogo | productos | Producto |
| catalogo | productos_silla | ProductoSilla |
| catalogo | productos_piso | ProductoPiso |
| catalogo | productos_descuento | DescuentoProducto |
| clientes | clientes | Cliente |
| proformas | proformas | Proforma |
| proformas | proformas_detalle | DetalleProforma |
| proformas | especificaciones_mueble | EspecificacionMueble |
| pedidos | pedidos | Pedido |
| pedidos | transiciones_estado_pedido | TransicionEstadoPedido |
| ordenes_trabajo | ordenes_trabajo | OrdenTrabajo |
| notas_entrega | notas_entrega | NotaEntrega |
| recibos | recibos | Recibo |
| documentos | archivos_adjuntos | ArchivoAdjunto |
| capturas | capturas | Captura |
| capturas | intentos_captura | IntentoCaptura |
| capturas | trabajos_outbox | TrabajoOutbox |
| capturas | items_ia | ItemIA |
| capturas | items_humano | ItemHumano |
| capturas | evaluaciones_nlp | EvaluacionNLP |
| capturas | mediciones_proceso | MedicionProceso |
| movimientos_stock | movimientos_stock | MovimientoStock |

## Diferencias obligatorias v3 → requisitos finales

- Los actores `*_by_id`, vendedor, revisor, evaluador, operador y jefe de taller
  se modelarán como FK a `settings.AUTH_USER_MODEL`, no como enteros sueltos.
- `proformas_detalle` incorporará `modo_calculo` e `importe_negociado` para
  soportar `PRECIO_UNITARIO` y `TOTAL_NEGOCIADO` (G01/P29).
- `recibos` incorpora el estado `EMITIDO`/`ANULADO` y su protección T06.
- `capturas` incorpora `clave_idempotencia` única (T09), aunque el flujo se
  implementará recién en F08.
- Los triggers se trasladan por migraciones `RunSQL` después de que las tablas
  existan; no se ejecuta el DDL v3 como un segundo bootstrap.

## Correctivo F07.1 + F07.2

La auditoría posterior al primer cierre confirmó que los `default=` de Django no
habían generado defaults físicos suficientes para el contrato SQL directo. La
migración `capturas.0003_refuerzo_estructural_f071_f072` completa los defaults,
checks y la FK compuesta de v3; no sustituye checks por triggers.

### Índices auditados

- **A. Estructurales ahora:** `uq_mov_stock_venta_pedido_producto`,
  `ix_outbox_pendientes` y los índices automáticos de FKs/PK/UNIQUE requeridos
  por integridad y acceso de las cadenas de trigger.
- **B. Redundantes:** PK, UNIQUE y FK que PostgreSQL/Django ya indexan; no se
  duplicaron con los nombres `ix_*` de v3.
- **C. Diferibles a F07.6:** índices de consulta administrativa no críticos
  (`clientes`, catálogo, fechas documentales y mediciones). Se documentan para
  el plan de optimización, sin crear duplicados prematuros.

Los 39 nombres de función v3 y 35 nombres de trigger v3 permanecen cubiertos.
El esquema tiene además cuatro funciones/triggers correctivos de F07.2 para
TOTAL_NEGOCIADO, protección de totales y congelamiento comercial.
