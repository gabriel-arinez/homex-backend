# F08.3 — HITL y confirmación

## Estado

**Implementación local cerrada.**

- Rama: `re-refactor`.
- Base: `e229f28ff5de25791d0ba4b0188193919bb9abd9`.
- F08.2 verificada antes de iniciar mediante GitHub Actions run `35891109351`: 8/8 jobs verdes.
- El commit y CI remoto de F08.3 quedan pendientes de publicación por el responsable del repositorio.

## Objetivo

Convertir una propuesta IA persistida en una corrección humana final, una evaluación operativa versionada y una línea comercial válida, sin permitir que el navegador sustituya la evidencia original ni aprobar la proforma.

## Contrato API

### Consultar revisión

```http
GET /api/v1/capturas/{id}/
```

Devuelve exclusivamente evidencia almacenada en el servidor:

- captura, proforma y vínculo comercial;
- texto transcrito;
- último intento `FINALIZADO`;
- proyección `item_ia` inmutable;
- indicador derivado `incorporada`.

El queryset limita cada vendedor a sus propias capturas. Staff y superuser conservan acceso global.

### Confirmar captura

```http
POST /api/v1/capturas/{id}/confirmar/
```

El cuerpo contiene:

- `intento_id` e `item_ia_id` como identidades que el servidor vuelve a comprobar;
- `item_corregido`, sin copia de la propuesta IA;
- `linea_comercial`, con tipo, unidad y semántica de precio.

Los serializadores son estrictos. Un campo como `original_ia`, métricas, versiones, latencias o precios totales calculados por el navegador se rechaza. El servidor recupera el original desde `ItemIA` y su `IntentoCaptura.resultado_raw` asociado.

La primera confirmación responde `201`. Una segunda confirmación se rechaza con `409 captura_ya_confirmada`; no crea historia de revisiones ni otra línea.

## Transacción y bloqueos

`confirmar_captura()` ejecuta una sola transacción corta y bloquea en este orden:

1. proforma;
2. captura;
3. item IA/intento.

Después valida:

- propietario o privilegio administrativo;
- procesamiento `COMPLETADA` y último intento `FINALIZADO`;
- correspondencia exacta captura → intento → item IA;
- ausencia de confirmación anterior;
- proforma no aprobada;
- catálogos activos y JSON comercial V1.

En la misma transacción crea:

1. `DetalleProforma`;
2. `ItemHumano` final;
3. `EvaluacionNLP` versionada;
4. `EspecificacionMueble`;
5. vínculo `Captura.proforma_detalle`.

Un error en cualquier escritura revierte todas las anteriores.

## Datos comerciales

F08.3 incorpora únicamente `TIPO_ITEM.MUEBLE_MEDIDA`, coherente con el alcance `RULES_ONLY` de voz v1. La unidad debe ser `PIEZA`.

Se preservan los dos modos de precio:

- `PRECIO_UNITARIO`: exige unitario y rechaza importe negociado;
- `TOTAL_NEGOCIADO`: exige total, rechaza un unitario aportado y calcula el unitario sólo como referencia.

Para tres muebles por Bs 100 se almacena unitario referencial Bs 33,33, pero PostgreSQL conserva `detalle.total = 100,00`. La corrección humana registra ese total autoritativo.

La confirmación mantiene la proforma en su estado actual. No crea `Pedido`, no ejecuta aprobación y no descuenta stock.

## JSON comercial V1

La API valida antes de persistir:

- `espesor`: `{"espesor": "valor con unidad"}`;
- dimensiones: ejes `ancho`, `alto`, `profundidad`, `largo` o `diametro`, con valores textuales que preservan unidad;
- accesorios: array de textos.

También se corrigió la proyección del worker para transformar las colecciones tipadas de `homex-nlp` al JSONB comercial V1. `resultado_raw` continúa reteniendo el contrato NLP completo; la proyección consultable deja de intentar guardar listas donde PostgreSQL exige objetos.

## Evaluación

F08.3 consume la API pública:

```python
from homex_nlp.field_comparison import compare_fields
```

El original comparable procede de `ItemIA`, nunca del request. Valores ausentes o colecciones vacías no se convierten en aciertos evaluables.

Se persisten:

- `version_metrica = field-comparison-v1`;
- campos evaluables, corregidos, agregados y eliminados;
- `precision_campo`;
- `precision_item`;
- revisor y fecha de revisión.

Sin campos originales evaluables, ambas precisiones quedan `NULL`.

Una edición comercial posterior modifica el detalle mediante su flujo normal y no reescribe la corrección final ni la evaluación utilizada como evidencia.

## Integridad PostgreSQL

La migración `capturas.0006_hitl_inmutabilidad_f083` crea:

- `trg_proteger_item_humano_final`;
- `trg_proteger_evaluacion_nlp_final`.

Ambos rechazan `UPDATE` y `DELETE`. Las relaciones uno a uno existentes garantizan una corrección por item IA y una evaluación por corrección.

Se verificó:

- migración desde PostgreSQL vacío;
- rollback de `0006` a `0005`;
- ausencia de triggers después del rollback;
- reaplicación de `0006`;
- presencia física de ambos triggers;
- segunda ejecución completa de `migrate` como no-op.

## Pruebas específicas

Resultado final:

```text
16 passed
```

Cobertura:

- original IA recuperado del servidor;
- payload IA manipulado rechazado;
- propuesta parcial corregible;
- precisión `NULL` sin denominador;
- confirmación atómica;
- rollback ante fallo intermedio;
- doble confirmación rechazada sin duplicados;
- dos confirmaciones concurrentes producen una sola línea;
- resultado NLP atrasado rechazado;
- corrección y evaluación físicamente inmutables;
- edición comercial posterior no reescribe evidencia;
- `TOTAL_NEGOCIADO` conserva Bs 100 exactos para cantidad 3;
- `TOTAL_NEGOCIADO` rechaza unitario aportado y MUEBLE_MEDIDA rechaza unidad distinta de PIEZA;
- confirmación no aprueba la proforma;
- aislamiento por vendedor;
- proyección NLP real compatible con JSON V1.

## Gates locales finales

- suite PostgreSQL completa: `149 passed in 45.62s`;
- concurrencia: `12 passed, 137 deselected in 6.18s`;
- Ruff: correcto;
- formato: `173 files already formatted`;
- Django check: correcto;
- `makemigrations --check --dry-run`: sin cambios;
- OpenAPI regenerado, validado, sin advertencias y sin drift;
- `uv sync --locked --extra dev --extra worker`: correcto;
- `git diff --check`: limpio;
- skips/xfails añadidos: ninguno.

## Archivos principales

- `apps/capturas/hitl.py`;
- `apps/capturas/api/serializers.py`;
- `apps/capturas/api/views.py`;
- `apps/capturas/pipeline.py`;
- `apps/capturas/migrations/0006_hitl_inmutabilidad_f083.py`;
- `tests/api/test_f083_hitl_api.py`;
- `tests/integration/test_f083_hitl.py`;
- `docs/openapi.yaml`.

## Riesgo pendiente de la fase siguiente

F08.4 debe ejecutar el recorrido integrado con PostgreSQL real, Redis real, worker real y el wheel fijado. F08.3 prueba la transacción, concurrencia, API y persistencia HITL; no sustituye ese gate integral de resiliencia.
