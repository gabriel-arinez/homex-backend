# AP4 — Consolidación del módulo de clientes

## Diagnóstico y alcance

La matriz previa se conserva en `~/Descargas/HOMEX_AP4_MATRIZ_BRECHAS_20261015.md`. El backend ya publicaba CRUD, búsqueda, filtros y aislamiento por `created_by`, y PostgreSQL ya protegía la identidad mínima mediante `fn_validar_cliente`. AP4 completó las brechas sin cambiar reglas de proformas, pedidos, inventario o despliegue.

## Implementación

- `ClienteSerializer` publica `tipo_cliente_info` con código y etiqueta del catálogo.
- La validación compartida exige nombres y apellidos tanto para persona como para contacto de empresa; empresa exige razón social y persona rechaza razón social.
- El tipo se selecciona únicamente desde `TIPO_CLIENTE` activo y queda inmutable tras el alta.
- La misma validación se usa en el CRUD y en `cliente_nuevo` del guardado integral AP3.
- `DELETE /api/v1/clientes/{id}/` desactiva bajo bloqueo de fila; no elimina datos ni relaciones.
- AP3 rechaza un `cliente` existente fuera de la cartera del vendedor aunque se manipule el ID. Staff conserva su alcance global contractual.
- Las actualizaciones se serializan con `SELECT FOR UPDATE`.

La migración nueva `clientes.0002_ap4_integridad_identidad` añade la defensa física que impide cambiar `tipo_cliente_id`. No reescribe migraciones publicadas. La función histórica `fn_validar_cliente` continúa siendo autoridad física para la forma PERSONA/EMPRESA.

## Historia comercial

El cambio de datos actuales no modifica snapshots. La prueba AP4 emite una proforma, actualiza el cliente y comprueba que `cliente_nombre_snapshot`, `cliente_empresa_snapshot` y `cliente_celular_snapshot` conservan los valores emitidos. Un cliente inactivo sigue siendo consultable en su cartera y deja de ofrecerse en selectores de nuevas operaciones.

## Contrato y permisos

OpenAPI incorpora `tipo_cliente_info` como campo de solo lectura. No se añadieron permisos: `comercial.operar` y el queryset por vendedor siguen vigentes. Se corrigió el punto de entrada integral para usar el contexto autenticado del serializer.

## Evidencia local

- Ruff y formato: correctos.
- Django check: correcto.
- `makemigrations --check --dry-run`: sin cambios.
- PostgreSQL: 229 pruebas correctas.
- Concurrencia: 13 pruebas correctas.
- AP4 específica: 9 pruebas correctas.
- Migración desde PostgreSQL vacío: correcta; segunda ejecución sin operaciones.
- OpenAPI regenerado, validado y sin drift.

No se modificó producción, no se promovió D07 RC2 y no se adelantó AP5.
