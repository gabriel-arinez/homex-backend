# Final commercial voice validation (2026-11-17)

Final verification is complete on the existing `feat/voice-hitl-review` branches. No PR, push, merge or package publication is authorized. Earlier verification below is historical. The current ledger and `evidence/voice-validation-final.json` bind this final candidate.

## Current contract

**Audio ≥15 seconds → automatic ASR → editable transcript (≥20 words, ≤3,000 characters) → explicit NLP → commercial proposal or abstention → HITL → confirmed application.**

- Microphone maximum: 240 seconds; uploaded files: 300 seconds and 20,000,000 bytes. Rejected decoded audio creates no capture, attempt or outbox job. Browser validation precedes submission; backend decodes before admission. The API runtime now declares the existing PyAV decoder directly because validation precedes the worker.
- Only commercial voice-assistant endpoints enforce the text thresholds. General NLP, manual products and historical inputs retain their existing contracts. Whitespace-separated tokens containing Unicode letters or numbers count as words; isolated punctuation does not. Character counting uses Unicode code points on both sides.
- ASR output is retained intact, including over-limit text. Oversized typing/paste is rejected with a message; existing content is preserved. Over-limit ASR text can be reduced before explicit interpretation.
- Catalog extraction uses positive commercial evidence and category compatibility, not greeting/testing/microphone/name blacklists. Commercial insufficiency still produces abstention or evidence-backed partial fields.
- Thickness assignment compares exact normalized measurements. A different value requires a distinct verified correction event retaining original and final values; edits/reversions reopen review. Existing ownership, immutable provenance and idempotency checks remain.
- Observations no longer receive an entire-input/description fallback. Explicit complementary observations retain evidence; applying proposals preserves manual notes and ignores legacy notes equal to the full transcript.

## Calibration and artifact identity

| Evidence                                            | Words          | Characters | Threshold result |
| --------------------------------------------------- | -------------- | ---------- | ---------------- |
| 120 written scripts                                 | 30–96          | 192–645    | 120/120 pass     |
| 120 stored real ASR transcripts                     | 27–90          | 150–554    | 120/120 pass     |
| Backend historical synthetic 240-second experiment  | Not remeasured | 2,807      | Pass             |
| Frontend historical synthetic 240-second experiment | 99             | 638        | Pass             |

The written snapshot available here peaks at 645 characters, not the approximate 671 in the request. The two long experiments are different synthetic recordings, not genuine four-minute seller dictations. Stored real-ASR duration metadata is null. No evidence available requires raising 3,000 characters; this does not claim universal coverage of real long dictation.

NLP **0.1.29**, wheel SHA-256 `4e8ccb3362152e69ec552917a44c19f839b4f56c737a2e8997f3f23d4ebbff50`. Installed metadata and all 32 package files match the wheel/source; the only changed Python modules relative to 0.1.28 are package identity and catalog extraction. Previous wheels/checksums remain unchanged. Source and installed-wheel NLP suites: **1,209 passed each**.

## Verification ledger

- Observed RED before implementation for thresholds, forbidden-name regressions, observation preservation and thickness integrity; focused GREEN completed.
- Final independent backend suite: **752 passed**; frontend Vitest: **412 passed**. Source and installed NLP suites: **1,209 passed each**.
- Browser verification covers **115 cases**: initial full run **108 passed / 7 failed**, followed by the single scoped test-fixture correction and **7/7 passing rechecks**. The failures used short/undecodable fixtures invalidated by the new thresholds; no production correction was needed. The staged seller-flow/accessibility E2E passed.
- Frontend typecheck/lint/format and production build, backend lint/format/system checks/migration drift, offline locks, NLP/backend builds, generated OpenAPI/types and contract check passed. OpenAPI retains one non-fatal `CategoryEnum` choice-set naming warning and no schema errors.
- Parent reran the reported 23-test voice subset and backend Ruff successfully. The backend feature worktree has a durable ignored `.venv` installed offline with 0.1.29; all 32 package files match the new wheel.
- Implementation commits: NLP `bf67a50`; backend `f311c8d`, `2ccab9a`; frontend `23d3343`, `980720c`, `169c138`. Documentation-only closure is the final branch HEAD. The evidence JSON lists modified files and commands/outcomes. Historical artifacts and prior commits remain intact.
- NLP's configured Makefile lint/format scope (`src tests tools training`), schema export check and offline lock passed. An additional noncanonical whole-tree scan found **338 lint errors / 30 unformatted files** in preserved audit scripts; the exact same counts reproduce on baseline `50216e5`. Those frozen artifacts were not changed. Python repositories do not configure a standalone static typechecker; frontend `vue-tsc` passed.
- RDD remains globally disabled by existing user preference; no native review consent or lifecycle started. Independent functional verification passed for audit/contract/package risk.
- No remote CI or physical microphone/device verification is claimed. Browser tests use synthetic audio and local route stubs; backend tests decode real PCM and exercise the installed NLP package.

