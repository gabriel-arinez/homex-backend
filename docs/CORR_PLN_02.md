# CORR-PLN-02 — consumidor del parche monetario NLP0.1.19

Dependencia upstream: homex-nlp PR40, commit388d012. La corrección funcional está
en el lector monetario del wheel; backend no sustituye texto, valores ni offsets.
Acepta exactamente0.1.19, RULES_ONLY y contrato1.0. Reglas prf04-rules-money-1.
Wheel nuevo vendorizado con SHA256
ac19d9f93959977c58570c2cf02ecec2d615ecd1e450bae177aab796f6361b7c.
El wheel0.1.18 y su manifiesto se conservan históricos. Lock y verificadores fijan
el artefacto nuevo; no se omite ninguna validación contractual.

Prueba sintética API→outbox→pipeline→NLP→PRF04_2→GET compara representaciones de
una escala monetaria explícita frente al importe sin escala. Comprueba cantidad,
moneda, modalidad, dimensiones, texto/spans, replay idempotente y ausencia de
persistencia comercial automática. Corpus y transcripciones privadas no se publican.
La suite completa mantiene permisos, revisiones, contratos y seguridad existentes.

F09 usa el mismo fixture Small fijado del PR46 mediante flag explícito. No se
investiga ni descarga Base. Esa prueba de integración no compara precisión ASR.
No se incorpora el cache PR45: compatibilidad se verifica por separado, sin
arrastrar commits ni configurar workers operativos.

Orden futuro: integrar primero el release NLP40, después este consumidor. Las
herramientas ASR-OPT-04 van en PR de investigación separado sobre PR46. Las
comparaciones históricas NLP0.1.18 no se sustituyen: expediente nuevo pareado con
las mismas60 hipótesis. Sin merge, despliegue, migraciones operativas ni ASR-OPT-06.
