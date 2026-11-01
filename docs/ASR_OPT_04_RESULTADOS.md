# ASR-OPT-04 — resultados agregados, 2026-10-31

Doce perfiles de un factor en Small/Medium/Turbo;29 corridas escalonadas y196
transcripciones nuevas, baseline60 reutilizada. Cinco full20, resto detenido según
gates. No holdout, auditoría acústica0, campos comerciales confirmados0.
No se cambió normalizador, referencia, audio, pesos ni parámetros operativos.
N de riesgo272 palabras; full20 863. Δ respecto al mismo modelo y mismos audios.

|Modelo|Perfil|N audios final|WER numérico|CER numérico|ΔWER pp|Inf final(s)|RSS pico MiB|Gate|
|---|---|---:|---:|---:|---:|---:|---:|---|
|small|hotwords|7|4.7794%|3.2096%|-0.3676|18.118|815.2|REJECT_CRITICAL_OR_AMBIGUOUS|
|small|initial_prompt|7|4.0441%|3.0208%|-1.1029|19.866|877.6|REJECT_CRITICAL_OR_AMBIGUOUS|
|small|beam3|7|5.8824%|3.3984%|+0.7353|17.567|815.3|REJECT_RISK_WER_NO_CRITICAL_BENEFIT|
|small|no_previous_text|7|5.8824%|3.5242%|+0.7353|18.718|814.4|REJECT_CRITICAL_OR_AMBIGUOUS|
|medium|hotwords|7|4.4118%|3.0837%|+0.7353|53.798|2248.6|REJECT_CRITICAL_OR_AMBIGUOUS|
|medium|initial_prompt|7|3.6765%|2.9578%|+0.0000|51.483|2258.0|REJECT_CRITICAL_OR_AMBIGUOUS|
|medium|beam3|20|1.2746%|0.9684%|+0.0000|152.464|2138.9|FULL20_OBSERVED_NO_NEW_CRITICAL_EVENT|
|medium|no_previous_text|20|1.2746%|0.9684%|+0.0000|161.456|2137.6|REJECT_SCOPE_REVIEW|
|large-v3-turbo|hotwords|7|2.9412%|2.8320%|+0.0000|46.680|2051.3|REJECT_CRITICAL_OR_AMBIGUOUS|
|large-v3-turbo|initial_prompt|20|1.2746%|0.9289%|+0.1159|155.091|2054.7|FULL20_OBSERVED_NO_NEW_CRITICAL_EVENT|
|large-v3-turbo|beam3|20|1.1587%|0.9289%|+0.0000|157.772|2051.6|FULL20_OBSERVED_NO_NEW_CRITICAL_EVENT|
|large-v3-turbo|no_previous_text|20|1.1587%|0.9289%|+0.0000|160.671|2051.6|FULL20_OBSERVED_NO_NEW_CRITICAL_EVENT|

Hotwords y prompt son vocabulario genérico sin números/especificaciones del corpus.
Beam3 y contexto previoFalse cambian solo ese factor. Todas las corridas CPU/int8
(request; CT2 effective int8_float32), un hijo por vez. Coste nuevo1306.774s de
inferencia, sin abortos de recursos. RSS máximo2258MiB aproximadamente; swap del
hijo y carga externa se conservan en expediente. Tiempos observacionales, no causalidad.

El gate posterior de ámbitos observa un cambio de asociación de color en un perfil
sin contexto previo: requiere revisión, no acredita error acústico. La salida del
gate automático inicial se conserva. `scope_gate.py` compara nombres vinculados y
decisiones, sin confundir IDs efímeros con identidad ni convertir ambigüedad en acierto.
Otro cambio de accesorio fue solo unión léxica; se conserva separado de valores.

Ninguna variante aceptada reduce WER numérico de su baseline. No hay dos factores
favorables compatibles para combinar. No se añade VAD ni recorte por padding de
timestamps; no se demostró defecto acústico que justificase segmentación destructiva.
Conservar parámetros baseline y Small operativo; ningún perfil se activa o promueve.

Corrección funcional separada: NLP PR40, consumidor PR47. Wheel final0.1.19
SHAac33987da2c045014aeaf773bcce675730797d00e925ef9f07f3082c06dba868,
contrato1.0/RULES_ONLY y huella prf04-rules-money-1. Reproyección final256 salidas:
campos idénticos al candidato intermedio en el corpus; las60 hipótesis pareadas
reducen discrepancias exploratorias de importe3/2/1→3/1/0, sin mejora acústica atribuida.
0.1.18 permanece histórico. Esta rama no arrastra el cambio de wheel operativo.

Expediente privado: métricas literal/v1/numérica, S/D/I/N, matrices, kwargs efectivos,
identidades, recursos, gates, auditorías de privacidad y verificador solo lectura.
Los datos por audio y referencias nunca van a Git/CI. CI y SHA finales en PR48.
Sin merge, despliegue ni ASR-OPT-05/06. Para promoción futura: validar campos críticos,
resolver ámbitos/catálogo y ensayar captura real bajo encargo separado.
