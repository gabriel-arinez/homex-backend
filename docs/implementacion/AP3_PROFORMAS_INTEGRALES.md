# AP3 — Proformas integrales

## Punto de partida

AP6 ya aportaba unidades comerciales, precios editables, descuentos por línea, estados,
protección de totales en PostgreSQL y fichas `datos_tecnicos` JSONB. La API, sin embargo, exigía
crear primero una cabecera y persistir después cada línea y especificación.

## Contrato implementado

- `POST /api/v1/proformas/integral/` crea cabecera, cliente nuevo opcional, líneas,
  especificaciones y estado en una sola transacción.
- `PUT /api/v1/proformas/{id}/integral/` sincroniza de forma atómica una proforma editable,
  conserva los identificadores enviados y elimina únicamente las líneas omitidas.
- `emitir=false` conserva `BORRADOR`; `emitir=true` exige cliente y líneas y termina en
  `EN_REVISION`.
- `clave_idempotencia` e `idempotencia_hash` protegen el primer guardado frente a reintentos y
  doble envío. Un replay idéntico devuelve la misma proforma; reutilizar la clave con otro payload
  produce `409`.
- `TIPO_CLIENTE` se publica como catálogo auxiliar para el cliente provisional del editor.

La numeración continúa usando `seq_proformas_numero`, pero sólo se consume cuando comienza una
persistencia explícita. Abrir, navegar o abandonar el editor no llama a PostgreSQL.

## Integridad

El caso de uso bloquea la proforma con `SELECT FOR UPDATE` durante una sincronización y reutiliza
los servicios AP6 para validar edición, duplicados de catálogo, modo de cálculo, promociones y
JSONB. Los triggers siguen calculando líneas y totales y congelando snapshots. La creación de un
cliente nuevo pertenece a la misma transacción: cualquier error revierte cliente, proforma,
detalles y especificaciones.

Se añadió la migración `proformas.0011_ap3_idempotencia_guardado_integral`. No modifica históricos
ni reescribe migraciones publicadas.

## Verificación

- Suite PostgreSQL completa: 220 pruebas verdes.
- Concurrencia PostgreSQL: 13 pruebas verdes, incluida doble persistencia simultánea con una UUID.
- Pruebas AP3 focales: creación, emisión, rollback, replay idempotente, preservación de IDs,
  JSONB abierto y aislamiento entre vendedores.
- Ruff, formato, `makemigrations --check`, OpenAPI y migración desde base vacía forman parte de los
  gates de cierre.

## Fuera de alcance

AP3 no cambia aprobación, pedidos, inventario, NLP, entrenamiento, documentos ni despliegue.

## Auditoría correctiva H01–H05

- La FK de cliente se valida nuevamente en servicios, también para la API heredada,
  contra la cartera visible del vendedor; administración conserva su alcance.
- Toda actualización integral requiere `revision_esperada` (SHA-256 del agregado).
  El servidor compara la huella de cabecera, líneas y fichas bajo bloqueo
  `SELECT FOR UPDATE`. Los cambios intermedios del editor o HITL producen
  `409` y rollback, sin aplicar sustituciones de líneas desactualizadas.
- `EN_REVISION` y `ENVIADA` no pueden perder sus líneas ni su total positivo.
  También se controla la eliminación directa de la última línea y la ausencia
  de fichas obligatorias.
- El modo histórico `TOTAL_NEGOCIADO` se conserva al sincronizar una línea
  existente, sin convertir ni recalcular su importe negociado. Las líneas nuevas
  continúan utilizando `PRECIO_UNITARIO`.
- La omisión de `especificacion` en un detalle preserva la ficha; enviar
  `especificacion: null` significa eliminación explícita (sujeta al estado).
- La migración `0011` no cambia y no se añade una migración nueva: el token
  se deriva de datos persistidos, incluidos cambios hechos por NLP/HITL.

La respuesta `Proforma` expone `revision` (solo lectura). El PUT integral
requiere `revision_esperada`; una versión omitida se rechaza con 400 y una
desactualizada con 409. Antes de reintentar debe recuperarse la proforma actual.
Los conflictos no autorizan borrar trabajo local automáticamente.

Pruebas de regresión: `tests/api/test_ap3_auditoria_regresiones.py` y
`tests/api/test_ap3_proformas_integrales.py` cubren aislamiento de clientes,
integridad de emisión, actualización HITL concurrente, omisión de fichas,
históricos y clientes empresariales.
