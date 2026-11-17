# Commercial voice integration fixtures

The real-stack CI fixtures must satisfy the commercial assistant's existing 20-word minimum. The furniture phrase contained 11 words; flooring and other-product phrases were similarly too short even though generated audio included 20 seconds of silence.

Synthetic dictations now include explicit complementary commercial observations. Existing product, price, material, dimension and category anchors are preserved. The new pure regression test covers every synthetic commercial phrase against the same operational word counter and 3,000-character maximum used by the API.

Observed RED: short furniture fixture failed. GREEN: all four fixture texts pass. No application validation or security check is disabled. GitHub real-stack jobs verify actual ASR output; source word counts alone do not prove acoustic recognition.

The normal f09 CI consumer is pinned to frontend `7d19395b9d77898f7c35383004dc75ff1f422bce`, whose OpenAPI bytes match this backend and whose declared backend reference is ancestor `7c9e748213a23e650d76120e64d9a8b2fdd6a3df`. The strict contract/ancestry verifier remains unchanged. Manual exact-peer dispatch remains enabled for merged-main verification.
