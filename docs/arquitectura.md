# Arquitectura

HOMEX es un monolito modular Django/DRF. PostgreSQL es la autoridad de integridad comercial; Redis, Celery y NLP no son requisitos del recorrido manual de venta.

Las apps separan cuentas, catálogo, clientes, proformas, pedidos, inventario, taller, entregas, pagos y documentos. Las vistas traducen HTTP, los servicios delimitan transacciones y PostgreSQL protege stock, movimientos y recibos frente a escrituras directas.

El flujo manual es: proforma enviada → pedido/OT/movimientos → cobros → nota de entrega. Sólo una proforma aprobada crea pedido; la nota se emite desde `LISTO_ENTREGA`.
