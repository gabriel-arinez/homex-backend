# Contrato de listados FE03 — clientes y productos

## Objetivo

Cerrar el contrato HTTP mínimo que FE03 necesita para consumir clientes y productos sin cargar
colecciones completas ni inventar búsqueda, filtros o paginación en Vue.

Este trabajo no cambia autoridad comercial ni permisos. Los querysets autorizados del backend se
aplican antes de búsqueda y filtros.

## Paginación común

Los listados de clientes y productos usan paginación por número de página:

- `page`: página solicitada;
- `page_size`: tamaño solicitado;
- tamaño por defecto: `20`;
- tamaño máximo: `100`.

La respuesta de listado tiene la forma:

```json
{
  "count": 0,
  "next": null,
  "previous": null,
  "results": []
}
```

## Clientes

Endpoint:

`GET /api/v1/clientes/`

Búsqueda:

- parámetro `search`;
- campos: `nombres`, `apellidos`, `empresa`, `celular`.

Filtros exactos:

- `activo=true|false`;
- `tipo_cliente=<id positivo>`.

Orden estable: `id` ascendente.

El aislamiento previo se conserva:

- vendedor: sólo clientes propios;
- staff/superusuario: todos los clientes.

## Productos

Endpoint:

`GET /api/v1/catalogo/productos/`

Búsqueda:

- parámetro `search`;
- campos: `sku`, `nombre`.

Filtros exactos:

- `activo=true|false`;
- `categoria=<id positivo>`.

Orden estable: `nombre`, `id`.

El catálogo continúa siendo universal para vendedores autenticados y sus mutaciones continúan
requiriendo administración comercial.

## Validación

Los filtros booleanos o identificadores con formato inválido responden `400`. La búsqueda no
relaja permisos ni permite obtener recursos fuera del queryset autorizado.

## OpenAPI

Los parámetros y el envelope paginado forman parte de `docs/openapi.yaml`. FE03 debe regenerar
sus tipos desde ese contrato y no duplicar DTOs manualmente.

## Evidencia de cierre

- Rama: `feat/fe03-contrato-listados`.
- Commit funcional validado: `5ea36baa17f46c94597820572c180ee38d596e3a`.
- GitHub Actions: run `36086389321`.
- Resultado: **9/9 jobs verdes**.
- Suite PostgreSQL: `162 passed`.
- Concurrencia PostgreSQL: `12 passed, 150 deselected`.
- Ruff: correcto; `184 files already formatted`.
- Django check: correcto.
- Migraciones desde PostgreSQL: correcto.
- OpenAPI: validado y sin drift.
- Privilegios runtime: correcto.
- Worker smoke e integración real F08: correctos.

Con esta evidencia, el contrato de listado, búsqueda, filtros y paginación requerido por FE03 queda
cerrado y listo para ser consumido desde el snapshot OpenAPI del frontend.
