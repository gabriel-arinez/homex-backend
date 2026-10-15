# AP5 — Catálogo comercial y presentación de proformas

## Alcance implementado

AP5 reutiliza `Producto`, `FamiliaProducto`, `ProductoSilla`, `ProductoPiso` y `DescuentoProducto`; no crea tablas ni modifica la semántica de stock. El alta y la edición del producto base, su ficha específica y su promoción forman ahora una única transacción del endpoint de productos. Un error en cualquier ficha revierte el producto completo.

El contrato expone etiquetas semánticas de categoría, unidad y familia, la ficha aplicable, la promoción y su vigencia. Los filtros continúan ejecutándose en PostgreSQL y se añadió el filtro por familia. El stock es de sólo lectura y la demanda pendiente sigue siendo referencial.

Las reglas de alta son:

- `SILLA` usa `PIEZA` y exige una ficha, sin inventar atributos empresariales obligatorios;
- `PISO_FLOTANTE` nuevo usa `M2`, sin conversión desde cajas;
- `OTRO` admite `PIEZA`, `JUEGO` o `BARRA` y no crea una categoría adicional;
- categoría y unidad siguen siendo inmutables después del alta;
- cada SKU conserva precio, unidad y stock independientes;
- una promoción usa la tabla y las fechas existentes; una línea conserva aparte el precio y descuento elegidos por el vendedor.

## Documento comercial

`GET /api/v1/proformas/{id}/documento-pdf/` genera un PDF bajo demanda. Conserva el endpoint HTML previo, respeta el aislamiento del queryset de proformas y toma importes, cliente histórico, unidades, detalles y especificaciones desde la persistencia. Las tablas repiten cabecera al cambiar de página y las condiciones vacías se omiten. No se guarda una copia del PDF ni se consume una numeración adicional.

## Compatibilidad y exclusiones

PostgreSQL continúa calculando totales y autorizando stock. AP5 no crea reservas, almacenes, mensajería, enlaces públicos, alternativas agrupadas ni movimientos por selección. Tampoco modifica el flujo Proforma → Pedido → OT/Nota de entrega. El HTML se conserva para clientes existentes.

## Validación

La cobertura AP5 comprueba altas de silla, piso y otro, permisos administrativos, unidades, atomicidad ante error de ficha, promoción vigente y PDF multipágina. La evidencia final de la suite y CI se completará en el cierre del PR.