## Prior intervention (historical)

# Trusted voice-review correction

The existing ASR → editable text → explicit NLP → explicit application flow is preserved. Work remains on `feat/voice-hitl-review`; no publishing, PR or main merge was performed.

## Changes

- Catalog responses expose additive typed `field_reviews` with stable review IDs, severity, real field paths and candidate IDs; warning strings remain compatible.
- `revision_voz.py` validates browser claims against immutable server attempts: actor/context, source ancestry, original values, actual evidence and the latest saved value. Reused IDs cannot rewrite historical decisions. Repeated unchanged saves preserve history without duplication.
- Catalog adds the optional `revision_humana_voz` JSON channel through migration `0012_voice_review_audit`. Existing furniture audit and immutable `RevisionAsistida` remain intact.
- Audit validation reads actual stored common and category-specific values, including notes, nested chair specifications and flooring dimensions. Decimal-equivalent values remain equivalent.
- Catalog's existing nonnegative-price policy is preserved; furniture prices and quantities retain their positive-value rules. Inch dimensions (`pulgadas`) remain valid exactly as in the existing manual form. The audit does not introduce stricter unrelated commercial requirements.
- ASR origin, ownership, session, permission and idempotency controls remain covered; text reinterpretation never runs Whisper again.

## Final component checks

| Check                                                      | Result                           |
| ---------------------------------------------------------- | -------------------------------- |
| Full backend suite after final normalization               | 704 passed, zero skips           |
| Independent public API, audit, history and package subset  | 78 passed; final audit 23 passed |
| Focused audit regression suite                             | 23 passed                        |
| Ruff lint/format                                           | Passed, repository scope         |
| Django system/migration checks, offline lock, schema drift | Passed                           |
| Operational installed artifact verifier                    | Passed, 35 files                 |

Specific RED regressions cover forged audit acceptance, missing persisted notes during floor review, and a valid manual zero catalog price being incorrectly rejected only when accompanied by audit metadata, plus supported inch dimensions rejected only by the new audit. Owner/session/forgery rejection remains atomic. The independent baseline probe used the actual historical 0.1.27 wheel with untouched backend source, not a mismatched 0.1.28 runtime.

The only OpenAPI warning is the baseline-existing `CategoryEnum` naming collision; schema validation has no errors. The frontend snapshot and generated types match this schema.

## Package identity

Actual installed and vendored version: **homex-nlp 0.1.28**.

SHA256: `abf68e16979c9cdf64eff534051798cec3a12b9d27672fd0f9fcd4805e825fea`.

The wheel, checksum file, offline lock, adapter version guard, operational checksum pins and installed bytes agree. Producer source and installed-wheel suites each passed 1,185 tests. Historical 0.1.25, 0.1.26 and 0.1.27 artifact bytes were not changed. No package was published.

Cross-component browser/CPU-Whisper evidence and final commit identities are recorded in the frontend's `docs/voice-hitl-corrective-verification.md`. Tests use disposable local PostgreSQL and synthetic fixtures, not production data or claims about field speech accuracy. Remote CI was not triggered.

Risk: items 1, 2, 3 and 5 — persisted audit, ownership/provenance, additive consumed contracts and coordinated package integration. Functional and independent verification cover these surfaces.
