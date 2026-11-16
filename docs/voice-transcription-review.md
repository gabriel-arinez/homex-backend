# Review voice transcription before interpretation

Catalog and custom-furniture capture endpoints support an additive, opt-in ASR-only stage. Existing clients that omit the option retain combined ASR/NLP behavior.

## Request and review

1. POST audio to `/api/v1/capturas/catalogo/` or `/api/v1/capturas/asistidas/` with `solo_transcribir: true`, a fresh `clave_idempotencia`, and the existing session/context fields. The option requires audio.
2. Poll the returned capture. Terminal success is `estado: COMPLETADA`, `solo_transcribir: true`; catalog `propuesta` is null, assisted `resultado` is `TRANSCRIBED` and `propuesta_configurador` is null. No NLP, product writes, or proposal projection runs.
3. Review/edit `texto_transcrito_original`. POST the corrected `texto` with a new idempotency key and `captura_origen` referencing the audio capture, retaining the same session, owner, category/currency/proforma context. Do not set `solo_transcribir` for text.
4. Poll the new capture for the existing NLP proposal. Applying a proposal remains an explicit client-side action; these endpoints never apply form or commercial data automatically.

## Audit and evidence

Both poll responses add `captura_origen`, `solo_transcribir`, `texto_asr_original`, and `texto_corregido`. The original capture's immutable `texto_transcrito` is not edited. `texto_transcrito_original` retains its historical meaning: the current capture's input text. A linked text capture exposes the origin's transcript in `texto_asr_original` and its own text in `texto_corregido`.

Assisted responses additionally expose `candidatos` and `advertencias` copied from the real NLP response. Candidates contain `candidate_id`, `label`, `start`, `end`, `text`, `source`, `normalized_value`, `component_ref`, `decision`, and `reason`. Warning fields are `code`, `path`, `severity`, and `message`. Offsets refer to the corrected text processed by NLP, not the original audio transcript. No invented field/span associations are added.

The ASR-only request is persisted in the attempt's existing JSON metadata. Its input hash distinguishes ASR-only from combined processing without changing hashes for existing requests. Completion retains the execution-token/attempt lock checks; no schema migration is necessary.

## Limits and worker deadlines

- Text: at most 20,000 characters and at least one Unicode letter. Whitespace, punctuation, numbers-only, and emoji-only inputs are rejected. Commercial sufficiency remains an NLP decision: short legitimate names are allowed.
- Audio: decoded duration between 2 and 300 seconds; at most 20 MB. Decoding counts samples rather than trusting uploaded metadata. Silent audio is not rejected based on amplitude; an empty ASR transcript returns `TRANSCRIPT_EMPTY` while preserving evidence.
- CPU Whisper: configurable `HOMEX_CAPTURE_SOFT_TIME_LIMIT` (default 1,200 seconds) and `HOMEX_CAPTURE_TIME_LIMIT` (default 1,260 seconds, at least soft limit + 60). Reconciliation and audio retention cannot fall below the hard deadline plus safety margins. The worker deadline is independent of the UI polling deadline. These limits bound work; they do not promise an inference latency for every CPU/model.

## Verification

`tests/api/test_voice_transcription_review.py` checks both capture modes, no NLP during ASR-only work, no ASR for corrected text, preserved audit, original ownership/session guards, stage-aware idempotency, exact candidate evidence, invalid text/transcripts, decoded duration boundaries, and real WAV decoding when PyAV is installed. Existing catalog, assisted, and worker-audio suites verify combined-client compatibility.

## Vendored NLP integration

The staged workflow consumes the immutable `homex_nlp-0.1.26-py3-none-any.whl` artifact (SHA-256 `a1d4d00e79d924a8c53cdb038b64b639b243611f6241a8d48618ae983c76d5d3`). The released 0.1.25 wheel remains unchanged. Backend dependency, runtime adapter, and operational identity checks require 0.1.26; historical artifact checks retain their original identity.

The wheel rejects catalog chatter such as `hola buenas`, `probando`, `uno dos tres`, `hola 123`, and `probando123`, and abstains on undescribed `mueble`/`un mueble`. Legitimate short `silla plegable`, explicit novel names such as `nombre: Credenza Nórdica`, and described custom furniture remain eligible. Backend integration tests exercise the actual installed artifact through both APIs and preserve rejected currency evidence offsets and unresolved decisions. The decoded minimum also has a hard two-second floor even when a caller requests a lower minimum.

An isolated worktree virtual environment was populated with `uv sync --offline --extra dev --extra worker`; it does not modify the original checkout's virtual environment. Installed package bytes were compared with all 32 Python-package files in the vendored wheel.
