# Matriz de permisos — HOMEX Backend F07

## Alcance

Este documento describe los permisos reales implementados en el backend al
cierre de F07.

No documenta funcionalidades futuras de F08 ni permisos inexistentes.

Los perfiles reconocidos actualmente son:

- `VENDEDOR`: usuario perteneciente al grupo Django `VENDEDOR`;
- `ADMIN`: usuario con `is_staff=True` o `is_superuser=True`;
- `SIN_ROL`: usuario autenticado que no pertenece al grupo `VENDEDOR` y tampoco
  es staff/superusuario.

La autorización base está centralizada en:

`apps/core/permissions.py`

mediante:

- `EsVendedor`;
- `EsAdministradorComercial`.

## Principios de autorización

### Vendedor

El vendedor:

- puede operar su propio flujo comercial;
- no puede consultar objetos comerciales pertenecientes a otro vendedor;
- no puede ejecutar acciones sobre objetos ajenos;
- puede consultar el catálogo universal;
- no puede administrar productos, fichas ni promociones.

Cuando intenta acceder directamente por ID a un objeto comercial perteneciente
a otro vendedor, el objeto queda fuera del queryset autorizado y la API
responde `404`.

Esto evita revelar la existencia de recursos ajenos.

### Administrador

Los usuarios `is_staff` o `is_superuser`:

- cumplen también `EsVendedor`;
- pueden consultar objetos de todos los vendedores;
- administran el catálogo;
- mantienen las acciones comerciales actualmente habilitadas por los mismos
  endpoints.

### Usuario sin rol

Un usuario autenticado sin rol comercial recibe `403` en los endpoints
protegidos por `EsVendedor` o `EsAdministradorComercial`.

### Identidad y capacidades para clientes API

El endpoint autenticado:

`GET /api/v1/auth/me/`

expone la identidad del usuario actual y una lista de capacidades derivada de
las mismas reglas de autorización del backend.

Capacidades públicas actuales:

- `comercial.operar`: el usuario cumple `EsVendedor`;
- `comercial.administrar`: el usuario cumple `EsAdministradorComercial`.

Correspondencia actual:

- `VENDEDOR` → `comercial.operar`;
- `ADMIN` → `comercial.operar` + `comercial.administrar`;
- `SIN_ROL` → lista de capacidades vacía.

El endpoint requiere autenticación, pero no exige rol comercial. Esto permite
que clientes como el frontend conozcan de forma explícita que un usuario
autenticado no posee capacidades comerciales.

Las capacidades son una proyección de la autorización real del backend. No
sustituyen las permission classes, los querysets autorizados ni las validaciones
de servicios.

## Matriz

| Recurso | VENDEDOR: listar/ver | VENDEDOR: crear/modificar | VENDEDOR: acciones | ADMIN | SIN_ROL |
|---|---|---|---|---|---|
| Clientes | Sólo propios | Crear y modificar propios | DELETE sólo dentro de su queryset autorizado, según API actual | Acceso global | 403 |
| Productos | Sí, catálogo universal | No | No | CRUD administrativo | 403 |
| Ficha silla | No | No | No | CRUD administrativo | 403 |
| Ficha piso | No | No | No | CRUD administrativo | 403 |
| Promociones/descuentos | No | No | No | CRUD administrativo | 403 |
| Proformas | Sólo propias | Crear y modificar propias | Enviar, aprobar y agregar detalle sólo sobre propias | Acceso global | 403 |
| Detalle de proforma | Acceso únicamente mediante acciones habilitadas y queryset propio | PATCH sólo sobre detalle de proforma propia | Crear especificación sólo sobre detalle propio | Acceso global según endpoints habilitados | 403 |
| Pedidos | Sólo propios | API de lectura; no edición directa | Cambiar estado, cancelar, emitir recibo y emitir nota sólo sobre pedido propio | Acceso global | 403 |
| Órdenes de trabajo | Sólo propias | No | No | Acceso global | 403 |
| Recibos | Sólo propios | No edición comercial directa | Anular recibo propio | Acceso global | 403 |
| Notas de entrega | Sólo propias | No | No | Acceso global | 403 |
| Movimientos de stock | Historial global de sólo lectura | No | No; los efectos siguen en servicios/triggers PostgreSQL | Historial global de sólo lectura | 403 |
| Documentos | Descarga de documentos dentro de su alcance comercial | No | Descarga contextual; sin CRUD documental | Acceso global | 403 |

