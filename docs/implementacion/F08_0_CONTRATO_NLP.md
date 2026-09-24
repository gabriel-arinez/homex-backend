# F08.0 — Contrato backend ↔ homex-nlp

## Estado

**Fase cerrada.**

F08.0 integra `homex-nlp` mediante una frontera explícita y pura, sin adelantar persistencia, endpoints de captura, Redis, worker, audio, ASR ni HITL.

La integración inicial opera exclusivamente en `RULES_ONLY`.

## Base de trabajo

- Rama: `re-refactor`
- Base de F08.0:
  `48278a7e0556dd9ea2cd01d9b6c164118b2391a6`
- Commit inicial F08.0:
  `4d281ffb9a3873721c89b15adcad6647e673fa8b`
- Commit correctivo funcional final:
  `357c2b265d4d63fa0f9eb74a46bc0291efa5536d`
- `homex-nlp` canónico:
  `b5fe2921320c9031f6d44dc5c91a18411daa393e`

## Objetivo

Integrar el paquete NLP fijado por versión, validar su contrato público y transformar su resultado al dominio español del backend sin permitir que el paquete se convierta en autoridad comercial.

F08.0 no persiste todavía resultados NLP.

## Distribución fijada

- paquete: `homex-nlp==0.1.0`
- wheel: `vendor/homex_nlp-0.1.0-py3-none-any.whl`
- SHA-256:
  `cfacc3a987f6158f43934cb64304fa50ea3e577cfa576f3db1e6d2a9576d19e6`
- Python soportado: 3.11
- `schema_version` soportada: `1.0`
- modo operativo: `RULES_ONLY`

`pyproject.toml` fija la versión exacta y `[tool.uv.sources]` utiliza una ruta relativa al wheel versionado.

`uv.lock` conserva la fuente local, el hash exacto del wheel y las dependencias transitivas.

El backend no depende de una rama flotante ni de un checkout hermano del repositorio NLP.

## Frontera pública

La integración vive en:

`apps/capturas/nlp/`

`AdaptadorNLP` consume únicamente las interfaces públicas autorizadas:

- `homex_nlp`
- `homex_nlp.contracts`
- `homex_nlp.engine`

La suite protege esta frontera mediante análisis AST para impedir dependencias accidentales contra `homex_nlp.rules`, entrenamiento, recursos privados u otros internals.

## Solicitud externa

Se conservan los nombres públicos del paquete:

- `request_id`
- `text`
- `currency_context`
- `domain_profile_version`

No se renombran campos públicos de `homex_nlp`.

El mapeo al dominio español ocurre únicamente después de validar el contrato externo.

## Versiones y compatibilidad

El adapter valida explícitamente:

- `homex_nlp.__version__ == "0.1.0"`
- `schema_version == "1.0"`
- `engine.mode == "RULES_ONLY"`

Fallos explícitos:

- versión de paquete desconocida → `PaqueteNLPNoSoportado`
- schema desconocido → `ContratoNLPNoSoportado`
- modo distinto de `RULES_ONLY` → `ModoNLPNoSoportado`
- campos adicionales o estructura inválida → `pydantic.ValidationError`

No existe fallback silencioso, coerción automática a v1 ni aceptación automática de ampliaciones futuras.

## RULES_ONLY sin bypass

La versión inicial de F08.0 exponía en `transformar()` el parámetro `exigir_rules_only`, que técnicamente permitía desactivar la comprobación.

El commit correctivo `357c2b265d4d63fa0f9eb74a46bc0291efa5536d` eliminó ese bypass.

En el contrato final de F08.0:

- `transformar()` no acepta un parámetro para omitir la comprobación;
- cualquier `engine.mode != "RULES_ONLY"` se rechaza;
- `HYBRID` no puede habilitarse accidentalmente;
- habilitar otro modo requerirá una ampliación deliberada del contrato y sus pruebas.

## Mapeo interno

`ResultadoNLP` y `PropuestaMueble` son la proyección interna en español.

Se conservan:

- propuesta;
- candidatos;
- spans/offsets;
- decisiones;
- referencias de componentes;
- warnings;
- información del motor;
- errores;
- latencia;
- payload contractual completo.

