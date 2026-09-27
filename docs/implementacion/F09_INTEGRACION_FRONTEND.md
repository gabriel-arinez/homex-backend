# F09 — Integración con frontend

## Estado

**Implementación y validación local completadas. Cierre remoto pendiente de publicar la rama.**

- Rama: `feat/f09-integracion-frontend`.
- Base backend: `96e5afd0c3bd0e5c75ddd5469313ac2e79cdad7e`.
- Frontend integrado: `57c32d3aa2c2e46fbcc7136f6a90995b67c664ea`, merge de FE08 a `main`.
- Commit funcional/documental FE08: `3661d43e7374131f3ed34a0b375102860c406d6a`.
- Evidencia frontend previa: GitHub Actions `36327844337`, 11/11 jobs verdes.

F09 no añade endpoints, estados, tablas ni reglas comerciales. Cierra desde backend la integración que FE08 ya demostró desde Vue y convierte ese recorrido en un gate obligatorio para cada revisión backend.

## Autoridad contractual

El job `f09-frontend-integration` descarga un commit completo y fusionado del frontend, no una rama mutable. Antes de ejecutar el navegador:

1. carga `docs/openapi.yaml` del backend y `contracts/backend-openapi.yaml` del frontend;
2. compara semánticamente los documentos YAML completos, por lo que ignora sólo diferencias de formato;
3. comprueba que `contracts/backend-ref.txt` contiene un SHA completo;
4. exige que ese SHA sea ancestro del backend bajo prueba.

Una diferencia de endpoint, método, esquema, estado, permiso o payload rompe el gate. La comparación no exige que ambos archivos tengan la misma indentación.

Resultado local:

```text
f09-contract-consumer-ok backend_ref=96e5afd0c3bd0e5c75ddd5469313ac2e79cdad7e
```

No se creó una API paralela para Vue. OpenAPI continúa siendo la única autoridad del intercambio HTTP.

## Entorno real compartido

El nuevo job levanta:

- PostgreSQL 17 desde una base vacía;
- Redis 7.4;
- Django con `config.settings.integration`;
- Celery worker real, sin eager mode;
- Celery beat como publicador/reconciliador outbox;
- el wheel fijado `homex-nlp==0.1.0`;
- `faster-whisper-base` en CPU/int8;
- frontend Vue construido para producción;
- Chromium y Playwright.

El modelo ASR se descarga de forma explícita antes de arrancar el worker y se cachea fuera del runtime. El audio español se genera durante el job, se utiliza a través de la UI de grabación y no se versiona ni se conserva como artefacto.

## Recorrido comercial desde Vue

El Playwright fusionado en frontend ejecuta contra esta revisión backend:

```text
login JWT
→ cliente y producto reales
→ proforma manual
→ línea de catálogo
→ ENVIADA
→ APROBADA
→ pedido CONFIRMADO
→ movimiento VENTA
→ orden de trabajo
→ recibo EMITIDO
→ cancelación bloqueada por cobro
→ recibo ANULADO
→ EN_PRODUCCION
→ LISTO_ENTREGA
→ nota de entrega
```

Un segundo pedido demuestra la cancelación válida sin recibo emitido y la `REVERSA_VENTA`. El navegador no calcula stock, totales, saldo, permisos ni transiciones; comprueba las respuestas y estados publicados por Django.

Después de Playwright, `verificar_integracion_frontend_f09.py` consulta PostgreSQL y exige que la evidencia corresponda a las proformas concretas creadas por el navegador:

- proforma comercial `APROBADA`;
- pedido en `LISTO_ENTREGA`;
- segundo pedido `CANCELADO`;
- OT automática;
- `VENTA` y `REVERSA_VENTA` del SKU utilizado;
- recibo `ANULADO`;
- Nota de Entrega emitida.

Resultado local:

```text
2 passed
f09-frontend-backend-ok pedido=1 captura=1 postgresql=ok audio-temporal=eliminado
```

## Captura, ASR, NLP y HITL desde Vue

El segundo escenario entra por `/capturas/nueva`, opera la grabación mediante `MediaRecorder` y deja que el servicio real del frontend construya `multipart/form-data`. El flujo completo es:

```text
Vue
→ POST multipart HTTP 202
→ Django/PostgreSQL outbox
→ Redis
→ Celery
→ faster-whisper
→ homex-nlp RULES_ONLY
→ propuesta REQUIRES_REVIEW
→ formulario HITL
→ confirmación
→ detalle y EspecificacionMueble
```

