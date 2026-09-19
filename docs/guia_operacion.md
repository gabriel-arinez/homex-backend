# Guía de operación

1. Crear o seleccionar cliente y productos.
2. Crear proforma, agregar detalles y enviarla.
3. Aprobar: PostgreSQL crea pedido, venta de stock y orden de trabajo.
4. Registrar recibos sólo sobre pedido confirmado; anular errores, no borrarlos.
5. Pasar el pedido a `LISTO_ENTREGA` y emitir una sola nota de entrega.
6. Cancelar sólo pedidos sin recibos emitidos; la reversa de stock es automática.
