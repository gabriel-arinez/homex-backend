# F08.4 — Resiliencia y cierre F08

## Estado

**F08.4 cerrada, verificada y fusionada a `main`.**

- Base de la fase: `0170fcb00c96ba2adfa5ca51a1818eaa8c17638c`.
- Implementación F08.4: `301446be656715e7480928dcd2f2d686d65989a9`.
- Merge final a `main`: `fcec7e6a438dca35f78bc3c8f0010fba9e54cf36`.
- GitHub Actions sobre F08.4: CI #50, 9/9 jobs verdes.
- GitHub Actions sobre el merge final a `main`: CI #53, 9/9 jobs verdes.

La fase no añade reglas comerciales ni modifica el esquema: cierra la matriz de fallos de F08 y
agrega un gate con infraestructura real.

## Integración real obligatoria

El job `f08-real-integration` ejecuta, sin modo eager:

1. PostgreSQL 17 vacío y Redis 7.4 reales;
2. instalación bloqueada con los extras `dev` y `worker`;
3. todas las migraciones;
4. un proceso Celery real con pool `solo`;
5. espera activa hasta recibir `pong` del worker;
6. `scripts/verificar_integracion_f084.py`.

El verificador crea una proforma y una captura de texto en PostgreSQL. El trigger genera el
outbox; el publicador entrega sólo las identidades a Redis; el worker consume la tarea, ejecuta
`homex-nlp` y persiste el resultado. El gate exige finalmente:

- outbox publicado exactamente una vez;
- intento `FINALIZADO` y captura `COMPLETADA`;
- propuesta `ItemIA` persistida;
- `schema_version == "1.0"` y motor `RULES_ONLY`;
- paquete instalado `homex-nlp==0.1.0`;
- wheel versionado con SHA-256
  `cfacc3a987f6158f43934cb64304fa50ea3e577cfa576f3db1e6d2a9576d19e6`;
- respuesta real de Redis a `PING`.

`config.settings.integration` desactiva explícitamente `CELERY_TASK_ALWAYS_EAGER`; por tanto, el
gate no puede pasar ejecutando la tarea dentro del proceso publicador.

## Matriz de resiliencia

| Frontera | Garantía y evidencia |
|---|---|
| Base de datos | PostgreSQL es la autoridad de captura, intento, evidencia y outbox. Suite completa, migración desde vacío, triggers e integración real. |
| Redis | Una caída conserva el outbox pendiente; publicación sólo marca éxito tras aceptación. F08.2 prueba indisponibilidad y F08.4 usa Redis real. |
| Archivo temporal | Original privado, copia ASR descartable, permisos restrictivos, eliminación tras transcripción persistida y TTL seguro. Casos F08.2. |
| ASR | Éxito, error, crash antes de persistir y recuperación conservando el original. Casos F08.2 con la API pública `AsrService`. |
| NLP | Wheel y hash fijados; modo `RULES_ONLY`; resultado v1 persistido. Contrato unitario e integración real F08.4. |
| Worker | `acks_late`, rechazo al perder worker, prefetch 1, redelivery idempotente y proceso Celery real en el nuevo gate. |
| Reintento | Reconciliación devuelve trabajo estancado a pendiente; un reintento NLP reutiliza la transcripción sin audio. Casos F08.2. |
| Contrato incompatible | Versiones/schema/modo desconocidos se rechazan. El pipeline cierra el intento con `NLP_CONTRACT_INCOMPATIBLE`, mensaje seguro y sin evidencia parcial. |

La matriz combina pruebas deterministas para las ventanas de fallo difíciles de provocar de forma
estable con un recorrido real del camino feliz. Los dobles no sustituyen el gate real y el gate
real no sustituye las pruebas de crash, expiración y redelivery.

## Error contractual seguro

`procesar_intento()` distingue ahora `ErrorContratoNLP` de un fallo inesperado. Una
incompatibilidad de paquete, schema o modo se registra como:

```text
NLP_CONTRACT_INCOMPATIBLE
El contrato del motor NLP no es compatible con el backend.
```

No se persiste el payload incompatible, no se filtra su detalle y no se crea `ItemIA`. La captura
y el intento terminan en `ERROR`, permitiendo diagnóstico operativo sin confundirlo con un fallo
genérico del pipeline.

## Evidencia local

- integración real aislada: `f084-real-ok`;
- worker real: tarea recibida y finalizada como `FINALIZADO`;
- suite PostgreSQL: `155 passed`;
- concurrencia: `12 passed, 143 deselected`;
- Ruff: correcto;
- formato Ruff: `177 files already formatted`;
- Django check: correcto;
- `makemigrations --check --dry-run`: sin cambios;
- OpenAPI: validado y sin drift;
- PostgreSQL vacío: migraciones completas correctas;
- segunda ejecución de migraciones: no-op;
- runtime worker y wheel fijado: correctos.

## Archivos principales

- `apps/capturas/pipeline.py`;
- `config/settings/integration.py`;
- `scripts/verificar_integracion_f084.py`;
- `tests/integration/test_f084_resiliencia.py`;
- `.github/workflows/ci.yml`;
- `docs/implementacion/F08_4_RESILIENCIA_CIERRE.md`.

## Cierre remoto

El workflow pasó de ocho a nueve jobs al incorporar `f08-real-integration`.

La implementación F08.4 publicada en
`301446be656715e7480928dcd2f2d686d65989a9` ejecutó CI #50 con **9/9 jobs verdes**,
incluido el recorrido real PostgreSQL + Redis + Celery + wheel NLP.

Después, la rama `re-refactor` fue fusionada a `main` en
`fcec7e6a438dca35f78bc3c8f0010fba9e54cf36`. El CI #53 volvió a ejecutar el workflow
completo sobre `main` y terminó también con **9/9 jobs verdes**.

Con esa evidencia remota, **F08 queda formalmente cerrada**.
