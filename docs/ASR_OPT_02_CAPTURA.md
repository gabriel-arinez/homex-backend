# ASR-OPT-02 — captura y acondicionamiento

Se conserva frontend main 302b00e3 intacto. El grabador pide audio:true, escoge
WebM/Opus, Ogg/Opus y WebM por isTypeSupported y no fija bitrate ni restricciones
DSP. Se auditaron permisos/errores/cancelación/tracks, tipo MIME y extensión en
asistidasService y capturasService, y captura asistida. La espera de resultados
asistidos es 120 segundos con polling cada 750 ms; upload legado tiene timeout
30 s. No confundir estos tiempos con un umbral de calidad de ASR.

La cancelación durante getUserMedia pendiente y reinicios solapados merecen un
gate futuro de lifecycle; esta investigación no altera el grabador ni afirma
que pedir constraints garantiza aplicarlas. Se preservan límites/temporales,
fallback de texto, permisos y generación de captura del código actual.

Pre-registro offline: 20 WAV originales contra WebM/Opus 64k. Para IDs de riesgo
01/03/20: WebM/Opus 128k (solo bitrate), Ogg/Opus 64k (solo contenedor), ganancia
-6dB, highpass 80Hz, denoise afftdn nf=-25 y remuestreo a 48kHz, cada uno separado.
No se concatenan filtros ni recortan silencios/palabras. Derivados nuevos con
comandos FFmpeg exactos, hashes, tamaño y duración decodificada comprobada.
Opus requiere remuestreo a 48kHz; Whisper decodifica a 16kHz. La comparación es
pareada por señal original, no por tomas humanas diferentes. La inferencia Small
conserva la llamada baseline, un solo modelo a la vez, sin ajustar beam/VAD.

Se miden RMS/pico dBFS, clipping, DC, fracción de muestras bajo -60dB (no es VAD ni
SNR), duración, bytes y diferencias de texto/proyección; sin gold no son mejoras
acústicas certificadas. No se selecciona filtro por acercarse a un guion.

`browser_probe.mjs` consulta supportedConstraints en Chromium/Firefox/WebKit y
getCapabilities/getSettings de un track Web Audio sintético. Prueba formatos y
bitrate efectivo de MediaRecorder sin llamar getUserMedia ni abrir micrófono.
No son propiedades de micrófono: el gate de captura real queda PENDIENTE. La UI
privada se inspecciona en los navegadores disponibles. No se publican grabaciones.

Reproducción: instalar runtime de evaluación ya disponible, generar derivados con
`python -m research.asr_opt.audio corpus.json /ruta/privada/nueva`; crear un request
runner por preset y ejecutar secuencialmente. Publicar solo resultados agregados.

Fuentes: [constraints soportadas](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getSupportedConstraints),
[settings efectivos](https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrack/getSettings),
[MediaRecorder](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder/MediaRecorder).
Sin muestra real controlada ni gold auditado, no cambiar defaults frontend.

Resultado técnico: se ejecutaron 38 derivados (20 WebM64 y tres por cada uno de
los otros seis presets), con Small y proyección congelada, conservando los 20
originales. Las diferencias de texto/campos son exploratorias; no se autoriza
ningún filtro, bitrate o constraint como mejora de precisión sin gold.
Chromium y Firefox completaron captura sintética y 20 secciones de revisión;
WebKit arrancó, pero MediaRecorder no está disponible en ese contexto headless:
se comprobó su fallback sin solicitar micrófono. En Chromium/Firefox el bitrate
informado fue 128000; Ogg/Opus se admitió en Firefox y no en Chromium. No extrapolar
a navegadores/dispositivos del usuario. La primera sonda asumía MediaRecorder:
se corrigió para registrar ausencia de API sin confundirla con fallo de arranque.
