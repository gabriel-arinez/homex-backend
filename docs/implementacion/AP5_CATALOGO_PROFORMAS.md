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

La cobertura AP5 comprueba altas de silla, piso y otro, permisos administrativos, unidades, atomicidad ante error de ficha, promoción vigente y PDF multipágina. El cierre correctivo requiere las pruebas de regresión AP5 y los 13 jobs verdes en ambos repositorios, incluyendo los CI posteriores a cada merge.

## Auditoría correctiva AP5 — H01 a H11

El catálogo publica `revision` de lectura y exige `If-Match` en PUT/PATCH de productos. La ausencia de versión devuelve 400 y los datos obsoletos devuelven 409, sin sobrescribir las modificaciones de otro administrador. La versión cubre producto, ficha y promoción, pero evita conflictos injustificados por movimientos de stock.

Las referencias históricas de categoría, unidad y familia se conservan aunque el valor haya sido desactivado; no es posible asignar referencias nuevas inactivas. Los importes calculados se serializan como cadenas decimales, de acuerdo con OpenAPI.

El PDF identifica las líneas `TOTAL_NEGOCIADO` y admite filas con descripciones extensas; las especificaciones se dividen entre páginas si es necesario. El frontend corrige la clonación de proxies reactivos, restaura borradores contextuales incluyendo la línea aún no guardada, conserva promociones inactivas y protege la navegación en fichas de producto.

| Hallazgo | Criterio de regresión |
| --- | --- |
| H01 | Clonar, duplicar y deshacer sobre objetos reactivos Vue |
| H02 | Distinguir importe negociado de precio unitario en PDF y previsualización |
| H03 | Edición de producto que no reactiva promoción inactiva |
| H04 | Dos administradores, segundo con revisión antigua recibe 409 |
| H05 | Ruta de producto reutilizada, no mostrar ni guardar producto anterior |
| H06 | PDF con fila y especificaciones de varias páginas |
| H07 | `response.json()` representa precio, demanda y disponibilidad como texto |
| H08 | Modificación de producto tras desactivar su clasificación histórica |
| H09 | Retorno contextual conserva datos no enviados del formulario de línea |
| H10 | Confirmación de cambios sin guardar ante navegación y cierre |
| H11 | Cobertura de estos casos en pruebas backend y frontend |

No se altera el despliegue D07, ni la promoción RC2, ni se introducen migraciones históricas.
