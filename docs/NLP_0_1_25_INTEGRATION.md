# NLP 0.1.25 consumer integration

The backend consumes the immutable0.1.25 wheel, matching the NLP release manifest.
Strict adapter version, pyproject/lock, runtime attestation and integration hash
checks agree. Previous vendored artifacts and historical verification remain.
Schema1.0 and RULES_ONLY are unchanged; no model/ASR/business-policy change.

The real adapter retains quantity, price, complete ordered dimensions and their
component evidence. Unknown axes remain pending, not commercial dimensions.
When scalar dimensions already reference an unresolved whole-chain candidate,
the review projection must not add a duplicate request for that same chain,
but only when all operands have individual pending resolutions. Partial or fully
resolved linked measurements cannot suppress an unresolved-chain fallback.
Unknown-owner triple chains request three missing dimensions, not two.
This compatibility adaptation does not remove raw evidence or the individual
typed missing-axis resolutions; unrepresented legacy chain evidence still gets
its existing pending request. No axis or unit is guessed by the backend.

Tests in `tests/unit/test_nlp_0125_retakes.py` use the installed public adapter:
quantities2/3/6, unit1600, calculated totals, drawer63/73 without script repairs,
false-height absence, full raw evidence retention, pending-axis handling and the
legacy unresolved fallback. Real PostgreSQL/Redis/worker and frontend review /
confirmation remain covered by the existing CI integration gates on current
Frontend main; no OpenAPI or Frontend source change is required.
