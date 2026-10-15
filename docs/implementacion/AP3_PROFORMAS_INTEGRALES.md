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
