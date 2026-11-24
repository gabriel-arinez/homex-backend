# Modalidad de abastecimiento en catálogo (`CON_STOCK` / `BAJO_PEDIDO`)

## Resumen de reglas comerciales

1. **Modalidades en `productos`**:
   - `CON_STOCK`: productos sujetos a control de inventario físico (`stock`, `stock_minimo`, movimientos `CARGA_INICIAL`, `AJUSTE`, `VENTA`, `REVERSA_VENTA`).
   - `BAJO_PEDIDO`: productos comercializados sin necesidad de existencias físicas (ej. pisos flotantes adquiridos al proveedor tras confirmar pedido).
2. **Valores predeterminados**:
   - Nuevos productos `PISO_FLOTANTE` creados por API o importador (con `stock_inicial = 0`): `BAJO_PEDIDO`.
   - Nuevos productos `SILLA` u `OTRO`: `CON_STOCK`.
   - Registros históricos existentes antes de la migración `catalogo.0015_producto_modalidad_abastecimiento`: permanecen en `CON_STOCK` sin alterar movimientos ni inventarios previos.
3. **Confirmación de pedidos y stock (`fn_confirmar_pedido_descontar_stock`)**:
   - Los productos `BAJO_PEDIDO` pueden cotizarse y aprobarse sin stock.
   - Únicamente los productos `CON_STOCK` validan disponibilidad física y generan movimientos `VENTA`.
   - En pedidos mixtos (`CON_STOCK` + `BAJO_PEDIDO` + `MUEBLE_MEDIDA`), solo se descuenta inventario de los ítems `CON_STOCK` y se conservan las obligaciones de fabricación (`EN_PRODUCCION`) cuando hay `MUEBLE_MEDIDA`.
4. **Cancelaciones y reversiones (`fn_cancelar_pedido_revertir_stock`)**:
   - Se revierten (`REVERSA_VENTA`) únicamente los movimientos `VENTA` efectivamente registrados al confirmar el pedido.
5. **Integridad de movimientos (`fn_validar_movimiento_stock`)**:
   - Los productos `BAJO_PEDIDO` rechazan movimientos `VENTA`, `CARGA_INICIAL` y `AJUSTE`, así como la configuración de `stock_minimo` no nulo.
   - Los cambios de modalidad (`CON_STOCK` <-> `BAJO_PEDIDO`) preservan el `stock` y el historial de `movimientos_stock` existentes, permitiendo revertir ventas previas si un pedido anterior es cancelado.
