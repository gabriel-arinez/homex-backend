# Catálogo demostrativo HOMEX (15 productos)

El archivo `tests/fixtures/catalogo_demo_15.json` contiene cinco sillas, cinco
pisos flotantes y cinco artículos diversos con SKU `DEMO-*`. Precios y nombres
son **ficticios**; no se incluyen imágenes ni existencias.

## Validar sin escribir

```bash
cd ~/HOMEX/homex-backend
.venv/bin/python manage.py cargar_catalogo_demo --actor-id <ID_VENDEDOR>
```

La simulación ejecuta la validación y revierte todas las operaciones.

## Cargar en base de desarrollo descartable

**No ejecutar contra la base real de HOMEX.** Requiere entorno de desarrollo,
`DEBUG=true`, el usuario propietario existente y habilitación explícita:

```bash
cd ~/HOMEX/homex-backend
HOMEX_ALLOW_DEMO_DATA=1 .venv/bin/python manage.py cargar_catalogo_demo --actor-id <ID_VENDEDOR> --apply
```

La carga es atómica, repetible e idempotente si los SKU y sus datos no cambian.
Si un SKU existe con datos comerciales distintos, la transacción se revierte.
No registra stock positivo ni altera productos existentes. Las imágenes pueden
subirse después, desde las galerías del sistema, con archivos autorizados.

La unidad de `PISO_FLOTANTE` es **M2**, no CAJA, según el contrato vigente.
