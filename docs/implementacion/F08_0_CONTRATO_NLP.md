# F08.0 — Contrato backend ↔ homex-nlp

## Resultado

El backend integra `homex-nlp` mediante una frontera explícita y pura, todavía sin persistencia,
endpoints, Redis, worker ni audio. La integración inicial opera exclusivamente con reglas y no
requiere un modelo NER.

## Distribución fijada

- paquete: `homex-nlp==0.1.0`;
- wheel versionado: `vendor/homex_nlp-0.1.0-py3-none-any.whl`;
- SHA-256: `cfacc3a987f6158f43934cb64304fa50ea3e577cfa576f3db1e6d2a9576d19e6`;
- source portable de uv: ruta relativa declarada en `[tool.uv.sources]`;
- hash y dependencias transitivas bloqueados en `uv.lock`;
- Python soportado: 3.11;
- schema soportado: `1.0`;
- modo operativo: `RULES_ONLY`.

El wheel se conserva en el backend para que CI, una construcción aislada y un despliegue no dependan
de una rama flotante, de un checkout hermano ni de conectividad con un registro privado aún no
definido.

## Adapter

`apps.capturas.nlp.AdaptadorNLP` es el único punto autorizado de consumo. Importa únicamente las
interfaces públicas documentadas:

- `homex_nlp.__version__`;
- `homex_nlp.contracts.ExtractionRequest`;
- `homex_nlp.contracts.ExtractionResult`;
- `homex_nlp.engine.RulesEngine`.

La solicitud utiliza los nombres públicos originales del paquete (`request_id`, `text`,
`currency_context`, `domain_profile_version`). La respuesta se valida primero con el contrato
Pydantic estricto y luego se transforma a `ResultadoNLP`/`PropuestaMueble`, cuyos nombres pertenecen
al dominio español del backend.

`resultado_original` conserva un deep copy completo del JSON contractual. Candidatos, spans,
decisiones, warnings, referencias de componentes, motor y errores no se reconstruyen ni se pierden.
Los DTO son inmutables y no importan ORM.

## Fallos explícitos

- versión de paquete distinta de `0.1.0` → `PaqueteNLPNoSoportado`;
- `schema_version` distinta de `1.0` → `ContratoNLPNoSoportado` antes de mapear;
- motor distinto de `RULES_ONLY` en el flujo operativo → `ModoNLPNoSoportado`;
- campos adicionales o estructura inválida → `pydantic.ValidationError` por `extra=forbid`.

No existe fallback silencioso, coerción a v1 ni aceptación automática de ampliaciones futuras.

## Pruebas F08.0

La suite específica verifica:

- importación sin Django, base de datos ni escrituras;
- versión exacta del paquete y extracción `RULES_ONLY`;
- rechazo de versiones desconocidas de paquete/schema;
- rechazo de campos adicionales;
- transformación del fixture normativo v1 sin pérdida de evidencia;
- aislamiento por copia del payload original;
- rechazo explícito de `HYBRID` y ausencia de dependencia NER.

F08.0 no cambia modelos ni migraciones. La persistencia de capturas, intentos, outbox e idempotencia
corresponde a F08.1.

## Validación local

- `uv sync --locked --extra dev`: OK.
- Ruff y formato: OK.
- Django check: OK.
- `makemigrations --check`: sin cambios.
- pruebas específicas F08.0: 9 passed.
- suite PostgreSQL sin concurrencia: 95 passed.
- suite de concurrencia: 9 passed.
- total del repositorio: 104 pruebas verdes.
- OpenAPI: validado y sin drift.
- `git diff --check`: limpio.
