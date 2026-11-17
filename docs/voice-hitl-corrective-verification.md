# Trusted voice-review correction

The existing ASR → editable text → explicit NLP → explicit application flow is preserved. Work remains on `feat/voice-hitl-review`; no publishing, PR or main merge was performed.

## Changes

- Catalog responses expose additive typed `field_reviews` with stable review IDs, severity, real field paths and candidate IDs; warning strings remain compatible.
- `revision_voz.py` validates browser claims against immutable server attempts: actor/context, source ancestry, original values, actual evidence and the latest saved value. Reused IDs cannot rewrite historical decisions. Repeated unchanged saves preserve history without duplication.
- Catalog adds the optional `revision_humana_voz` JSON channel through migration `0012_voice_review_audit`. Existing furniture audit and immutable `RevisionAsistida` remain intact.
- Audit validation reads actual stored common and category-specific values, including notes, nested chair specifications and flooring dimensions. Decimal-equivalent values remain equivalent.
- Catalog's existing nonnegative-price policy is preserved; furniture prices and quantities retain their positive-value rules. The audit does not introduce stricter unrelated commercial requirements.
- ASR origin, ownership, session, permission and idempotency controls remain covered; text reinterpretation never runs Whisper again.

## Final component checks

| Check | Result |
| --- | --- |
| Full backend suite after final normalization | 703 passed, zero skips |
| Independent public API, audit, history and package subset | 78 passed |
| Focused audit regression suite | 22 passed |
| Ruff lint/format | Passed, 394 files |
| Django system/migration checks, offline lock, schema drift | Passed |
| Operational installed artifact verifier | Passed, 35 files |

Specific RED regressions cover forged audit acceptance, missing persisted notes during floor review, and a valid manual zero catalog price being incorrectly rejected only when accompanied by audit metadata. Owner/session/forgery rejection remains atomic. The independent baseline probe used the actual historical 0.1.27 wheel with untouched backend source, not a mismatched 0.1.28 runtime.

The only OpenAPI warning is the baseline-existing `CategoryEnum` naming collision; schema validation has no errors. The frontend snapshot and generated types match this schema.

## Package identity

Actual installed and vendored version: **homex-nlp 0.1.28**.

SHA256: `abf68e16979c9cdf64eff534051798cec3a12b9d27672fd0f9fcd4805e825fea`.

The wheel, checksum file, offline lock, adapter version guard, operational checksum pins and installed bytes agree. Producer source and installed-wheel suites each passed 1,185 tests. Historical 0.1.25, 0.1.26 and 0.1.27 artifact bytes were not changed. No package was published.

Cross-component browser/CPU-Whisper evidence and final commit identities are recorded in the frontend's `docs/voice-hitl-corrective-verification.md`. Tests use disposable local PostgreSQL and synthetic fixtures, not production data or claims about field speech accuracy. Remote CI was not triggered.

Risk: items 1, 2, 3 and 5 — persisted audit, ownership/provenance, additive consumed contracts and coordinated package integration. Functional and independent verification cover these surfaces.
