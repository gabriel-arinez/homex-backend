# AP4 — Matriz de brechas y cierre de auditoría

Documento versionado para reproducir el alcance de la consolidación de clientes.
Reemplaza la referencia exclusiva a la matriz local en `~/Descargas`.
Las cifras de pruebas se acreditan mediante los CI de los PR correctivos.

| ID | Brecha detectada | Salvaguarda implementada | Prueba / evidencia |
| --- | --- | --- | --- |
| H01 | Razón social invisible tras cambiar EMPRESA por PERSONA | El componente compartido limpia `empresa` al seleccionar PERSONA | Vitest de transición de tipo, AP3 y AP4 comparten componente |
| H02 | Ficha obsoleta al reutilizar ruta con otro ID | Observador de ruta, limpieza y control de respuestas fuera de orden | Vitest navegación 1→2 |
| H03 | PK ajena e inexistente producían respuestas distintas | Campo de relación visible por vendedor y resolución opaca `404` | API POST integral y API heredada |
| H04 | Cliente inactivo bloqueaba edición histórica | Permitir exclusivamente la FK previamente enlazada; impedir nuevos vínculos | PostgreSQL POST, DELETE y PUT integral |
| H05 | Dos escritores sobrescribían cambios concurrentes | SHA-256 de campos persistidos, `If-Match` y bloqueo de fila, `409` si obsoleto | API dos PATCH y DELETE desactualizado |
| H06 | Filtros no seguían navegación del navegador | Sincronización URL→filtros con guard contra recargas duplicadas | Vitest de navegación entre búsquedas |
| H07 | Cobertura de snapshots afirmada pero incompleta | Emisión real de PERSONA/EMPRESA y comprobación de cuatro snapshots tras edición y baja | PostgreSQL pruebas de regresión |
| H08 | Matriz de brechas existía solo en Descargas | Esta matriz queda integrada con el código y enlazada en la documentación de ambos repositorios | Historia de commits y PR |

## Contrato y compatibilidad

- `GET /api/v1/clientes/{id}/` devuelve `revision` de solo lectura.
- `PUT/PATCH/DELETE /api/v1/clientes/{id}/` requieren la cabecera `If-Match`
  con la revisión observada. La precondición ausente devuelve `400`;
  la desactualizada devuelve `409`. No se descarta automáticamente el formulario.
- Solo el vendedor propietario (o personal con alcance administrativo contractual)
  puede referenciar un cliente. Cliente ajeno y cliente inexistente devuelven
  `404` sin diferenciar existencia.
- Una proforma previa puede conservar su cliente desactivado. Una nueva no puede
  seleccionar clientes inactivos.
- El tipo comercial continúa siendo inmutable en PostgreSQL y la desactivación
  sigue sin eliminar registros.

## Criterio de cierre

Requiere tests PostgreSQL, concurrencia, OpenAPI sin drift, Vitest, Playwright,
integración real y los 13 jobs por repositorio después de merge. La auditoría
no promueve RC2 ni modifica el despliegue productivo.