## Detalle por recurso

### Clientes

Endpoint:

`/api/v1/clientes/`

`ClienteViewSet.get_queryset()` aplica:

- staff/superuser → todos;
- vendedor → `created_by=request.user`.

Un vendedor ajeno no puede obtener directamente un cliente perteneciente a
otro vendedor.

### Catálogo

Endpoints:

- `/api/v1/catalogo/productos/`;
- `/api/v1/catalogo/sillas/`;
- `/api/v1/catalogo/pisos/`;
- `/api/v1/catalogo/descuentos/`.

Productos:

- `list` y `retrieve` requieren `EsVendedor`;
- crear, modificar o eliminar requiere `EsAdministradorComercial`.

Fichas de silla, piso y descuentos:

- requieren `EsAdministradorComercial` para todas las acciones expuestas.

El catálogo es universal para consulta; no pertenece individualmente a cada
vendedor.

### Proformas

Endpoint:

`/api/v1/proformas/`

El vendedor sólo obtiene proformas donde:

`vendedor = request.user`

Acciones protegidas por el mismo queryset:

- recuperar;
- modificar;
- enviar;
- aprobar;
- agregar detalle.

DELETE de proforma está explícitamente deshabilitado y responde `405`.

### Detalles de proforma

Endpoint:

`/api/v1/proformas-detalle/`

El queryset de un vendedor está restringido mediante:

`proforma__vendedor=request.user`

Las acciones expuestas actualmente son:

- `PATCH` del detalle;
- creación de especificación.

Un detalle perteneciente a otro vendedor queda fuera del queryset y responde
`404`.

### Pedidos

Endpoint:

`/api/v1/pedidos/`

El vendedor sólo obtiene pedidos cuya proforma pertenece al propio vendedor.

La API no permite edición directa del modelo.

Acciones comerciales:

- `cambiar-estado`;
- `cancelar`;
- `emitir_recibo`;
- `emitir_nota_entrega`.

`cambiar-estado` expone `EN_PRODUCCION`, `LISTO_ENTREGA` y `ENTREGADO`. La validez de la transición concreta sigue siendo autoridad de PostgreSQL. `CANCELADO` sólo se procesa mediante `cancelar`.

Todas obtienen primero el pedido mediante el queryset autorizado.

Por tanto un vendedor no puede ejecutar estas acciones sobre un pedido ajeno.

### Órdenes de trabajo

Endpoint:

`/api/v1/ordenes-trabajo/`

Es de sólo lectura.

El vendedor sólo puede consultar órdenes asociadas a pedidos cuya proforma le
pertenece.

Staff/superuser tiene consulta global.

### Recibos

Endpoint:

`/api/v1/recibos/`

Es de sólo lectura excepto por la acción:

`anular`

El vendedor sólo puede ver o anular recibos asociados a pedidos propios.

La edición comercial directa no está expuesta.

### Notas de entrega

Endpoint:

`/api/v1/notas-entrega/`

Es de sólo lectura.

El vendedor sólo consulta notas cuyo pedido pertenece a su flujo comercial.

La emisión se realiza mediante la acción del pedido y no mediante creación
directa en este ViewSet.

### Movimientos de stock

El contrato complementario para FE05 publica:

`GET /api/v1/movimientos-stock/`

y:

`GET /api/v1/movimientos-stock/{id}/`

La API es estrictamente de sólo lectura. `POST`, `PATCH`, `PUT` y
`DELETE` no están habilitados. Los movimientos continúan produciéndose
exclusivamente mediante casos de uso comerciales y reglas PostgreSQL,
incluyendo `CARGA_INICIAL`, `VENTA` y `REVERSA_VENTA`.

