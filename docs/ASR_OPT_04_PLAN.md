# ASR-OPT-04 — perfiles aislados y preregistro

Base de herramientas: PR46 edd6611, conservado sin cambios. La corrección funcional
está separada en NLP PR40 (0.1.19) y consumidor backend dependiente. Esta rama no
cambia apps/, wheel operativo, frontend ni servicios. La proyección de investigación
permite elegir explícitamente release0.1.18 o0.1.19 con su huella exacta; el modo
histórico sigue siendo0.1.18 por defecto.

Solo Small/Medium/Turbo locales CPU/int8, identidades completas verificadas y un
proceso efímero a la vez. Baseline histórica reutilizada. Cuatro variantes de un
factor: vocabulario genérico hotwords, initial_prompt corto genérico, beam_size3 y
condition_on_previous_textFalse. No números ni frases del corpus en vocabulario.
FW1.2.1 aplica hotwords si no hay prefix; initial_prompt utiliza tokens previos.
Se ensayan separados. No VAD/recortes sin defecto acústico concreto que lo justifique.

Smoke, subconjunto de riesgo y full20 solo si gates pasan. Rechazar regresiones de
importe/modalidad/moneda/cantidad/medida/eje/unidad/negación antes de puntuar WER.
WER/CER literal/v1/numérico v2 fijos; convención es-BO igual para todos. Subconjunto
sin beneficio crítico y peor WER numérico no continúa. Máximo4 factores individuales
y1 combinación por modelo, solo si hay factores favorables compatibles. Sin barrido
combinatorio, cascada, entrenamiento ni ASR-OPT-05/06.

Reserva768MiB, RSS min(3GiB, disponible-reserva), swap del hijo128MiB; timeout por
etapa180/600/1200s. Presupuesto total de inferencia nueva90min; datos/segmentos,
kwargs, hashes, tiempos/CPU/RSS/swap y carga conservados privados. Se preserva la
llamada baseline exacta, el texto emitido y los timestamps completos.

Las20 referencias son conocidas, no holdout; auditoría independiente0 y campos
comerciales confirmados0. Resultados in-sample/exploratorios. Diagnósticos ambiguos
no son aciertos ni autorizan promoción. Solo agregados y fixtures sintéticos públicos.
Preregistro completo con hash y expedientes fuera de Git. Sin merge ni despliegue.
