# Verify thickness assignment and correction separately

A pending thickness may be assigned only to a component with the same exact normalized measurement. For example, 18 mm, 1.8 cm and 0.018 m are equivalent; 25 mm is not.

The form exposes **Confirmar corrección de espesor** separately from assignment. A different valid thickness requires a `corregido` decision with immutable original evidence, actual final component value and capture identity. Edits or reversal reopen the pending review. The backend validates all claims independently, preserving ownership, permissions, immutable capture provenance and repeated-save idempotency.

Root cause: the old backend required only a populated thickness, and the form audited the pending value rather than the actual component value.

Verification: backend focused RED 6 failures then GREEN 9 tests; frontend thickness/field-review GREEN 10 tests. Final independent suites: backend 752 passed; frontend 412 passed, including correction and reversal. No schema migration is introduced.

Rollback boundary: `revision_voz.py`, the form's thickness controls and `pendientesAsistencia.ts`, and their regression tests must be reverted together. No historical audit records are rewritten. See `voice-hitl-corrective-verification.md` for the integration ledger.
