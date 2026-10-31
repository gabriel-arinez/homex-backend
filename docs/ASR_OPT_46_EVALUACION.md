# Cierre correctivo de evaluación — 2026-10-31

Se reutilizan las 60 hipótesis y la matriz histórica de proyección, sin nuevas
inferencias, modelos ni cambios de servicios. Las 20 referencias aportadas tienen
integridad técnica comprobada y declaración de escucha; no acreditan auditoría
acústica independiente. Se mantienen sus atestaciones originales y privacidad.
El modo oficial conserva su gate; `--provisional-declared` permite evaluación
explícitamente provisional, sin transformar borradores comerciales en gold.

## Métricas provisionales microagregadas

| Modelo | WER literal | WER v1 | WER numérico v2 | CER literal | CER v1 | CER numérico v2 |
|---|---:|---:|---:|---:|---:|---:|
| Small | 37.1292% | 30.2392% | 3.2445% | 28.2429% | 27.7686% | 1.2846% |
| Medium | 36.7464% | 28.7081% | 1.2746% | 28.3314% | 27.6179% | 0.9684% |
| Turbo | 35.3110% | 28.4211% | 1.1587% | 28.0660% | 27.6028% | 0.9289% |

No son precisión acústica certificada. Se reproducen exactamente los S/D/I/N
preliminares de las cuatro métricas v1. N palabras v1=1045, caracteres
literales=6784 y normalizados=6637; N palabras v2=863 y caracteres=5060.
Los cambios de denominador impiden interpretar la caída como mejora de ASR.

`numeric.py`, versión `es-context-numeric-v2`, agrega gramática conservadora de
cardinales españoles, miles y decimales explícitos con contexto de moneda,
unidad u objeto. Usa Decimal y la misma convención es-BO en los tres candidatos.
Por ejemplo sintético: «doce mil bolivianos» y «12.000 bolivianos» equivalen
solo con convención monetaria declarada; «uno veinte» queda ambiguo. Separadores
de tres cifras sin convención permanecen ambiguos. Conserva negaciones,
por/cada, modalidad, unidades, ejes y signos. No convierte unidades para WER.
La conversión controlada m/cm/mm se limita al diagnóstico dimensional con mismo
eje y ámbito, conservando unidades originales. No interpreta toda elipsis ni
expresión coloquial. Trazas y alineamientos solo en expediente privado.

## Evaluación comercial

`assess` une reportes runner con `projection.py`: exige IDs únicos/completos,
hash de audio, hash de texto y texto exacto conservado en la salida NLP.
Nunca requiere copiar manualmente `commercial_fields`. Distingue diagnóstico
textual ASR, extracción NLP/proyección y diferencias entre modelos.

Las propuestas comerciales se revisaron mecánicamente contra el texto aportado;
ningún campo recibió aprobación humana nueva. El esquema tipado diferencia
cantidad comercial, cantidad interna/capacidad, importe, moneda, modalidad,
ejes/unidades/ámbitos, espesores, materiales, colores, componentes y negaciones.
Los borradores con comentarios y procedencia por hoja permanecen privados.
Ausencia de anotación no es ausencia física; null no autoriza inventar certeza.

| Discrepancias exploratorias / 20 referencias de texto | Small | Medium | Turbo |
|---|---:|---:|---:|
| Cantidad comercial | 2 | 1 | 0 |
| Importe extraído | 3 | 2 | 1 |
| Moneda extraída | 3 | 1 | 0 |
| Modalidad extraída | 3 | 1 | 0 |
| Número de propuestas | 2 | 1 | 0 |
| Pérdidas críticas de importe con equivalencia textual | 0 | 1 | 1 |

Denominador comercial oficial: **0**, campos confirmados: **0**. Las omisiones
de propuesta también producen omisiones de importe/moneda: no sumar categorías
como errores independientes. Etiquetas de producto y colecciones no homologadas
no prueban error acústico. Componentes/espesores sin alineamiento fiable de ámbito
y negaciones sin representación estructurada son NO_EVALUABLE; diagnósticos
textuales separados no certifican alcance comercial. No hay ganador comercial.

Normalización por tipo: capitalización de etiquetas/nombres y descriptores
conservando símbolos de unidades/monedas; Decimal para campos numéricos; orden
como multiconjunto solo en dimensiones, materiales y colores. No casefold global
sobre códigos/ejes/unidades. Diferencias literales se conservan por separado.

El gate bloquea promoción si el texto reconoce inequívocamente un importe y NLP
lo reduce. Existe una pérdida por factor 1000 en ambos candidatos mayores. No se
clasifica como error acústico ni se corrige automáticamente el importe. El test
público usa un ejemplo sintético diferente; el caso real y sus pruebas son privados.

## Identidad y cobertura

`model-identities.json` fija repos canónicos, revisiones exactas y hashes/tamaños
de pesos y auxiliares conservados. Runner comprueba todos antes de cargar;
auxiliares ausentes, alterados o no auditados fallan. Acquire rechaza otra revisión
hexadecimal antes de conectar red. La comprobación actual offline coincide con
los manifiestos históricos; no se atribuye retroactivamente el nuevo preflight a
corridas anteriores, que comprobaron solo model.bin. Small local no demuestra por
su ruta que fuese un snapshot Git. Se preservan SHA/dirty reales de cada corrida.

F09 conserva su fixture Small fijado y la invocación Base histórica del helper.
Se prueban ambas rutas y el rechazo de hash con dobles sintéticos, sin descargar
ni evaluar Base. Esto no acredita equivalencia acústica entre esos fixtures.
Los candidatos de esta investigación siguen siendo Small/Medium/Turbo.

Pruebas locales: suite backend 428 correctas, más 46 pruebas standalone, pruebas
privadas de regresión, esquemas, lint/formato, wheel, Django/migraciones y OpenAPI.
La CI del HEAD publicado es la autoridad para integración/navegador/worker.
No se repiten los experimentos de navegador documentados; su evidencia histórica
permanece intacta. No se probó micrófono físico en esta intervención.

## Reproducción y decisión

```bash
python3 -m unittest discover -s research/asr_opt/tests -v
python3 -m research.asr_opt.assess CORPUS REFERENCIAS BORRADOR REPORTE MATRIZ SALIDA_PRIVADA_NUEVA
python3 -m research.asr_opt.evaluate CORPUS REFERENCIAS REPORTE SALIDA_PRIVADA_NUEVA --provisional-declared --monetary-convention es-BO
python3 research/asr_opt/verify.py EXPEDIENTE_PRIVADO
```

Ningún comando descarga modelos. Assess solo lee corpus/hipótesis/proyecciones y
escribe una salida privada nueva. Todos los datos privados quedan fuera de Git/CI.
El expediente incluye S/D/I/N, denominadores, atribuciones y manifiestos.

**PRECISIÓN_FINAL_PENDIENTE_VALIDACION_HUMANA.** Small permanece baseline.
Orden únicamente textual provisional: Turbo, Medium, Small. La regresión comercial
impide promocionar Medium/Turbo. Se requiere confirmar/rectificar los borradores y
resolver dudas de ámbito con revisor real, fecha y hash; no repetir 20
transcripciones ni rellenar 120 campos desde cero. La auditoría acústica final y
el gate de micrófono real siguen separados. No ejecutar ASR-OPT-04/06, fusionar ni
desplegar a partir de este cierre.
