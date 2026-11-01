# Identidades explícitas de NLP (CORR-PLN-03)

El reconocimiento y la proyección comercial tienen identidades independientes.
`nlp-identities.json` fija cinco artefactos: histórico 0.1.18; candidato
0.1.19 ac19d9f9; cierre previo ac33987d; correctivo mixto intermedio y final 0.1.19, huella
prf04-rules-money-2. El registro fija SHA del wheel y de sus módulos/metadatos.
No basta la versión declarada: se comparan los bytes instalados, METADATA y
WHEEL con el artefacto y se rechazan imports editables o sombreados.

Runner acepta `nlp_identity` y `nlp_wheel` en su solicitud; por defecto conserva
historical-018 y el wheel 0.1.18 del vendor. Las llamadas Whisper y sus kwargs
no cambian. Cada informe nuevo incorpora `nlp_identity`; no se reescriben informes.
La identidad NLP del runtime acústico no implica que se haya proyectado con él.

Projection acepta `--nlp-identity`, `--nlp-wheel`, `--expected-nlp` y
`--expected-port` (55487 histórico o 55491 aislado de esta revisión). Conserva
base prefijada asr_opt_, host loopback y transacción READ ONLY. El adaptador
backend debe corresponder al release; esta rama no cambia la dependencia del
backend ni incorpora PR47. Se prueba la combinación en un worktree temporal.

Assess selecciona identidad comercial con `--nlp-identity`; verifica la identidad
acústica registrada por separado. Matrices nuevas requieren identidad completa.
`--legacy-historical` permite leer informes/matrices históricos 0.1.18 sin campos
nuevos, marcados LEGACY_METADATA_ONLY_NOT_WHEEL_ATTESTED. No atribuye un SHA
comprobado retrospectivamente a metadatos antiguos. Para volver a ejecutar
el histórico con prueba exacta de instalación se usa el wheel historical-018.
El modo oficial de evaluación humana conserva sus restricciones.

`verify.py` y `verify_opt04.py` siguen verificando sus expedientes históricos
sellados (incluida su versión 0.1.18). No son verificadores genéricos de nuevos
experimentos. La revisión actual tiene adenda y manifest propios; no recalcula
las matrices históricas ni su significado. No se requiere nueva inferencia.

Pruebas: `python -m unittest discover -s research/asr_opt/tests -v`.
Los ejemplos locales y las rutas de artefactos están en el cierre privado
HOMEX_CORR_PLN_03_CIERRE_AUDITORIA.md, fuera del repositorio público.

Para el cierre CORR-PLN-03 seleccionar `corrective-019-mixed-final` (SHA9c299ff0).
`corrective-019-mixed` conserva la identidad intermedia67e910a1, sin reasignarla.
