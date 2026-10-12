# Trazabilidad interrepositorio — D07 RC2 (corte 2026-10-11)

> **Alcance:** registro de la implementación fusionada, evidencias existentes y trabajo operacional diferido. No es certificado de promoción, prueba nueva ni autorización de despliegue. Ante cifras o condiciones históricas contradictorias, tienen prioridad el manifiesto de release actual, las evidencias específicas y el registro de pendientes.

## Identidad reproducible de la candidata

| Componente | Revisión incluida en la candidata |
| --- | --- |
| Deploy D07 | PR [#8](https://github.com/gabriel-arinez/homex-deploy/pull/8), merge `1870f1646f977045ce4ffa7762d9f8dd759fcd2c` |
| Backend F10 + protección RC2 | `3e05362ac49c170963a8dc1d32b4d612e491112f` |
| Frontend FE09 | `479a092462b36a90006eb1c52f9570ea63084bab` |
| NLP F10 | `79efeaf6a8ca738eb3abce414850f973b1962fd8` |
| Release | `0.7.0-d07-rc2`, **`candidate`** |

Imágenes inmutables fijadas por el manifiesto deploy:

- Backend (API y worker): `ghcr.io/gabriel-arinez/homex-backend:0.7.0-d07-rc2@sha256:0a9f7f0e7650304808fe8d99227648ef42b34507c11d3ed86adbd8176391166a`.
- Frontend-proxy: `ghcr.io/gabriel-arinez/homex-frontend-proxy:0.7.0-d07-rc2@sha256:023cad7b1d64520e5e3d2d407d27ed6224c88ae1c2f4bcbd0b74c24b0bebe15c`.
- Paquete NLP `homex-nlp==0.1.0`, contrato `schema_version=1.0`, modo `RULES_ONLY`; wheel `homex_nlp-0.1.0-py3-none-any.whl`, SHA-256 `cfacc3a987f6158f43934cb64304fa50ea3e577cfa576f3db1e6d2a9576d19e6`.
- Modelo local `Systran/faster-whisper-small@536b0662742c02347bc0e980a01041f333bce120` y checksum declarado en `homex-deploy/releases/manifest.yaml`.

## Lo implementado por repositorio

**Backend:** Django/DRF como autoridad comercial, PostgreSQL y Outbox; F10 agrega `/api/v1/ready/`, validación de media persistente y separación obligatoria del directorio de audio temporal. RC2 incorpora `capturas.0008_propiedad_ejecucion`, `ejecucion_token` UUID y bloqueo por intento en PostgreSQL para excluir trabajo concurrente y proteger la reconciliación de Outbox. API y worker utilizan la misma revisión. Referencias: [F10 backend](https://github.com/gabriel-arinez/homex-backend/blob/main/docs/implementacion/F10_DESPLIEGUE_RECUPERACION.md), [merge RC2 backend](https://github.com/gabriel-arinez/homex-backend/commit/3e05362ac49c170963a8dc1d32b4d612e491112f).

**Frontend:** FE09 produce build estático reproducible y seguro; verifica snapshots OpenAPI, errores/red/timeout, navegación y pantallas de escritorio/tablet/móvil por Playwright. El navegador envía audios al backend, no contiene secretos de almacenamiento y no decide reglas de negocio. Referencia: [FE09](https://github.com/gabriel-arinez/homex-frontend/blob/main/docs/implementacion/FE09_RELEASE.md).

**NLP:** F10 comprueba distribución wheel/sdist reproducible, contrato 1.0, import ASR perezoso y modelo local sin descarga implícita, privacidad y limpieza de temporales, concurrencia controlada y perfil agregado. El paquete no gestiona Django, Outbox ni backups. Referencia: [F10 NLP](https://github.com/gabriel-arinez/homex-nlp/blob/main/docs/F10_DESPLIEGUE_RECUPERACION.md).

**Deploy:** D07 integra imágenes OCI por digest, preflight antes de operaciones sobre PostgreSQL/Redis, migración one-shot con parada de escritores, `grant-runtime`, health/readiness/monitor, Cloudflare Zero Trust/HTTPS privado y recuperación D05. Restic + Cloudflare R2 **solo respalda unidades cifradas** (PostgreSQL + media + manifiesto): la media comercial en producción sigue en filesystem persistente local. Referencias: [D07 release](https://github.com/gabriel-arinez/homex-deploy/blob/main/docs/implementacion/D07_RELEASE.md), [runbook](https://github.com/gabriel-arinez/homex-deploy/blob/main/docs/RECOVERY_RUNBOOK.md).

## Evidencia verificada — distinguir sus límites

- Backend F10: documentación de fase registra 188 pruebas PostgreSQL, 12 de concurrencia y 11/11 jobs CI en las ejecuciones iniciales; no debe confundirse con pruebas nuevas de RC2.
- NLP F10: 51 pruebas generales, 7 específicas, wheel/sdist reproducibles y perfil agregado; el perfil controlado de CI **no** mide hardware definitivo.
- Frontend FE09: 68 pruebas E2E, 23 de accesibilidad y 10 navegadores/dispositivos simulados en el cierre inicial, además de la integración real en CI; los tests responsivos **no** equivalen a dispositivos físicos autorizados por Zero Trust.
- Deploy: en D07 hubo escenarios aislados reales de captura/proforma, Celery, reconciliación/idempotencia, migración D04→D07 y restauración de PostgreSQL/media; hubo también mocks para fallo de `deploy.sh`. El ensayo aislado D04→D07→D04 con fallo a mitad de migración y retorno **de todos los servicios** sigue incompleto.
- Recuperación D04 de octubre 11: backup `homex-20261009T051913Z` con SHA-256 verificado, manifiesto D04 coincidente (`0.4.0-d04-rc1`), PostgreSQL 17.6 saludable, 34 tablas públicas, siete migraciones `capturas`, `runtime-privileges-ok` y `db-media-integrity-ok` con media 0/0. No se obtuvo la línea final `homex-restore-ok` por interrupción de la terminal y no se demostró el arranque de todo el stack D04. Nunca promover esta evidencia a un PASS de rollback integral.
- Backups con SHA-256 conformes: `homex-20261009T051913Z` (D04) y `homex-20261011T041518Z` / `homex-20261011T042511Z` (D07 RC1); **no** son tres backups D04. El restore externo Restic se ensayó aisladamente, pero no existe aún política aprobada y automatizada de retención R2.
- Según la última observación del ensayo, los siete contenedores `homex-prod` seguían en D04. El merge a `main` **no cambió** el despliegue físico.

## Pendientes para una sesión posterior

1. Ensayo operacional aislado: arranque completo D04, fallo inducido después de iniciar migración D07, rollback desde unidad D04 con manifiesto/imágenes compatibles y verificación de API, worker, jobs, Redis, PostgreSQL y archivos comerciales referenciados. Conservar evidencias y evitar `down -v` en namespaces existentes.
2. Restitución de media enlazada a datos comerciales y comportamiento de Outbox ante fallos reales de broker/proceso y entregas duplicadas.
3. ASR con modelo real, recursos y latencias en hardware objetivo; flujo voz→NLP→HITL completo y privacidad/limpieza.
4. PC/tablet/móvil físicos autorizados, denegación a dispositivos no autorizados, túnel/CA/HTTPS y no exposición de servicios internos.
5. Política de retención Restic/R2, alertas, credenciales de recuperación y ensayo periódico de pérdida de host; **no ejecutar `restic forget --prune`** sin aprobación.
6. Ventana/autorización explícita de producción, respaldo anterior, despliegue, smoke, observabilidad y plan de retroceso; promoción a `released` solo después de gates completos.

**Decisión del 11-10-2026:** por instrucción expresa del responsable, se fusionó la **implementación** D07 en `main` con pendientes registrados, pero no se declaró cerrada su validación productiva. `homex-prod` debe permanecer en D04 hasta nueva autorización. El detalle operativo y criterio de reanudación está en [pendientes D07](https://github.com/gabriel-arinez/homex-deploy/blob/main/docs/implementacion/D07_CIERRE_PENDIENTES_20261011.md).