La consulta admite filtros por producto, pedido, tipo de movimiento y rango de
fechas, además de búsqueda por SKU, nombre u observación. El historial es
operativo/global para usuarios con `comercial.operar`; no representa
propiedad del vendedor ni reserva por proforma.

### Documentos

No existe un CRUD ni una tabla adicional de documentos emitidos. Los
renderizadores de F07.4 se exponen como descargas HTML derivadas de datos
persistidos:

- `GET /api/v1/proformas/{id}/documento/`;
- `GET /api/v1/ordenes-trabajo/{id}/documento/`;
- `GET /api/v1/recibos/{id}/documento/`;
- `GET /api/v1/notas-entrega/{id}/documento/`.

Cada acción usa el queryset autorizado de su recurso. Un vendedor no puede
descargar un documento perteneciente al flujo comercial de otro vendedor;
staff/superuser conserva alcance global.

## PostgreSQL: migrador y runtime

La autorización HTTP/Django es independiente de los privilegios PostgreSQL.

Los roles operativos son:

### Migrador/propietario

Responsable de:

- ejecutar migraciones;
- crear/modificar objetos del esquema;
- funciones;
- triggers;
- índices.

### Runtime

Puede utilizar los objetos existentes mediante:

- `SELECT`;
- `INSERT`;
- `UPDATE`;
- `DELETE`;
- uso de secuencias.

No recibe privilegios para:

- `CREATE TABLE`;
- `ALTER TABLE`;
- `CREATE FUNCTION`;
- creación de triggers;
- ownership del esquema.

El procedimiento está en:

`docs/sql/privilegios_runtime.sql`

La verificación automatizada está en:

`scripts/verificar_privilegios_runtime.py`

## Evidencia automatizada

Cobertura previa:

- `tests/api/test_f072_api.py`
  - cliente sin rol → 403;
  - vendedor ajeno → recurso no visible.

- `tests/api/test_f073_api.py`
  - permisos y aislamiento de órdenes de trabajo;
  - vendedor propietario;
  - vendedor ajeno;
  - usuario sin rol;
  - staff.

- `tests/api/test_f074_api.py`
  - permisos de recibos;
  - anulación;
  - permisos de notas de entrega;
  - aislamiento entre vendedores.

Cobertura F07.6:

- `tests/api/test_f076_permisos.py`
  - catálogo visible para vendedor;
  - escritura de catálogo sólo administrativa;
  - fichas especializadas administrativas;
  - aislamiento de proformas;
  - aislamiento de detalles;
  - envío de proforma ajena rechazado;
  - modificación de detalle ajeno rechazada;
  - aislamiento de pedidos;
  - cancelación de pedido ajeno rechazada;
  - emisión de recibo sobre pedido ajeno rechazada;
  - emisión de nota sobre pedido ajeno rechazada.

Resultado específico de la matriz de permisos F07.6:

`3 passed`

Cobertura adicional de transiciones:

- `tests/api/test_f076_transiciones_pedido.py`
  - recorrido normal hasta `LISTO_ENTREGA`;
  - salto de estado no configurado rechazado por PostgreSQL;
  - pedido ajeno no visible;
  - `CANCELADO` no admitido por la acción genérica.

Resultado conjunto de permisos y transiciones:

`7 passed`

## Regla para nuevas APIs

Toda nueva API comercial debe:

1. usar una permission class explícita;
2. aplicar aislamiento a nivel de queryset cuando corresponda;
3. proteger también acciones custom;
4. tener prueba de usuario autorizado;
5. tener prueba de usuario sin rol;
6. tener prueba de acceso directo a objeto ajeno cuando exista propiedad por
   vendedor;
7. actualizar esta matriz.

No se considera suficiente ocultar una operación en frontend.


### Aprobación de proformas

La aprobación de una proforma no introduce una capacidad adicional. El vendedor que cumple
`EsVendedor` puede enviar y aprobar sus propias proformas; los usuarios administrativos conservan
el alcance global definido por los querysets. El backend sigue validando propiedad, estado y reglas
comerciales en cada operación.

Por tanto, `comercial.operar` cubre crear, editar en BORRADOR, enviar y aprobar una proforma
propia. `comercial.administrar` no es requisito para aprobar.
