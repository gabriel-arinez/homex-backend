# Contrato FE05 — Operaciones

## Objetivo

Completar el contrato backend requerido por FE05 del frontend sin trasladar
autoridad comercial a Vue ni crear estructuras de negocio nuevas.

Base de la rama:

`9fac22ecc4f471237e6611b5a226532ab2a037ab`

Rama:

`feat/fe05-contrato-operaciones`

## Movimientos de stock

Se publica un historial estrictamente de sólo lectura:

- `GET /api/v1/movimientos-stock/`;
- `GET /api/v1/movimientos-stock/{id}/`.

Filtros soportados:

- `search`: SKU, nombre de producto u observaciones;
- `producto`;
- `pedido`;
- `tipo_movimiento`;
- `fecha_desde`;
- `fecha_hasta`;
- paginación estándar `page/page_size`.

La respuesta incluye información semántica del producto y del tipo de
movimiento. No se publica ninguna mutación directa: `VENTA`,
`REVERSA_VENTA`, `CARGA_INICIAL` y demás efectos continúan bajo autoridad
de los casos de uso y triggers PostgreSQL.

## Órdenes de trabajo

El detalle de una OT incorpora las líneas reales de la proforma que originó su
pedido, además de:

- número de proforma;
- estado semántico;
- estado de saldo semántico;
- datos persistidos de recepción/entrega.

No se calcula ni expone porcentaje de avance ficticio.

## Documentos comerciales

Se exponen los renderizadores ya existentes de F07.4 como descargas HTML:

- `GET /api/v1/proformas/{id}/documento/`;
- `GET /api/v1/ordenes-trabajo/{id}/documento/`;
- `GET /api/v1/recibos/{id}/documento/`;
- `GET /api/v1/notas-entrega/{id}/documento/`.

No se crean tablas `documentos_emitidos`, contadores ni duplicados de
evidencia. Cada documento se deriva de datos persistidos y respeta el queryset
autorizado de su recurso.

## Catálogos operativos

`GET /api/v1/catalogo/opciones/` admite también:

- `ESTADO_PEDIDO`;
- `ESTADO_ORDEN_TRABAJO`;
- `TIPO_PAGO`;
- `TIPO_MOVIMIENTO`.

Esto permite que FE05 muestre nombres/códigos reales sin hardcodear IDs.

## Permisos

- usuario sin rol comercial: `403`;
- vendedor: acceso a su flujo comercial para pedidos/OT/recibos/notas/documentos;
- movimientos de stock: historial operacional global de sólo lectura para
  usuarios comerciales;
- staff/superuser: alcance global;
- acceso directo a documento comercial ajeno: `404`.

## Pruebas específicas

`tests/api/test_fe05_contrato_operaciones.py` cubre:

- listado/filtros de movimientos;
- información semántica;
- mutaciones de movimientos rechazadas con `405`;
- usuario sin rol;
- detalle real de OT;
- descarga de los cuatro documentos;
- aislamiento entre vendedores;
- publicación de catálogos operativos FE05.

## Migraciones

No se crean migraciones. El cambio es exclusivamente de API/serialización,
documentación y pruebas sobre entidades ya existentes.

## OpenAPI

`docs/openapi.yaml` debe regenerarse desde este contrato y superar
`openapi-drift` antes de cerrar la rama.

## Cierre

La fase contractual sólo se considera cerrada cuando todos los jobs del CI
remoto estén verdes y el OpenAPI versionado corresponda exactamente al código.
