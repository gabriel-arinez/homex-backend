# Project quantity-one monetary review suggestions

An unresolved monetary amount reaches `comercial.precio_unitario` only when the
extractor marks equivalence for an explicit root quantity one. The pending
`PRECIO_AMBIGUO` and its explanatory message remain; NLP price mode stays absent.
No quantity is inferred from the configurator's fallback quantity.

The existing review validator maps this pending to `precio_unitario`. It reads
the original amount from the immutable server projection and checks field,
evidence, original value, final saved value, positive amount, and decision state.
`confirmado` cannot modify the original proposal; `corregido` can. Existing
permissions, final totals, discounts, transaction and idempotency controls remain.

Regression: `tests/api/test_residual_money_review.py` exercises public capture,
projection, integral save, forged originals, invalid confirmations, and replay.
