# Partial voice extraction remains separate from final saving

Commercial capture intake now accepts short, processable transcripts. The former
20-word gate rejected legitimate inputs before the NLP engine could decide whether
a commercial identity was sufficient. Both assisted furniture and catalog intake
retain their 3000-character maximum and require a Unicode letter. Blank, numeric-only
and punctuation-only text remain invalid.

## Review path

1. POST the original text to `/api/v1/capturas/asistidas/` (or the existing catalog
   capture endpoint) with the usual authenticated context and idempotency key.
2. Process the existing capture attempt and GET its review result.
3. Review the recognized proposal; absent prices and specifications remain pending.
4. Complete the mandatory commercial fields before final saving. Extraction does
   not create products, clients, proformas or details.

The serializer does not duplicate NLP commercial sufficiency rules. Greetings may
enter processing but must produce `NO_PROPOSAL`. Original text is not normalized or
rewritten at intake, preserving downstream evidence offsets. Permissions, strict
request fields, ownership, idempotency and final-save validation are unchanged.

## Focused evidence

`tests/api/test_final_partial_capture.py` exercises the real POST →
`procesar_intento` → GET path for `una mesa`, `una mesa simple`,
`tres escritorios blancos` and `un mueble de melamina`. It checks proposal identity,
explicit quantity, missing price and dimensions, original text, no commercial writes,
replay/conflict behavior and rejection of final saving without price. Shared-route
boundary cases cover Unicode text, blanks, noise and the 3000-character limit.

The intake tests intentionally check identity family, not the complete qualifier
vocabulary; qualifier retention belongs to the NLP identity regression suite.

## Authorized policy regression update

Final-lote02 S2/S12 explicitly replace the minimum-word policy with processable
letter-bearing text. The parent authorized updating the exact legacy 19-word
assertions in `test_final_commercial_voice_limits.py`: 19 words are now admitted;
empty, punctuation-only and numeric-only inputs still fail. This is a requirement
change, not weakening tests merely to make a candidate pass. Maximum-character,
audio-duration, authorization, idempotency and final-save checks remain intact.

## Reviewable inference and technical knowledge

`test_final_inferred_projection.py` verifies that inferred units and shared gauges
remain typed suggestions, not explicit form values. Root axes keep their explicit
measurements, including explicit component measurements. An inferred component
axis uses the existing optional `resolucion.valor` string as an axis marker;
frontend and backend require a positive value and valid unit for that specific
axis, not merely another nonempty axis. Human corrections need not equal the
suggested number. Legacy requests without a marker retain their behavior.
Shared-unit gauges use `ESPESOR_SIN_COMPONENTE` and require an explicit destination
or audited correction; an existing different explicit gauge is never overwritten.
The original 110/65 cm component prepopulation regression tests remain unchanged.

Complete ambiguous amounts remain review messages. Quantity one explains the
arithmetic equivalence between unit and total without inventing a spoken price
mode; quantities above one do not derive unit prices. Existing commercial
validation remains authoritative.

Material-role classifications, contextual lexical recoveries, geometry, ranges,
color selection and per-side distribution remain review evidence. Explicit brands
use existing technical attributes; accessory material stays with the accessory.
Explicit two-color combinations use consistent primary/secondary legacy slots and
role-named attributes, not competing writes to the single legacy Color attribute.
Bounded service observations and all original candidate offsets are preserved.

Verification uses only the isolated PostgreSQL test database configured by the
external `final_isolation_settings`; no ASR or historical corpus is rerun. Final
full-suite, browser and distribution checks belong to the parent integration task.
