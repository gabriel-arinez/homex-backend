# PRF-04 verifies the installed NLP artifact

The PRF-04 integration report now identifies the ordinary installed `homex-nlp==0.1.24`
artifact, not the historical `0.1.21` vendor wheel. Existing CLI arguments and metric
fields remain unchanged; `nlp_artifact` adds distribution/module versions, module
origin, wheel filename, and the count of verified packaged files.

## Verification boundary

Before querying captures or reporting metrics, the verifier checks:

- Distribution metadata and imported module versions both equal `0.1.24`.
- The operational vendor wheel matches SHA-256
  `12d1dab78a5e1ea04780e0e3345e1885cc5dc9edf5c7b2aa1b989f8349379ec6`.
- Every wheel file except installer-rewritten `RECORD` is listed in the installed
  manifest and matches its installed bytes, including package data and metadata.
- Imported package/submodule origins agree with distribution paths; editable
  installs and unexpected package files are rejected. Generated `__pycache__`
  files are excluded from the package inventory.

Historical wheels and evidence remain untouched. This verifies the verifier's
process, not a separate worker's filesystem; run it in the same controlled runtime
as the integration being measured.

## Scoped contract regression

Installed-wheel contract tests compare exact `(component_ref, axis, value_mm)`
sets for general and component dimensions. A controlled in-memory mutation clears
component references: the old axis/value-only comparison still passes, while the
scope-aware comparison fails. The package output and source evidence are unchanged;
this closes an assertion gap without changing NLP behavior.
