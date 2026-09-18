# Importación de sillas confirmadas

`import_sillas` importa únicamente fichas comerciales aprobadas. El dataset NER no es una fuente de inventario: sus 19 líneas describen texto y etiquetas para entrenamiento, pero no contienen SKU, precio, stock ni una presentación comercial inequívoca.

## Archivo de entrada

El comando recibe un arreglo JSON. Cada objeto representa un SKU físico con existencia propia y requiere:

```json
[
  {
    "sku": "CODIGO-CONFIRMADO",
    "name": "Nombre comercial confirmado",
    "list_price": "1500.00",
    "stock": 3,
    "brand_code": "CODIGO_MARCA_EXISTENTE",
    "model": "Modelo",
    "primary_color_code": "COLOR_EXISTENTE",
    "secondary_color_code": null,
    "specifications": {"atributo": "valor confirmado"},
    "observations": ""
  }
]
```

Los códigos de marca y color son opcionales, pero, si se proporcionan, deben existir previamente en sus catálogos. No se crean valores desde texto libre. Un color secundario requiere uno primario. El importador no acepta duplicados de SKU dentro del archivo ni sobrescribe una ficha existente que difiera.

## Ejecución

```bash
uv run python manage.py import_sillas --input catalogo-sillas-confirmado.json --dry-run
uv run python manage.py import_sillas --input catalogo-sillas-confirmado.json
```

`--dry-run` valida toda la carga y devuelve las cantidades que se crearían sin hacer cambios. La ejecución real crea el producto con stock cero y registra una única `CARGA_INICIAL`; nunca escribe la existencia directamente. Ejecutar el mismo archivo una segunda vez informa la fila como omitida y no duplica productos ni movimientos.

## Insumos pendientes para una carga real

HOMEX debe proporcionar por cada presentación: SKU, nombre comercial, precio BOB, stock inicial y el mapa de color/presentación. También faltan los catálogos reales de pisos, productos `OTRO` y promociones. Hasta recibirlos, no se debe ejecutar la carga sin `--dry-run`.
