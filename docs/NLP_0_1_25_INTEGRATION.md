# NLP 0.1.25 consumer integration

The backend consumes the immutable0.1.25 wheel, matching the NLP release manifest.
Strict adapter version, pyproject/lock, runtime attestation and integration hash
checks agree. Previous vendored artifacts and historical verification remain.
Schema1.0 and RULES_ONLY are unchanged; no model/ASR/business-policy change.

The real adapter retains quantity, price, complete ordered dimensions and their
component evidence. Unknown axes remain pending, not commercial dimensions.
Root unknown-axis chains use one aggregate resolution with the complete literal
operand count. Frontend evaluates every pending independently against the global
count of new measurements: N requests of1 would not require N distinct measures.
Component chains retain scoped component-field resolutions, not new root axes.
Only complete pending coverage can suppress the whole-chain fallback. Partial or
fully resolved linked data cannot erase a still-unresolved chain; unknown-owner
triples require3 dimensions and the legacy pair remains2. Raw evidence is kept.

Tests in `tests/unit/test_nlp_0125_retakes.py` use the installed public adapter:
quantities2/3/6, unit1600, calculated totals, drawer63/73 without script repairs,
false-height absence, full raw evidence retention, pending-axis handling and the
legacy unresolved fallback. Real PostgreSQL/Redis/worker and frontend review /
confirmation remain covered by the existing CI integration gates on current
Frontend main; no OpenAPI or Frontend source change is required.
