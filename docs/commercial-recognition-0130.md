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
Remote CI/PR publication remains subject to explicit authorization.
