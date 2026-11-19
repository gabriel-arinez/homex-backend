# Consolidación de roles y contenido por rol (ADMIN, ENCARGADO_TIENDA, JEFE_TALLER)

Objetivo: unificar `VENDEDOR` y `ENCARGADO_TIENDA` en el rol único `ENCARGADO_TIENDA` (manteniendo compatibilidad progresiva con el grupo legado `VENDEDOR` y migrando asignaciones existentes), definir los tres roles definitivos (`ADMIN`, `ENCARGADO_TIENDA`, `JEFE_TALLER`), exponer referencias de cliente y título en órdenes de trabajo sin abrir módulos comerciales al taller, y adaptar rutas, navegación, órdenes de trabajo, catálogo y dashboards (`ResumenView`) al alcance de cada rol.
Rama: `feat/consolidacion-roles-contenido`.

## Specs

### S1 — Consolidación de roles y migración progresiva
- Tres roles definitivos:
  - `ADMIN` (`is_staff` / `is_superuser`): capacidades `comercial.operar`, `comercial.administrar`, `taller.operar`, `catalogo.crear_producto`.
  - `ENCARGADO_TIENDA` (grupo `ENCARGADO_TIENDA`, con soporte de transición para `VENDEDOR`): capacidades `comercial.operar`, `catalogo.crear_producto`.
  - `JEFE_TALLER` (grupo `JEFE_TALLER`): capacidad `taller.operar`.
- Migración de datos segura en `accounts` (`0002_consolidar_encargado_tienda`) que asegura la existencia de `ENCARGADO_TIENDA` y `JEFE_TALLER` y asigna `ENCARGADO_TIENDA` a toda cuenta perteneciente a `VENDEDOR` sin pérdida de datos.

### S2 — Referencias comerciales controladas en Órdenes de Trabajo
- `OrdenTrabajoSerializer` expone `proforma_titulo` y `cliente_resumen` (`id`, `nombre`, `empresa`, `celular`) derivados de la proforma asociada al pedido, permitiendo a `JEFE_TALLER` identificar cliente y referencia en listado y detalle de OT sin consultar `/api/v1/proformas/` ni abrir permisos comerciales.

### S3 — Rutas iniciales, navegación, brechas por rol y dashboards diferenciados
- Resolución de ruta inicial, guardas y etiqueta de rol según capacidades (`ADMIN`, `ENCARGADO_TIENDA`, `JEFE_TALLER`, `SIN_ROL`).
- Corrección de las 5 brechas en frontend:
  1. Aterrizaje post-login y redirección de `/` o `/resumen` según capacidades, y acción de retorno en `/forbidden`.
  2. En OT (`OrdenesTrabajoListView`, `OrdenTrabajoDetailView`, `WorkOrderActionsMenu`): no invocar `/api/v1/proformas/` sin `comercial.operar`, usar `cliente_resumen` y `proforma_titulo` nativos de la OT, y mostrar enlaces a `/pedidos/:id` sólo con `comercial.operar`.
  3. En `ProductoDetailView`: mostrar botón "Ver movimientos" sólo con `comercial.operar`.
  4. En OT: identificar ítems de fabricación por `tipo_item_info.codigo === 'MUEBLE_MEDIDA'`, mostrando ficha técnica completa cuando `especificacion` está presente (`JEFE_TALLER` / `ADMIN`) o aviso de ficha técnica reservada a taller para `ENCARGADO_TIENDA`.
  5. En `ResumenView` y `AppSidebar`: habilitar `/resumen` para `comercial.operar` y `taller.operar`, presentando visión global para `ADMIN`, visión comercial de tienda para `ENCARGADO_TIENDA` y visión operativa de taller (métricas de órdenes de trabajo por estado y tipo de trabajo) para `JEFE_TALLER`.

## Tasks

- [x] T1 — S1, S2 — inline — Consolidar permisos en `ENCARGADO_TIENDA`, crear migración `accounts.0002_consolidar_encargado_tienda`, exponer `cliente_resumen` y `proforma_titulo` en `OrdenTrabajoSerializer`, regenerar `docs/openapi.yaml` y actualizar pruebas backend.
- [x] T2 — S3 — inline — Sincronizar contrato OpenAPI en frontend, adaptar sesión/routing/sidebar/forbidden, corregir brechas en OT y catálogo, e implementar dashboard por rol en `ResumenView` con pruebas unitarias y E2E.
