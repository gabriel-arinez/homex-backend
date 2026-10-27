# Correcciones v14 derivadas de voz real

Base: backend #38, `8fc0f22fa9c58f094e9e8de42c43a1f1007f9d41`.
Consume NLP 0.1.14, fuente NLP #32 / `4dc3f25`, conservando reglas v14,
contrato 1.0, proyección PRF04_2 y todos los wheels históricos.

## Resultado esperado y evidencia

- «Quiero un escritorio de 120 de ancho y 75 centímetros de alto»:
  evidencia NLP ancho=120 sin unidad ni conversión; alto=75 cm. Proyección:
  sólo alto completo y pendiente MISSING_UNIT con resolución DIMENSION/ancho.
- «Necesito un escritorio de melamine a blanca de 120 centímetros de ancho
  con 2 cajones y una etapa de 18 milímetros de espesor»: ancho=120 cm,
  un componente cajones/cantidad_interna=2 sin espesor; 18 mm pendiente
  ESPESOR_SIN_COMPONENTE, sin crear tapa. También probado con melamina.
- El control «tapa de 18 mm y 25 mm» conserva los dos espesores y genera
  CONFLICTING_VALUES, sin elegir uno ni tratar «25 mm» como una entidad.
- La advertencia NLP sobre pieza ausente se convierte en el pendiente
  tipado, sin duplicarla como aviso genérico que no pueda resolver Vue.
- Regresiones de integración: 10 pruebas, incluidas las seis variantes
  120/60/75 cm con melamine/melamina y conservación del resultado original.
- Ruff y formato, Django check y migraciones sin cambios, build,
  OpenAPI sin diferencias y verificador del consumidor frontend: OK.
- Wheel verificado mediante `vendor/homex_nlp-0.1.14.sha256`.

Las pruebas agregadas son replays de texto y controles sintéticos, no
recapturas ni métricas ASR. No se modifican bases de laboratorio, audios,
capturas históricas, corpus o contratos. CI del PR verifica la suite completa,
PostgreSQL/concurrencia, migraciones, worker e integración frontend.
