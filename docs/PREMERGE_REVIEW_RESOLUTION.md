# Final eight-comment review: verified boundaries

This follow-up preserves NLP0.1.24 and its reviewed wheel. It changes backend
review/ingress/report behavior and the frontend observations consumer only where
controlled tests demonstrate a defect. No privacy cleanup, acoustic adjudication,
main merge or production deployment is included.

| Comment | Disposition and regression |
|---|---|
| PR60/4569818776 | Partially confirmed wording: technical validation raises DRF ValidationError and the old review GET returns400, not500. Catch it with the existing explicit null/error projection fallback; preserve raw evidence. |
| PR60/4569818790 | Confirmed response consistency defect. Select one finalized attempt, including absence, per representation; refresh the snapshot when the serializer is reused. |
| PR60/4569818804 | Confirmed processing-outcome gap. Preserve the full ASR transcript and reject over-limit output before either NLP branch with TRANSCRIPT_TOO_LONG, without a proposal or truncation. |
| PR60/4569818817 | Confirmed historical replay regression. Only an exact matching existing receipt can bypass the new-request length check. Reuse the authoritative actor, quote, detail and input-hash checks; unknown keys remain400 and conflicting keys409. No new work is created. |
| PR60/4569818832 | Confirmed metadata omission. Expose the producer's existing version_proyeccion as an additive optional response field, preserving older-client DTO compatibility. |
| PR60/4569818846 | Confirmed report identity defect. Verify the installed reviewed artifact before reporting runtime metrics; retain historical wheels and reports. See PREMERGE_WHEEL_IDENTITY.md. |
| PR60/4569818859 | Confirmed test-coverage gap, not a demonstrated NLP extraction defect. Assert exact component-reference/axis/value tuples; mutation clearing component refs must fail. |
| PR68/4569816481 | Conditional consumer loss confirmed with valid public API responses backed by independently stored raw and materialized observations. Fresh current pipeline normally produces equal fields; no production-frequency claim. Use structured observations when projection exists, and legacy observations only without a projection. Test both displayed text and posted correction, including nulls. |

The first read-only map incorrectly identified the technical validator exception
as Django's. Direct source inspection and an executable public GET disproved that
hypothesis before fixing the handler. An initial invalid-evidence test attempted
to mutate a closed attempt and correctly hit its immutable DB guard; the fixture
was corrected to insert invalid technical evidence before finalization. That
failed setup is retained, not counted as proof of a product defect.

Core backend RED: fifteen failures/three controls passed, including the initial
fixture mistake; corrected validator-only RED proves actual HTTP400. Core fixes
then passed eighteen cases; three additional public-response observation cases
pass without modifying the immutable source rows. Frontend RED has three losses
and twenty-two controls passing; one initialization assignment restores all
six observation combinations and all twenty-five focused cases.

The committed task document is a source-freeze checkpoint. Terminal exact-HEAD
CI, installed-wheel integration and PR publication evidence are recorded in the
new local corpus evaluation/log directories, never substituted by these focused
counts. Full suites and independent verification remain required before closure.

Rollback boundaries: the review snapshot/fallback/version changes, the bounded
transcript/replay changes, artifact verification, and frontend observations can
be reviewed separately. No migration or stored-format rewrite is involved.
Risk: items2/3/4/5 (authorized replay, shared response data, concurrent completion,
installed distribution identity). No permission, state or stock guard is relaxed.
