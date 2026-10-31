# ASR-OPT-01 — evaluación acústica independiente

Esta investigación parte de backend main a217b610. No cambia NLP 0.1.18, su wheel,
contrato, lock, ASR operativo o PR45. Los WAV/textos/pesos nunca se publican.

`research/asr_opt/evaluation.py`: WER = (S+D+I)/N, CER sobre caracteres incluyendo
espacios. Literal conserva mayúsculas, puntuación y Unicode; palabras separadas
por whitespace. Normalizado aplica NFC y casefold, sustituye puntuación por
espacios excepto separadores entre dígitos y signos de números. No convierte
palabras numéricas ni interpreta `uno veinte`, miles o decimales. Misma
normalización en ambos lados. Conserva originales y alineamientos; empates
Levenshtein prefieren sustitución, luego borrado e inserción. Agregación micro:
suma de errores / suma de unidades de referencia. Referencia vacía produce tasa
null y conteo de inserciones (posibles alucinaciones), nunca división por cero.
Con n=20 no se presume significación estadística ni se promedian WER por audio.

La referencia requiere IDs/hashes exactos, texto literal, atestación de escucha
humana ligada por hash al texto/audio y auditoría explícita de procedencia.
Un booleano o texto generado no acredita gold. Tramos dudosos impiden puntuar el
audio completo: no se puntúa una palabra inventada en lugar de un inaudible.
`field_errors` distingue omisión, sustitución, invención, formato y campos
INDETERMINADO, con denominador de campos evaluables y severidad por campo.
Los valores y contextos (eje, unidad, ámbito) deben anotarse por persona, sin
inferirlos de la hipótesis. Una diferencia ASR/NLP no acredita error acústico.

`corpus.validate_manifest` comprueba 20 IDs y WAV PCM16 mono 16 kHz, tamaño,
rutas, symlinks y SHA256. `prepare_review` crea paquete privado con reproductor y
exportación; jamás publica gold ni abre micrófono. Requiere escuchar, revisar
campos comerciales/dudas y auditar la exportación. Publicación de texto requiere
además revisión de privacidad y autorización expresa, no implícita en la UI.

`runner` carga solo Small/Medium/Turbo desde rutas locales con hash fijado y
modo offline. Transcripción exacta `transcribe(path, language='es')`: defaults
reales se registran (beam=5, fallback temperature, VAD=False, sin prompts/hotwords).
Carga separada, primera inferencia separada de calientes, orden fijo, tiempos por
audio, RTF, segmentos completos, RSS/swap y estado parcial. Un solo subproceso
modelo; supervisor termina exclusivamente su hijo. Política previa: reserva
768 MiB, máximo RSS menor entre 3 GiB y MemAvailable-reserva; abortar si swap del
hijo supera 128 MiB, cae la reserva o vence timeout explícito. No es umbral de
calidad ni estimación universal del modelo. No usar CUDA. No comparar velocidad
causalmente si hubo carga externa o presión de memoria.

Reproducir tests sin Django ni DB:

```bash
python3 -m unittest discover -s research/asr_opt/tests -v
```

Los resultados del corpus privado deben permanecer bajo Descargas. Sin gold,
metodología LISTA y precisión PENDIENTE_GOLD. Ningún ganador por precisión.

Fuentes: [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper),
[JiWER](https://github.com/jitsi/jiwer). Las métricas de esos proyectos no son
métricas de HOMEX. Las APIs/defaults se contrastan con 1.2.1 instalada.

Gate observado: 20/20 hashes/formato válidos, 522,635 s por frames; el total
histórico 522,636 s suma duraciones redondeadas por audio. Small reproduce 20/20
textos históricos exactamente, con código y runtime registrados. No hay gold
humano auditable: el proyecto real anterior no tiene eventos de revisión y la
demo usa hashes de audios sintéticos diferentes. 0/20 referencias verificadas.
WER/CER/errores críticos acústicos pendientes; no se sustituye gold por guiones.
Matriz NLP/PRF04_2 ejecutada en transacción READ ONLY sobre catálogo migrado de
PostgreSQL exclusivo de prueba. `projection.py` rechaza conexiones que no sean la
base asr_opt_* en 127.0.0.1:55487. No crea capturas ni proformas.

Los timestamps son tokens predichos en pasos de 20 ms; la implementación instalada
convierte posiciones de tokens en tiempos y no limita todos los finales al audio
real (ventanas acústicas con padding). No son relojes de muestras ni evidencia
literal de audio posterior al archivo. Se conservan y auditan los excesos; no se
recorta texto ni se cambia duration_seconds=None del contrato congelado.

La comparación semántica elimina texto léxico redundante cuando existe un valor
normalizado tipado (dos/2 conservan cantidad 2), y resuelve IDs pendientes a sus
hechos tipados antes de comparar. Los candidatos originales y spans permanecen
en el JSON privado. Se conservan cambios de valor, unidad, eje, material, grupos
y ámbito. Un campo sin anotación gold es NO_EVALUABLE; solo una ausencia humana
explícita (null) permite clasificar una invención. El CLI `evaluate` emite campos
comerciales únicamente con referencia auditada y anotaciones tipadas compatibles.
Fracciones, separadores numéricos iniciales y porcentajes no se borran durante
normalización. Una referencia vacía necesita confirmación humana de silencio.
Los signos separados de la cifra y decimales iniciales dentro de paréntesis se
conservan también: normalización no equipara `- 2` con `2` ni `(.20)` con `(20)`.
Esta precaución puede retener más puntuación numérica; se prefiere conservar la
ambigüedad a borrar una diferencia comercial. No interpreta valores acústicos.
