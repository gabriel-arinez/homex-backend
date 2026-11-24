# Modalidad de abastecimiento en catálogo (`CON_STOCK` / `BAJO_PEDIDO`)

## Resumen de reglas comerciales

1. **Modalidades en `productos`**:
   - `CON_STOCK`: productos sujetos a control de inventario físico (`stock`, `stock_minimo`, movimientos `CARGA_INICIAL`, `AJUSTE`, `VENTA`, `REVERSA_VENTA`).
   - `BAJO_PEDIDO`: productos comercializados sin necesidad de existencias físicas (ej. pisos flotantes adquiridos al proveedor tras confirmar pedido).
   - `ck_productos_bajo_pedido_sin_stock_minimo`: garantiza en PostgreSQL que todo producto `BAJO_PEDIDO` tenga `stock_minimo IS NULL`.
2. **Valores predeterminados**:
   - Nuevos productos `PISO_FLOTANTE` creados por API o importador (con `stock_inicial = 0`): `BAJO_PEDIDO`.
   - Nuevos productos `SILLA` u `OTRO`: `CON_STOCK`.
   - Registros históricos existentes antes de `catalogo.0015_producto_modalidad_abastecimiento`: permanecen en `CON_STOCK` sin alterar movimientos ni inventarios previos.
3. **Política segura de cambio de modalidad (`trg_validar_cambio_modalidad_producto`)**:
   - `CON_STOCK` → `BAJO_PEDIDO`: bloqueado en API y PostgreSQL mientras `stock > 0` (evita existencias físicas sin posibilidad de gestión). Si `stock = 0`, se permite conservando íntegramente el historial de `movimientos_stock` y limpiando `stock_minimo`.
   - `BAJO_PEDIDO` → `CON_STOCK`: permitido conservando existencias e historial previo.
4. **Confirmación de pedidos y stock (`fn_confirmar_pedido_descontar_stock`)**:
   - Los productos `BAJO_PEDIDO` pueden cotizarse y aprobarse sin stock.
   - Únicamente los productos `CON_STOCK` validan disponibilidad física y generan movimientos `VENTA`.
   - En pedidos mixtos (`CON_STOCK` + `BAJO_PEDIDO` + `MUEBLE_MEDIDA`), solo se descuenta inventario de los ítems `CON_STOCK` y se conservan las obligaciones de fabricación (`EN_PRODUCCION`) cuando hay `MUEBLE_MEDIDA`.
5. **Cancelaciones, concurrencia e indicadores (`fn_cancelar_pedido_revertir_stock`, `fn_validar_movimiento_stock`)**:
   - Se revierten (`REVERSA_VENTA`) únicamente los movimientos `VENTA` efectivamente registrados al confirmar el pedido, incluso si el producto cambió posteriormente a `BAJO_PEDIDO`.
   - `fn_validar_movimiento_stock()` bloquea la fila de `productos` con `FOR UPDATE` antes de validar la modalidad, serializando ajustes, confirmaciones, reversiones y cambios de modalidad concurrentes.
   - `disponibilidad_referencial` retorna `null` en API para productos `BAJO_PEDIDO` para evitar falsos déficits referenciales, manteniendo `demanda_pendiente` informativa.
