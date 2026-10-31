# ASR-OPT-03 — comparación limitada y supervisada

Solo Small, Medium multilingüe y Large-v3 Turbo. CPU/int8, un modelo por proceso
efímero, sin GPU/CUDA ni instalaciones nuevas; no cambia ASR operativo ni PR45.
Sin gold humano no se recomendará un ganador de precisión. Se conserva Small.

Identidades auditadas con API Hugging Face, licencia MIT, CTranslate2 y aliases de
Faster-Whisper 1.2.1 instalada:

| Modelo | Repo canónico | Revisión | SHA256 model.bin |
|---|---|---|---|
| Small | Systran/faster-whisper-small | 536b0662742c02347bc0e980a01041f333bce120 | 3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671 |
| Medium | Systran/faster-whisper-medium | 08e178d48790749d25932bbc082711ddcfdfbc4f | 9b45e1009dcc4ab601eff815b61d80e60ce3fd8c74c1a14f4a282258286b51ae |
| Turbo | dropbox-dash/faster-whisper-large-v3-turbo | 0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf | e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da |

El alias instalado Turbo apunta a mobiuslabsgmbh; ese repo redirige al canónico
Dropbox. No son dos candidatos distintos. `acquire.py` comprueba alias instalado,
repo canónico, commit inmutable, licencia, archivos y hashes; solo descarga con
--download explícito dentro de Descargas. `runner` nunca descarga y rechaza pesos
fuera de estas identidades. Small local se compara con metadata/hash upstream;
no se afirma que su ruta local fuese un snapshot Git si no existe ese metadato.

Secuencia pre-registrada por candidato: 1 audio (01, timeout 180 s), después
01/03/20 (300 s), después 20 (900 s) únicamente si los gates de recursos pasan.
No hay modelos simultáneos. Supervisión de RSS, swap y MemAvailable cada 250 ms;
política de reserva y abortos en ASR_OPT_01_METODOLOGIA. Los resultados parciales
se conservan. Un fallo de recursos no es error de reconocimiento ni precisión.

Mismos WAV y orden para las baterías de 20, misma llamada española baseline y
mismos defaults de transcripción registrados por introspección: beam_size=5,
best_of=5, temperature=[0,.2,.4,.6,.8,1], condition_on_previous_text=True,
vad_filter=False, initial_prompt=None y hotwords=None. cpu_threads=0 (default
de constructor), num_workers=1; variables de hilos y CPU se registran. No se
hace tuning de ASR-OPT-04. Carga, primera inferencia, calientes, total, RTF,
p50/p95, RSS/swap y contexto de carga externa se separan. Caché de disco/térmica
no controlada; no se atribuyen causalmente diferencias pequeñas de velocidad.

Texto exacto, segmentos y hashes privados; paso por NLP0.1.18/proyección en DB
exclusiva READ ONLY. Cantidades/precios/unidades/negaciones se comparan por campo,
sin contar palabras numéricas como errores comerciales ni inventar gold. Atril
no es tipo activo del catálogo migrado. Fronteras de frase pueden alterar alcance
de negación y extracción de precio: audios03/20 requieren escucha, no cambio NLP.
No se crea corpus complementario de silencio sin justificación; señales Web Audio
sintéticas de la sonda son solo pruebas de API, no pruebas de no alucinación.

La espera asistida existente es 120 s; se reporta viabilidad respecto de ella,
pero no se cambia UI ni se promueve un modelo por esta investigación.

Fuentes primarias: [aliases v1.2.1](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/utils.py),
[Medium](https://huggingface.co/Systran/faster-whisper-medium),
[Turbo](https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo),
[Whisper](https://github.com/openai/whisper/blob/main/README.md).