La verificación posterior exige:

- captura `COMPLETADA`;
- intento `FINALIZADO`;
- transcripción ASR y versión del modelo;
- `resultado_raw` original;
- `ItemIA` e `ItemHumano`;
- vínculo captura → detalle comercial;
- `EspecificacionMueble` asociada al mismo detalle;
- proforma todavía `BORRADOR`;
- directorio de audio temporal vacío.

Redis se usa sólo como transporte. Toda la evidencia y autoridad comercial se comprueban en PostgreSQL.

## Documentos y media

El gate también ejerce las APIs públicas que complementan el recorrido visual:

- descarga de proforma;
- descarga de Orden de Trabajo;
- descarga de recibo;
- descarga de Nota de Entrega;
- carga, lectura y eliminación de imagen principal de producto;
- generación de variantes WebP 320/640 y publicación de dimensiones;
- carga, listado y eliminación de adjunto de una proforma `BORRADOR`.

Los cuatro documentos deben ser HTML descargable, conservar su nombre contractual e incluir la numeración persistida. La imagen y el adjunto pasan por los servicios reales de almacenamiento; el gate no escribe campos de media directamente.

Resultado local:

```text
f09-public-surfaces-ok documentos=4 producto-media=ok proforma-media=ok
```

La configuración productiva R2, sus credenciales y la infraestructura de despliegue siguen fuera de F09. Las pruebas F07.7 existentes continúan validando la configuración R2 y la limpieza ante fallos.

## Correspondencia FE03–FE08

| Fase frontend | Contrato/backend verificado |
|---|---|
| FE03 | listados paginados, filtros, búsqueda, autoridad de precio/stock/disponibilidad e imágenes públicas |
| FE04 | editor mixto, líneas de catálogo y mueble, estados, totales protegidos, adjuntos y conflictos |
| FE05 | pedidos, OT, movimientos, recibos, notas y documentos descargables |
| FE06 | captura multipart, idempotencia, worker, estados NLP, propuesta y confirmación HITL |
| FE07 | conteos paginados respetando queryset y permisos backend |
| FE08 | recorrido comercial y NLP reales, contrato fijado, consola nominal y evidencia PostgreSQL |

La revisión no encontró una divergencia real que justificara modificar serializers, vistas, rutas o OpenAPI.

## Resiliencia del gate

- frontend y backend están fijados por SHA;
- `setup-uv` ejecuta con caché automática desactivada para evitar bloqueos observados en FE08;
- el modelo ASR tiene una caché explícita independiente;
- API y worker deben responder antes de iniciar Playwright;
- el frontend se construye dentro del job;
- las trazas Playwright y logs de API/worker/beat se publican sólo si falla;
- el verificador posterior impide aceptar una UI verde sin efectos persistidos;
- el audio temporal debe desaparecer.

## Evidencia local

- suite PostgreSQL: **175 passed**;
- concurrencia PostgreSQL: **12 passed, 163 deselected**;
- E2E compartido Vue/backend: **2 passed**;
- verificador PostgreSQL/audio: verde;
- documentos y media por API pública: verde;
- Django check: verde;
- `makemigrations --check --dry-run`: sin cambios;
- OpenAPI generado: válido y sin drift;
- snapshot OpenAPI del frontend: equivalencia semántica completa;
- Ruff: verde;
- Ruff format: verde;
- PostgreSQL vacío: migraciones completas;
- segunda ejecución de migraciones: no-op;
- workflow YAML: válido;
- `git diff --check`: limpio.

## Archivos principales

- `.github/workflows/ci.yml`;
- `scripts/preparar_integracion_frontend_f09.py`;
- `scripts/preparar_modelo_asr_f09.py`;
- `scripts/verificar_contrato_frontend_f09.py`;
- `scripts/verificar_integracion_frontend_f09.py`;
- `scripts/verificar_superficies_frontend_f09.py`;
- `docs/implementacion/F09_INTEGRACION_FRONTEND.md`.

## Condición de cierre remoto

El workflow backend pasa de nueve a diez jobs. F09 quedará formalmente cerrada cuando la rama se publique y GitHub Actions confirme los **10/10 jobs verdes**, incluido `f09-frontend-integration`. Hasta entonces, la implementación y la evidencia local están completas, pero no se afirma un cierre remoto inexistente.

F10 — despliegue y recuperación no forma parte de estos cambios.
