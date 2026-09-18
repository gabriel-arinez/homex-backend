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
