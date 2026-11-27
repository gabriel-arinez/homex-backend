# Lote02 candidate distribution

The candidate consumes exactly `homex_nlp-0.1.31-py3-none-any.whl`, SHA-256
`f758092f002f0a77e15719adf65fd49104493287d40ff7e0116e1fdb6b4899b3`.
The dependency, vendored artifact, lock hash, adapter and both operational identity
gates advance together. Historical wheels and historical release reports remain unchanged.

Rules identity: `prf04-rules-context-3`; catalog identity: `catalog-0.1.31`.
Contracts remain schema 1.0; inference uses existing unresolved candidates and
optional review-resolution metadata, not a new public schema.

Install only from the reviewed candidate checkout with `uv sync --locked`.
Verify the installed artifact through `scripts/verificar_prf04_integracion.py` in
an explicitly authorized environment; it rejects source overrides and altered files.
That script has operational prerequisites and is not permission to execute against
production. Unit tests exercise its identity guard without contacting real services.

The full evidence bundle records isolated checks, actual loaded module origins,
wheel hashes and residual failures. This document does not certify final release
readiness. No deployment, merge or commercial-data migration is authorized.
