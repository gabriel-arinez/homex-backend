# F10 — Despliegue y recuperación

## Estado y alcance

**IMPLEMENTACIÓN BACKEND COMPLETA; CIERRE PRODUCTIVO CONDICIONADO A D07.**

- rama: `feat/f10-deploy-recuperacion`;
- base backend: `9ce723048d98a3925be45d9c359a25e6be7b19f3`;
- contrato deploy comprobado: `fb9c321324cfc621ac07cc42fdeb1e3257a968ab` (`main`, D05 y D06 cerradas);
- release candidata que consume deploy: backend `9ce723048d98a3925be45d9c359a25e6be7b19f3`;
- ningún ensayo de esta fase modifica `homex-prod`.

F10 mantiene las fronteras del plan maestro. El backend aporta health/readiness, configuración
segura, migraciones, contrato de storage, media keys, audio temporal y recuperación del outbox.
`homex-deploy` sigue siendo dueño de imágenes, Compose, mounts, Nginx, migración controlada,
backup/restore, observabilidad, secretos, manifiesto y evidencia operacional.

## Liveness y readiness

`GET /api/v1/health/` permanece como liveness del proceso y no consulta dependencias. El nuevo
`GET /api/v1/ready/` comprueba:

- `SELECT 1` sobre PostgreSQL;
- existencia y permisos de lectura/escritura/traversal del directorio de media cuando se usa
  filesystem;
- acceso de lectura al storage mediante una operación `HEAD` sin crear objetos cuando se usa S3.

El endpoint devuelve `200` sólo si ambas dependencias están disponibles. En caso contrario devuelve
`503` con `ok/error`; no entrega excepciones, DSN, paths ni secretos. Sólo admite `GET` y no ejecuta
operaciones comerciales. Redis no forma parte del readiness HTTP: la API puede seguir recibiendo y
persistiendo capturas cuando Redis cae, pues PostgreSQL/outbox conserva el trabajo pendiente. La
salud de Redis y workers corresponde a la orquestación D06.

## Separación de media y audio

En settings productivos ahora `HOMEX_AUDIO_TEMP_ROOT` es obligatorio y absoluto. Para filesystem,
Django rechaza al arrancar cualquier configuración donde media y audio sean el mismo directorio o
uno esté contenido dentro del otro. Esto hace verificable la exclusión del audio en backups y evita
que un mount incorrecto convierta temporales ASR en media comercial.

La media comercial conserva el contrato existente:

- keys relativas, nunca paths del host ni URLs completas en PostgreSQL;
- prefijo `productos/` para imagen principal y variantes;
- prefijo `proformas/` para adjuntos y variantes;
- filesystem persistente como release inicial;
- S3/R2 sigue disponible sin cambiar modelos, API ni frontend.

## Recuperación e integridad

D05 ya ejecuta un restore destructivo únicamente en un namespace aislado. Su evidencia fija que:

1. detiene writers y respalda PostgreSQL más media coherente;
2. valida checksums, dump e inventario antes de destruir la base objetivo;
3. restaura DB y media conjuntamente;
4. aplica migraciones y privilegios runtime;
5. contrasta las referencias PostgreSQL con archivos en ambas direcciones;
6. no restaura audio temporal, Redis, modelos ASR ni secretos;
7. rechaza una copia inválida antes de modificar la base activa.

F10 no duplica esa implementación. `scripts/verificar_contrato_deploy_f10.py` lee exactamente el
commit deploy aprobado, exige esos controles, valida que el backend fijado por su manifiesto sea
ancestro de esta rama y registra `d07_pending=true`.

## Reinicios, outbox e idempotencia

No se cambia el modelo asíncrono cerrado en F08:

- PostgreSQL conserva captura, intento y outbox en una transacción;
- Redis sólo transporta identificadores;
- un fallo de publicación deja el outbox pendiente;
- reconciliación recupera trabajos publicados que no cerraron;
- la clave idempotente impide duplicar una captura HTTP;
- redelivery no reescribe intentos terminales ni evidencia IA.

La suite F08.1/F08.2/F08.4 sigue ejecutándose en la regresión completa. D06 añade la prueba real de
caída/recuperación de Redis y dos recepciones concurrentes con una captura, un intento y un outbox.

## Gate de runtime

`scripts/verificar_runtime_f10.py` se ejecuta con settings productivos y PostgreSQL aislado. Exige:

- cero migraciones pendientes;
- media y audio en árboles separados;
- escritura, lectura y eliminación de una sonda bajo `productos/`;
- readiness HTTP `200` con PostgreSQL y media disponibles.

El job `f10-deploy-runtime` crea PostgreSQL 17.6 vacío, aplica todas las migraciones, ejecuta el gate
de compatibilidad D05/D06, prepara roots descartables, ejecuta el smoke productivo y repite
`migrate` para comprobar idempotencia. El checkout deploy está inmovilizado por SHA.

## Evidencia local

Entorno aislado: contenedor `homex-f10-postgres-test`, puerto loopback `55432`; ningún servicio
`homex-prod-*` fue detenido, reiniciado ni escrito.

| Verificación | Resultado |
| --- | --- |
| pruebas específicas health/settings F10 | `20 passed` |
| suite PostgreSQL completa | `188 passed` |
| migración desde PostgreSQL vacío | OK |
| segunda ejecución de `migrate` | `No migrations to apply` |
| runtime productivo | `f10-runtime-ok migrations=ok postgresql=ok media=ok audio_separado=true` |
| contrato D05/D06 | `f10-deploy-contract-ok ... d07_pending=true` |

Antes del cierre de la rama se ejecutan además Ruff, format, Django check, `makemigrations --check`,
OpenAPI sin drift, concurrencia PostgreSQL y `git diff --check`.

## Compatibilidad y limitaciones

D05 y D06 están cerradas y verifican restore, logs seguros, métricas, límites y fallos controlados.
La copia externa cifrada continúa pendiente en infraestructura; la copia local ensayada no debe
considerarse protección suficiente frente a pérdida total del host.

D07 es una dependencia formal según `homex-deploy/docs/PLAN_MAESTRO.md`: debe fijar este commit de
backend en un manifiesto inmutable, construir las imágenes finales, migrar el servidor objetivo,
probar worker/media/backup/smoke y documentar rollback y acceso privado. Por ello esta rama puede
integrarse como implementación F10 del backend, pero **F10 no puede declararse cerrada para
producción hasta que D07 aporte evidencia verde y la copia externa cifrada tenga una decisión
operacional explícita**.

No se adelantó F11, no se añadieron tablas, migraciones, endpoints comerciales ni cambios de
permisos de negocio.

## Evidencia remota de la implementación

- implementación: `273157121d3bd4fec7c9ee1edbd588319fea2cdb`;
- corrección del contexto CI: `bb4b8905358b01cf81c1c9ca10ce55d5af4ee3e4`;
- GitHub Actions push `37890348983`: **success**, 11/11 jobs;
- GitHub Actions PR `37890352298`: **success**, 11/11 jobs;
- `tests-postgresql`: 188 pruebas verdes;
- `concurrency-postgresql`: 12 pruebas verdes;
- `f08-real-integration`, `f09-frontend-integration` y `f10-deploy-runtime`: verdes;
- lint, format, Django check, migraciones, privilegios PostgreSQL y OpenAPI: verdes.

PR: `https://github.com/gabriel-arinez/homex-backend/pull/7`.
