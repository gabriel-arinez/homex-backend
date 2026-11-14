# Evidence-led final eight-comment review
Target: existing backend feat/real-voice-120-semantic and frontend fix/real-voice-120-f09; NLP remains0.1.24 unless a demonstrated package defect requires change.
Delivery: original PR60/68/43 only, single-PR per existing branch, no merge/deploy/history deletion. Runners: locked Python3.11 pytest/Ruff, ordinary installed NLP wheel, Node24/Vitest/Playwright and exact-head CI. Forecast about650 authored changed lines, no review-chain creation under the explicit existing-branch scope.

## Specs
- S1: "Backend PR #60: investiga las 7 observaciones pendientes de Sourcery. Reproduce cada caso, identifica falsos positivos y corrige únicamente los defectos confirmados."
- S2: "Frontend PR #68: verifica la observación pendiente sobre las observaciones estructuradas. Corrige solo si existe una pérdida real de información."
- S3: "Pruebas: añade regresiones para los defectos confirmados, sin debilitar validaciones ni modificar innecesariamente el NLP."
- S4: "Compatibilidad: comprueba que backend y frontend consuman correctamente homex-nlp==0.1.24, con contratos OpenAPI consistentes."
- S5: "Verificación: ejecuta todas las pruebas, integración real y CI de los tres repositorios utilizando sus HEAD definitivos."
- S6: "Publicación: crea y sube los commits necesarios a las ramas actuales, actualiza los PR y documenta la resolución de las observaciones."
- S7: "Condiciones: no fusionar a main, no desplegar, no eliminar evidencias históricas ni modificar los audios originales. Mantener pospuestas la privacidad y la validación acústica humana."
- S8: "Entrega: informe breve con las 8 observaciones clasificadas, correcciones realizadas, commits finales, resultados de pruebas y enlaces a CI verdes."

## Tasks
- T0 [S1,S2,S7] delegated read-only maps, required because understanding exceeds five lookups; COMPLETE source map, executable classifications provisional pending controlled probes. Baselines NLP669df989/backend55cc748/frontend4dc21e4; branches/PRs unchanged and clean. Actual comment IDs retained in the new private diagnosis.
- T1 [S1,S3] inline core backend corrections COMPLETE in c2a6818990de72f4bed4794fbee5ab69e7fad942: snapshot/fallback/version and bounded transcript/exact replay. Controlled RED and focused GREEN; independent full606 passes. Risk items2/3/4.
- T2 [S1,S3,S4] delegated artifact-report/scoped-test unit COMPLETE in the source-freeze commit carrying this checkpoint; disjoint parallel writer surfaces. Own22 and parent43 focused passes, independent606 passes and ordinary installed identity verified. Risk items3/5.
- T3 [S2,S3,S4] inline frontend observations only after valid public-response loss reproduction; consumer schema regeneration/peer metadata after backend freeze. PENDING. Risk item3 if consumer behavior changes.
- T4 [S4,S5,S6,S8] delegated long checks and independent high-risk verification, exact installed wheel and final-head integration/CI, normal publication, original PR updates and concise report. PENDING. Risk items2/3/4/5.

## Log
### L1 User request (verbatim)
Codex, realiza la **última revisión técnica antes de fusionar HOMEX**.

1. **Backend PR #60:** investiga las 7 observaciones pendientes de Sourcery. Reproduce cada caso, identifica falsos positivos y corrige únicamente los defectos confirmados.
2. **Frontend PR #68:** verifica la observación pendiente sobre las observaciones estructuradas. Corrige solo si existe una pérdida real de información.
3. **Pruebas:** añade regresiones para los defectos confirmados, sin debilitar validaciones ni modificar innecesariamente el NLP.
4. **Compatibilidad:** comprueba que backend y frontend consuman correctamente `homex-nlp==0.1.24`, con contratos OpenAPI consistentes.
5. **Verificación:** ejecuta todas las pruebas, integración real y CI de los tres repositorios utilizando sus HEAD definitivos.
6. **Publicación:** crea y sube los commits necesarios a las ramas actuales, actualiza los PR y documenta la resolución de las observaciones.

**Condiciones:** no fusionar a `main`, no desplegar, no eliminar evidencias históricas ni modificar los audios originales. Mantener pospuestas la privacidad y la validación acústica humana.

**Entrega:** informe breve con las 8 observaciones clasificadas, correcciones realizadas, commits finales, resultados de pruebas y enlaces a CI verdes.

Continúa autónomamente hasta resolver todos los problemas técnicos comprobados. No declares cerrada la intervención si quedan defectos confirmados pendientes.

### L2 Initial source evidence and boundaries
Current GitHub original PRs43/60/68 remain OPEN/non-draft/CLEAN at669df989/55cc748/4dc21e4. Read-only explorers fetched the actual eight review bodies. Backend source suggests one validator-exception false positive (Django is raised and caught), five behavior/metadata issues plus one scoped-assertion gap; all await executable RED/proof before implementation. Frontend initializer demonstrably ignores structured observations, but fresh pipeline maps both representations from the same value. A valid stored public-response divergence must be reproduced before deciding consumer correction; no unsupported claim of production prevalence. RDD remains globally OFF. No root NLP source or distribution change planned. All new private evidence uses corpus evaluaciones/premerge-review-v1 and logs/premerge-review-v1; previous evidence and recordings stay untouched.

### L3 Executable diagnosis corrects preliminary assumptions
The technical validator imports DRF ValidationError, not Django; parent spot check and actual public GET reproduce HTTP400 instead of intended null/error HTTP200 fallback. The explorer's preliminary false-positive classification was wrong. The initial raw fixture tried to update a finalized attempt and correctly hit the immutable DB guard; fixed fixture inserts the technically invalid but NLP-valid value before closing. Initial core batch: fifteen failures and three passes; valid validator-specific RED then confirmed the handler defect. Core corrections pass eighteen focused cases. Three separate valid public responses prove raw projection and materialized observations may differ while the ordinary fresh pipeline usually makes them equal; frontend posted the stale representation in three controlled cases. Minimal projection-priority assignment now passes all twenty-five focused UI cases, preserving no-projection fallback and matching/null controls. No production prevalence or acoustic truth is asserted.
T2 writer completed wrong-wheel report RED, installed identity and scoped mutation proof, then twenty-two focused cases and scoped Ruff/format pass. Full shared suites, schema generation and independent high-risk verification remain pending. NLP package and all historical wheels unchanged.

### L4 Independent functional freeze
Fresh backend snapshot verification passes all606 tests, Ruff/format, Django/migrations, OpenAPI byte equality and offline lock104 packages. Private installed NLP distribution/module are0.1.24, all31 package files and operational wheel digest match. Fresh frontend snapshot passes all325 tests, types/lint/format/build and generated-contract checks; one observation assignment and six regressions are the only consumer behavior change. Core source published locally as c2a6818990de72f4bed4794fbee5ab69e7fad942; no remote publication until the coordinated metadata is finalized. Artifact writer evidence was initially placed in new relative folders; parent relocated eight files byte-identically into the authorized corpus paths and removed only those new misplaced copies. Historical evidence was not changed. The native assessment is high/unassessable for untracked inventory; no tier was lowered, RDD remains off, and independent high-risk checks ran instead of a review lifecycle. Remaining work: final peer pin, source-head real stack/E2E and current-head CI, normal pushes and original PR updates. No acoustic or privacy work is included.
