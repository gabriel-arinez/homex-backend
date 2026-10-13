# AP1 — Auditoría automática de dependencias Python

**Inicio:** 12/10/2026. **Repositorio:** `homex-backend`.

## Motivo y criterio

El proyecto tiene `pyproject.toml` y `uv.lock`; lint/Ruff, suites y las
comprobaciones previas no informaban vulnerabilidades conocidas de las
dependencias Python. No se debe presentar la existencia del lockfile
como escaneo de seguridad.

Se agrega el job GitHub Actions `dependency-audit`, utilizando
**`uv audit --locked`** mediante `setup-uv@v6` con `uv==0.12.9`.
Este subcomando incorpora consulta a una base de avisos de vulnerabilidades
y estados adversos a través de la red. Por defecto cubre los extras y los
grupos del proyecto, incluidos sus paquetes transitivos, basándose en el
`uv.lock` vigente; no actualiza el lockfile ni instala un segundo gestor
de dependencias. La base OSV se consulta externamente y es gratuita.

La auditoría falla si hay hallazgos o si no puede completar la consulta.
**No usar `continue-on-error`, `|| true` ni exclusiones globales.** Si el
job informa vulnerabilidades, documentar paquete, aviso, versión y solución;
actualizar versiones/lock solo tras verificar compatibilidad de Python,
ASR/NLP y pruebas de integración reales. Excepciones requieren aprobación,
alcance mínimo, justificativo y fecha de reevaluación. Nunca ocultar rojo.

## Validación de AP1

- Gate local reproducible: `uv audit --locked`.
- CI: job `dependency-audit` verde **además** de todos los anteriores.
- Mantener `uv sync --locked`, Ruff, PostgreSQL real (backend) y tests existentes.
- No se modifica configuración de producción, `homex-prod`, release D07/RC2
  ni contratos comerciales.

## Responsabilidad posterior

En AP2–AP5 cualquier cambio en `pyproject.toml` o `uv.lock` debe volver a
ejecutar este gate y conservar evidencia. La auditoría identifica avisos
**conocidos**; no sustituye análisis de permisos, pruebas de seguridad ni
gestión de actualizaciones.
