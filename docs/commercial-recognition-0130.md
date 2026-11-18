# Coordinated NLP 0.1.30 consumer

The Backend uses the canonical reproducible `homex_nlp-0.1.30-py3-none-any.whl`
(SHA256 `784bf4bac0e0602cb70cdc2410c3e716d27d9fd2f5d02c3c9237603cd3ac3955`).
Dependency, offline lock, strict adapter version and operational artifact checks
advance together. Previous wheels and historical evidence remain untouched.
No permission, audit, ASR, observations or voice-limit policy is weakened.

## Proof

- Ordinary installed wheel: all 32 package files match the vendor artifact.
- Final full Backend suite: 758 passed, no warnings/errors/skips.
- Ruff, format-check, Django system check and offline lock validation passed.
- Price rejection keeps evidence and review IDs, reclassifies the review, removes
  stale suggestion warnings and leaves the invalid field absent. Manual correction
  preserves provenance validation and uses null as the original rejected value.
- Actual final Backend payload was exercised in the unchanged Frontend component
  in an isolated test copy: no invalid autofill; correct rejection message and audit.

The initial unaligned installed-wheel test exposed the old strict 0.1.29 guard
(204 failures, 13 errors). The guard was advanced to the verified exact artifact,
not removed or generalized. Complete historical diagnostic logs remain external.

Canonical feature specification and differential report are in homex-nlp:
`odd/tasks/commercial-recognition-0130.md` and `docs/commercial-recognition-0130.md`.
The 120 frozen ASR inputs are unchanged; gains are demonstrated in directed
development probes, not acoustic gold or independent generalization.
Publication was explicitly authorized without merge or release. Current remote
CI is available on the linked PRs below.

## Published feature-branch chains

No merge, deployment or release is authorized. Trackers remain draft until all
children and coordinated integration have been reviewed. Current CI status is
available on each linked PR; a pending or skipped external review is not a pass.

| Repository | PR | Head → base | Role |
| --- | --- | --- | --- |
| homex-nlp | [#48](https://github.com/gabriel-arinez/homex-nlp/pull/48) | `feat/commercial-recognition-0130` → `main` | Draft tracker, no merge |
| homex-nlp | [#49](https://github.com/gabriel-arinez/homex-nlp/pull/49) | `feat/commercial-recognition-0130-identity` → `feat/commercial-recognition-0130` | Review slice |
| homex-nlp | [#50](https://github.com/gabriel-arinez/homex-nlp/pull/50) | `feat/commercial-recognition-0130-names-ci` → `feat/commercial-recognition-0130-identity` | Review slice |
| homex-nlp | [#51](https://github.com/gabriel-arinez/homex-nlp/pull/51) | `feat/commercial-recognition-0130-furniture-ci` → `feat/commercial-recognition-0130-names-ci` | Review slice |
| homex-nlp | [#52](https://github.com/gabriel-arinez/homex-nlp/pull/52) | `feat/commercial-recognition-0130-evaluation-ci` → `feat/commercial-recognition-0130-furniture-ci` | Review slice |
| homex-nlp | [#53](https://github.com/gabriel-arinez/homex-nlp/pull/53) | `feat/commercial-recognition-0130-report-ci` → `feat/commercial-recognition-0130-evaluation-ci` | Review slice |
| homex-backend | [#63](https://github.com/gabriel-arinez/homex-backend/pull/63) | `feat/commercial-recognition-0130` → `main` | Draft tracker, no merge |
| homex-backend | [#64](https://github.com/gabriel-arinez/homex-backend/pull/64) | `feat/commercial-recognition-0130-reviews` → `feat/commercial-recognition-0130` | Review slice |
| homex-backend | [#65](https://github.com/gabriel-arinez/homex-backend/pull/65) | `feat/commercial-recognition-0130-package` → `feat/commercial-recognition-0130-reviews` | Review slice |
