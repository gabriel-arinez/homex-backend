# Coherent review and bounded capture reception

Each review representation selects one finalized attempt, including its absence,
and reuses it for the attempt ID, materialized item and structured projection.
A new representation takes a fresh snapshot. Invalid NLP/technical evidence
returns a null projection with an explicit error flag; it does not rewrite raw
history or turn a readable capture into a failed review request.

The producer's existing projection version is now an optional additive output.
Existing clients may ignore it and older response DTOs remain representable.

New text requests retain the20,000-character limit. Only an existing exact
idempotent receipt may replay an older oversized text: actor, quote, detail and
original input hash must all match the authoritative existing guard. The replay
lookup never creates a capture, attempt or outbox task. Unknown keys still go
through normal length rejection and conflicting keys remain409.

Audio transcription uses the same boundary before either NLP branch. Over-limit
ASR text remains intact as evidence, closes with TRANSCRIPT_TOO_LONG and creates
no proposal. Accepted-length behavior, exactly-one-input checks, permissions,
quote states and the immutable-attempt guard are unchanged.

Regression commands and immutable evidence are recorded in the pre-merge task
checkpoint and the new corpus premerge-review-v1 evaluation/log directories.
Risk: items2/3/4 (authorized replay, shared response fields, concurrent completion).
