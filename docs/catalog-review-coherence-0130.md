# Catalog reviews follow the validated proposal

Backend-rejected fields now retain source evidence and a human-review observation,
without continuing to describe a discarded price as an accepted commercial suggestion.
No product, inventory, permission, provenance, or audit-history policy changes.

## Behavior

| Final validation | Proposal and review |
| --- | --- |
| Foreign currency | Remove the price, mark accepted source evidence `UNRESOLVED`, and explain the BOB-only restriction. |
| Incompatible stock unit or invalid DRF field | Remove the field and attach its validation warning to a linked review. |
| Valid BOB price | Preserve the accepted price and `COMMERCIAL_PRICE_REVIEW`. |

Existing reviews are reclassified **in place** to `BACKEND_VALIDATION_REJECTED`,
with severity `REVIEW` and the specific validation message. Review IDs and evidence
links remain stable; the review ID is an opaque identity, not its current semantic code.
New rejection reviews are created only when a field lacks an existing review.
Evidence IDs, spans, source text, and normalized values remain unchanged. Previously
persisted captures and append-only human decisions are not rewritten.

## Consumer compatibility

`ProductoForm.vue` consumes `code`, `severity`, `message`, and linked evidence, and
prioritizes the review message over the evidence reason. Updating both prevents the
UI from showing the old accepted-price explanation for a backend-discarded value.
No frontend or serialized schema change is required.

`validar_revision_voz` resolves catalog review IDs against the persisted proposal.
A rejected price has no original proposed value (`null`), but its linked review can
still record a human correction. The synthetic `field:precio_lista` identity is not
available when no accepted price remains. Existing evidence, owner, category,
origin, attempt, destination, and historical-decision checks remain enforced.

## Verification

`tests/api/test_catalogo_review_coherence_0130.py` exercises capture creation,
processing, readback, and manual product creation through the public API. It covers
USD rejection, incompatible units, DRF decimal overflow, valid BOB behavior,
stable identities/spans, and rejected forged evidence or stale original values.
Unit/overflow cases inject invalid normalized NLP values while reusing actual
extracted candidate identities and spans; they do not duplicate extraction.

The isolated UTF-8 PostgreSQL run uses `config.settings.test` and redirects media,
audio, and pytest temporary files outside the worktree. The full backend suite and
frontend test/build integration remain the parent integration checks.

Individual field validation is unchanged: this fix does not broaden the existing
validation policy to object-level `ProductoSerializer.validate()` rules.

Exact warning messages projected from replaced reviews are also removed from
the current rejected-field proposal. Valid BOB price warnings remain unchanged.
Historical persisted captures and original evidence identities remain untouched.
