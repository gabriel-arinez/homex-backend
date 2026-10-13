# AP1 — Auditoría de estándares de ingeniería y seguridad interrepositorio

**Corte:** 12/10/2026. **Estado:** ejecución AP1 en PR; **no cerrar** sin CI
remoto de los commits definitivos y aceptación externa. No incluye AP2 ni AP3–AP5.
Este registro compara el contrato
`HOMEX_TRASPASO_APARTADOS_1_A_5_20261012.md` (apartado 1)
con la documentación y el código publicados en `main`, no con una suposición
sobre el SQL histórico.

## Fuentes y baselines remotos contrastados

| Repositorio | main al iniciar AP1 | CI base exitoso | Cobertura visible en CI |
| --- | --- | --- | --- |
| frontend | `70883b0603c0820c878dad4449c5ef2bbcc20e7b` | [38192027974](https://github.com/gabriel-arinez/homex-frontend/actions/runs/38192027974) | 12 jobs: instalación, tipos, lint, formato, unitarias/componentes, build, E2E, accesibilidad, contrato, npm audit, release e integración real |
| backend | `a715876cc9b3c4a85aa397e736e60b18b90085fa` | [38188201596](https://github.com/gabriel-arinez/homex-backend/actions/runs/38188201596) | 11 jobs: Ruff, Django, migraciones PostgreSQL, tests PG, concurrencia, OpenAPI, privilegios PG, worker e integraciones |
| NLP | `0390a461551f105d138ef4e73aae57e7e16c7360` | [38188210073](https://github.com/gabriel-arinez/homex-nlp/actions/runs/38188210073) | package: Ruff, schemas, corpus, pytest, wheel/consumidor y F10 |
| deploy | `1782e900f40f61dd532a8b636790dcd61b043ac5` | [38197598668](https://github.com/gabriel-arinez/homex-deploy/actions/runs/38197598668) | 13 jobs: Compose, YAML, release, ASR, builds, integración, smoke, recuperación, resiliencia y secretos |

Fuentes de arquitectura: los cuatro planes maestros; backend
`docs/arquitectura.md`, `docs/migraciones.md`, `docs/permisos.md`,
`docs/openapi.yaml`; frontend `docs/design-system.md`; NLP
`docs/F09_INTEGRACION_SISTEMA.md`; deploy `docs/ARQUITECTURA_DEPLOY.md`.
También se contrasta `homex_bd_final_v3.sql` con las migraciones Django
actuales: el SQL describe diseño histórico, **no** es la fuente única operativa
ni se ejecuta en esta auditoría de seguridad.

## Matriz decisión → control existente → brecha → cambio

| Exigencia AP1 | Presente en main | Brecha encontrada / intervención |
| --- | --- | --- |
| Ramas, PR, revisión, CI antes de merge | CI en los cuatro; planes de ramas | En los cuatro `main`: `protected=false`, sin checks requeridos. No se simula protección por archivo. Proponer configuración externa y mantener PRs sin merge hasta verde/revisión. |
| Formato, lint, lockfiles | frontend: Prettier/Oxlint/ESLint, npm ci; backend/NLP: uv.lock y Ruff; deploy: yamllint/validadores | Conservar herramientas; no introducir formatters incompatibles. |
| Contratos entre repos | OpenAPI Django + snapshot frontend + generación tipos; JSON schemas/contratos NLP; manifest SHA/digests deploy | Con cada modificación de contrato, sincronizar repos de consumo y ejecutar gates, no usar el frontend como autoridad comercial. El checkout fijo F10 sirve como *baseline de release*, no como verificación automática contra todo cambio futuro de `main`. |
| PostgreSQL/migraciones/roles | CI real PG, paridad/privilegios, tests concurrencia | AP1 no duplica QA0; profundización de matriz de riesgos/transacciones corresponde a AP2. |
| IDOR/permisos | Querysets propios y pruebas vendedor/admin en clientes, proformas, pedidos, documentos y capturas | Ruta de adjuntos de proforma consultaba objeto global antes del check de propietario y distinguía `403` de `404`. Corregido en backend PR AP1, con tests negativos PG. |
| Secretos/dependencias | deploy: Gitleaks; frontend: `npm audit --audit-level=high`; locks en Python | Falta Gitleaks en frontend, backend y NLP: jobs propuestos en PRs específicos. Para dependencias Python, evaluar avisos existentes y costo/ruido antes de imponer auditor adicional; no declarar cubierta esa detección. |
| Audio/media/privacy | validación de tipos/tamaño de imagen, límite de audio, almacenamiento efímero y limpieza; QA0 prueba recuperación y no persistencia de audio | Mantener revisión negativa en AP2 y en cada ampliación de endpoints de AP3–AP5; sin reejecutar restore destructivo QA0 para AP1. |
| Liberación segura | manifiesto de release/D07 y flujos de deploy separados | D07 RC2 candidato; **prohibida promoción a producción sin autorización separada**; `homex-prod` no participa. |

## Cambios acotados AP1

1. Backend `apps/proformas/api/views.py`: archivos de proforma consultan
   `get_queryset()` autorizado, sin búsqueda global previa.
2. Backend `tests/api/test_f077_media_api.py`: POST/GET/DELETE ajenos → 404,
   inexistente → 404, propietario 201, administrador 200.
3. Backend `docs/permisos.md`: comportamiento IDOR documentado.
4. Backend CI: `permissions: contents: read` para el token;
   secrets/Gitleaks como control transversal de bajo costo.
5. Frontend y NLP: jobs Gitleaks en CI, sin sustituir pruebas anteriores.
6. Deploy: sin modificación de workflow durante AP1; reutiliza Gitleaks y
   la evidencia QA0 preexistente.

## Protección de main pendiente de configuración externa

Al inicio de AP1 GitHub devolvió `protected: false` para los cuatro `main`.
La conexión disponible permite consultar este estado, pero no ofrece operación
para cambiar branch protection/rulesets; **no afirmar que se activó**.

Propuesta mínima para todos: bloquear eliminación/force push, requerir PR y
al menos una revisión **independiente**, requerir que los checks de PR
específicos de cada repo terminen verdes, descartar aprobaciones obsoletas,
resolver conversaciones de revisión y restringir bypass a un proceso formal
de emergencia documentado. Seleccionar los nombres reales desde el PR verde
antes de guardar reglas, sin romper el flujo de un único propietario.

Checks por repo (valores tomados del CI y sujetos a ajuste tras los PRs):

- Frontend: `install`, `type-check`, `lint`, `format`,
  `unit-component`, `build`, `e2e`, `a11y`, `contract-drift`,
  `dependency-audit`, `release`, `integration-real`, `secrets`.
- Backend: `lint`, `worker-smoke`, `django-check`,
  `postgres-migrations`, `tests-postgresql`, `concurrency-postgresql`,
  `openapi-drift`, `postgres-privileges`, `f08-real-integration`,
  `f09-frontend-integration`, `f10-deploy-runtime`, `secrets`.
- NLP: `package`, `secrets`.
- Deploy: `compose-config`, `yaml`, `release-contract`,
  `asr-contract`, `build`, `integration`, `staging-integration`,
  `media-local-integration`, `private-release-candidate`,
  `recovery`, `resilience-observability`, `d07-release-contract`,
  `secrets`.

Esta lista indica los *jobs actuales*, no una afirmación de protección
activada; revisar cambios de configuración GitHub antes de exigirlos.

## Criterios de salida y límites de evidencia

- Confirmar HEAD de los PRs, logs y conclusión de cada job remoto.
- Conservar evidencias **negativas** (IDOR sobre PostgreSQL real).
- Si un detector de secretos alerta, analizar, revocar credenciales reales
  y corregir. No añadir exclusiones globales para obtener CI verde.
- No confundir CI remoto con pruebas locales en el equipo del usuario: aquí
  se usó un conector GitHub, **sin acceso al directorio Git local**.
  Por tanto `pwd`/`git status` del equipo del usuario y validación
  local independiente quedan pendientes de ejecución en dicho equipo.
- El análisis exhaustivo de valor/lagunas de pruebas pertenece a AP2,
  **no ejecutado** durante AP1.
- No modificar `homex-prod`, el candidato RC2 ni el apartado 6.

## Comandos de reproducción local (en clon local aislado)

```bash
cd ~/HOMEX/homex-backend
git status --short
git branch --show-current
git rev-parse HEAD
git remote -v
uv sync --locked --extra dev
uv run ruff check .
uv run ruff format --check .
# Requiere PostgreSQL configurado y settings de test en un entorno aislado:
uv run pytest -ra tests/api/test_f077_media_api.py
```

Las operaciones no destructivas anteriores no reemplazan CI, ni prueban
migraciones/rollbacks en producción.