`resultado_original` se crea mediante `deepcopy`, por lo que posteriores mutaciones del payload de entrada no alteran la evidencia retenida por el adapter.

Los dataclasses son `frozen` en el nivel superior. Las estructuras anidadas conservadas como `dict` no se consideran inmutables; la garantía actual es aislamiento por copia profunda.

No se importa ORM desde esta frontera.

## Fixture contractual

El fixture:

`tests/fixtures/nlp/medidas-componentes-v1.json`

coincide con el fixture normativo v1 de `homex-nlp` y valida transformación sin pérdida de evidencia.

## Archivos de F08.0

Introducidos o modificados:

- `apps/capturas/nlp/__init__.py`
- `apps/capturas/nlp/adapter.py`
- `tests/fixtures/nlp/medidas-componentes-v1.json`
- `tests/unit/test_f080_contrato_nlp.py`
- `tests/unit/test_f080_wheel.py`
- `vendor/homex_nlp-0.1.0-py3-none-any.whl`
- `vendor/README.md`
- `pyproject.toml`
- `uv.lock`
- `docs/implementacion/F08_0_CONTRATO_NLP.md`

## Migraciones

**Ninguna.**

F08.0 no añade ni modifica modelos Django.

Persistencia de capturas, intentos, outbox, items IA e idempotencia pertenece a F08.1.

## Pruebas específicas F08.0

La suite final verifica:

- importación sin inicializar Django;
- importación sin escrituras;
- versión exacta del paquete;
- extracción real con `RulesEngine`;
- operación `RULES_ONLY`;
- rechazo de versión de paquete desconocida;
- rechazo de `schema_version` desconocida antes de deserializar;
- rechazo de campos adicionales;
- transformación del fixture v1 sin pérdida de evidencia;
- aislamiento por copia profunda;
- rechazo de `HYBRID`;
- ausencia del antiguo parámetro de bypass;
- dependencia exclusiva de APIs públicas de `homex-nlp`;
- hash exacto del wheel fijado.

Resultado específico:

```text
11 passed in 0.32s
```

## Gates locales finales

### Dependencias

`uv sync --locked --extra dev`: OK.

### Ruff

```text
All checks passed!
```

### Formato

```text
148 files already formatted
```

### Django

```text
System check identified no issues (0 silenced).
```

### Migraciones pendientes

```text
No changes detected
```

### Suite PostgreSQL completa

```text
106 passed in 37.72s
```

### Concurrencia

```text
9 passed, 97 deselected in 4.71s
```

### OpenAPI

El schema fue regenerado con `--validate` y comparado contra `docs/openapi.yaml`.

Resultado: validación correcta y cero drift.

### Diff

`git diff --check`: limpio.

## Skips y xfails

No se añadieron `skip` ni `xfail` para hacer pasar los requisitos de F08.0.

No existen pruebas obligatorias omitidas en la suite final.

## CI remoto

### Commit inicial

GitHub Actions run #27 (`35823758962`) validó el commit inicial `4d281ffb9a3873721c89b15adcad6647e673fa8b` con 7/7 jobs verdes.

### Commit correctivo final

GitHub Actions run #28:

`35825340243`

Commit:

`357c2b265d4d63fa0f9eb74a46bc0291efa5536d`

Resultado: **success**.

Jobs verdes:

- `lint`
- `django-check`
- `postgres-migrations`
- `tests-postgresql`
- `concurrency-postgresql`
- `postgres-privileges`
- `openapi-drift`

## Riesgos y bloqueos

No queda un riesgo crítico conocido dentro del alcance de F08.0.

Quedan deliberadamente fuera de esta fase:

- persistencia de capturas;
- idempotencia HTTP;
- outbox;
- Redis;
- Celery/worker;
- audio efímero;
- ASR;
- HITL;
- NER experimental.

Esos elementos se incorporan en las fases F08.1–F08.4 según el Plan Maestro.

## Resultado final

F08.0 queda cerrada con el paquete `homex-nlp 0.1.0`, contrato v1 y modo `RULES_ONLY` fijados y validados.

La siguiente fase habilitada es **F08.1 — DB-04: capturas, intentos, outbox e idempotencia**.
