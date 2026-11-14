# Preserve explicitly scoped accessories in configurator proposals

The PRF-03 projection now retains accessories whose producer-contract
`component_ref` identifies a proposed component. Previously those accessories
were excluded from the global list without being copied to the component.

## Representation

- Global accessories remain in `datos_tecnicos.accesorios`.
- Explicitly scoped accessories use the existing component `atributos` array:
  `{"nombre": "Accesorios", "valor": "2 USB; 3 HDMI"}`.
- Multiple values retain producer order in one attribute; quantities are not
  summed, and an absent quantity stays absent.
- Invalid references remain rejected by the existing NLP contract validation;
  the projection also leaves a review warning if an unresolved reference reaches
  its defensive route. Neither route guesses a component or promotes it globally.

This does not establish acoustic or syntactic truth for the association. It
preserves the explicit upstream relationship for human review. The raw extraction,
stock, approved commercial prices and draft quote are not modified by reading a
proposal. No public schema, frontend source or NLP wheel change is required.

## Reproduce

With the locked backend environment, installed NLP wheel and test PostgreSQL:

```sh
uv run pytest -q tests/api/test_scoped_accessory_projection.py
uv run ruff check apps/capturas/proyeccion_prf03.py tests/api/test_scoped_accessory_projection.py
```

Observed test-first evidence: 3 failures / 4 passes before the change; all 7
pass after it. Full independent and final published-head integration evidence
is recorded separately in the coordinated real-voice audit.

Rollback boundary: this projection route and its focused tests/document only;
no migration, stored-data rewrite or artifact replacement.
Risk: item 3 (shared proposal projection consumed by the configurator).
