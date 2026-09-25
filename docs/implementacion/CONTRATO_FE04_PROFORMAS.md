# Contrato backend para FE04 — proformas manuales

## Objetivo

Cerrar los bloqueos contractuales detectados al iniciar FE04 sin trasladar reglas comerciales al
frontend.

## Decisiones de negocio

- el mismo vendedor puede aprobar su propia proforma;
- no existe una capacidad separada `comercial.aprobar`;
- una proforma sólo es editable mientras está en `BORRADOR`;
- `ENVIADA` y `APROBADA` quedan congeladas para edición de cabecera, detalles,
  especificaciones y adjuntos;
- la cancelación posterior a la aprobación pertenece al PEDIDO;
- no se implementa una transición nueva de proforma a `ANULADA` sin una regla de negocio
  explícita.

## Listado

`GET /api/v1/proformas/` usa paginación común HOMEX:

- `page`;
- `page_size`, 20 por defecto y 100 máximo.

Búsqueda `search`:

- número exacto de proforma;
- título;
- nombre, apellido, empresa o celular del cliente;
- snapshots del cliente.

Filtros:

- `estado=<codigo>`;
- `moneda=<codigo>`;
- `cliente=<id>`;
- `fecha_desde=YYYY-MM-DD`;
- `fecha_hasta=YYYY-MM-DD`.

El aislamiento por vendedor se aplica antes de filtros y búsqueda.

## Semántica publicada

Las proformas conservan los IDs existentes por compatibilidad y agregan:

- `estado_info: {id, codigo, nombre}`;
- `moneda_info: {id, codigo, nombre}`;
- `cliente_resumen`.

Los detalles agregan:

- `tipo_item_info`;
- `unidad_info`.

Las especificaciones agregan:

- `tipo_mueble_info`.

El listado usa un serializer liviano y no incluye `detalles`.

## Opciones estructurales

`GET /api/v1/catalogo/opciones/?concepto=<CODIGO>`

expone valores activos, autenticados para vendedor, de:

- `ESTADO_PROFORMA`;
- `MONEDA`;
- `TIPO_ITEM`;
- `UNIDAD_MEDIDA`;
- `TIPO_MUEBLE`.

Cada opción publica `id`, `concepto_codigo`, `codigo` y `nombre`. El frontend no debe
hardcodear identificadores.

## Conflictos

Los errores de formato o validación de payload siguen usando `400`.

Los conflictos de estado o concurrencia usan `409`, incluyendo:

- modificar una proforma que ya no está en BORRADOR;
- reenviar una proforma ya enviada;
- aprobar una proforma que ya no está ENVIADA;
- conflictos comerciales PostgreSQL traducidos por la capa de pedidos.

## OpenAPI

Se corrige la documentación de:

- creación de proforma: request `CrearProforma`, response `Proforma`;
- creación de detalle: request/response `DetalleProforma`;
- creación de especificación: request/response `EspecificacionMueble`;
- envío: sin body y response `Proforma`;
- aprobación: sin body y response `AprobarProformaRespuesta`;
- listados paginados y parámetros;
- endpoint de opciones estructurales;
- respuestas 409 de operaciones con conflicto.


## Evidencia de cierre

Contrato funcional validado en:

- rama: `feat/fe04-contrato-proformas`;
- commit funcional: `8bf4ca5aa3c2701bf30d8d05283074b57b532879`;
- GitHub Actions: run `36102087034`;
- resultado: **9/9 jobs verdes**;
- suite PostgreSQL: `167 passed`;
- concurrencia PostgreSQL: `12 passed, 155 deselected`;
- Ruff: correcto y `187 files already formatted`;
- Django check: correcto;
- migraciones PostgreSQL: correcto;
- OpenAPI: validado y sin drift;
- privilegios runtime: correcto;
- worker smoke e integración real F08: correctos.

Con esta evidencia, los bloqueos contractuales identificados al iniciar FE04 quedan resueltos y
el frontend puede regenerar sus tipos contra este contrato antes de continuar la implementación de
proformas manuales.
