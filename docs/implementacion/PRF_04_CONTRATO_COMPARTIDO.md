# HOMEX — PRF-04: contrato compartido NLP / backend / frontend

**Estado:** propuesta técnica para revisión; **PRF-04.1–PRF-04.5 aprobadas funcionalmente**. Este documento NO acredita implementación.

**Referencias `main` comprobadas el 21-10-2026:** NLP `dbfc80a3d2c6628fc5051658e5fd8d34668ce921`, backend `0d412f90edabcad41b69620ba783aed6d86c8119`, frontend `5bfc772df0aa2430d909b87fbcb22e6bde03461b`, deploy `d525a4c4a086259864f17dcd534ee18e8da91b3b`.

## 1. Invariantes funcionales aprobadas

1. Voz **opcional** solo al **crear una línea nueva** de `MUEBLE_MEDIDA`; disponible tanto en proforma nueva aún sin guardar como en proforma existente editable. No habilitar dictado para editar la línea de un mueble ya incorporado; esa edición es manual.
2. Un dictado = **un único mueble comercial**, aun si contiene componentes. Dictados de productos comerciales múltiples se rechazan sin añadir líneas; cantidad comercial y `cantidad_interna` no se confunden.
3. El micrófono permanece visible en el configurador durante la creación. Cuando hay cambios reales, un único modal explica que una nueva captura **reemplazará toda la información del mueble**. Cancelar conserva todo. Si no hay cambios, no hay modal.
4. La captura nunca mezcla valores antiguos con los nuevos: reemplazo **total y atómico** solo al terminar exitosamente y recibir propuesta utilizable de un único mueble. Cancelación, falta de propuesta, error ASR/NLP, desconexión o respuesta obsoleta preservan íntegramente el mueble previo.
5. El **mismo configurador PRF-03** muestra los datos autocompletados y permite correcciones. La transcripción original aparece en un bloque compacto desplegable; puede corregirse el texto y solicitar nueva interpretación manteniendo el original inmutable. **No** crear una segunda pantalla de aceptación, campos JSON ni confirmaciones campo por campo.
6. **No mostrar porcentajes/confianza.** Avisos discretos únicamente ante problemas **concretos, verificables y accionables**; un dato reconocido y colocado coherentemente no requiere confirmación. Lo opcional no dictado queda vacío sin alarma.
7. «Agregar mueble a la proforma» solo añade al **borrador local**. Ni dictar ni autocompletar ni agregar realizan `POST/PUT` comercial. La persistencia ocurre únicamente con la acción expresa «Guardar borrador»/«Emitir proforma», por los endpoints integrales PRF-03.
8. No inventar medidas, ejes, unidades, materiales, componentes, colores, precios ni vínculos; conservar información dudosa en `pendientes`/observaciones. No convertir accesorios en SKU, nuevos ítems, precios o stock.
9. Respetar `PIEZA`/`JUEGO`, `PRECIO_UNITARIO` > 0 en línea comercial nueva, moneda de proforma, descuento monetario total, límite 10 conjuntos/40 componentes, tipologías/atributos dinámicos, propietario, permisos, estados, idempotencia, revisión concurrente e integridad histórica.
10. Conservar evidencia original, versión de ASR, motor y versión de reglas/modelo, corrección humana y comparación. **Audio temporal**, nunca histórico, con limpieza comprobable.
11. Cuatro corpus nuevos (muebles, sillas, pisos y otros) como fuentes **activas únicas** para evolución; retirar antiguos y todas sus referencias después de verificar incorporación de información real valiosa y de sustituir tests/manifiestos. Priorizar entrenamiento e integración funcional de muebles.

## 2. Fronteras entre formatos

**No confundir tres estructuras**:

- **NLP:** `ExtractionResult` Pydantic, `schema_version` propio, `status`, `item_proposal` singular, candidatos, referencias a evidencia y advertencias. Puede operar como `RULES_ONLY` o, tras evaluación/promoción, `HYBRID`.
- **Proyección temporal de propuesta:** objeto tipado, validado y versionado internamente para presentar un mueble nuevo en el configurador. Contiene separación `comercial` / `especificacion` / `pendientes`; se calcula en servidor a partir de evidencia NLP, sin convertirse en línea comercial. Nunca confiar en proyecciones enviadas de vuelta por el navegador como originales de IA.
- **Dominio PRF-03:** línea `DetalleIntegralWritable` + ficha `EspecificacionMuebleWritable`, `datos_tecnicos` de estructura aditiva (`caracteristicas_generales`, `conjuntos`, `componentes`, `accesorios`, `advertencias`, `descripcion_original`). **Está prohibida** la clave `schema_version` dentro de `datos_tecnicos`; el versionado técnico queda fuera de esa ficha.

**Separación de autoridad:** NLP propone; backend valida/autentica, es dueño de la evidencia y escritura; frontend edita un borrador local; PostgreSQL autoriza la operación integral.

## 3. Contrato HTTP propuesto, explícito y separado del HITL antiguo

Se propone añadir rutas bajo `/api/v1/capturas/asistidas/`, manteniendo intacta la semántica de `/api/v1/capturas/` y `/api/v1/capturas/{id}/confirmar/` preexistentes.

### 3.1 `POST /api/v1/capturas/asistidas/` — 202

`multipart/form-data` para audio o `application/json` para texto. Campos propuestos:

- `clave_idempotencia`: UUID único por entrada real.
- `sesion_borrador`: UUID generado al abrir el editor de la proforma (permanece estable en ese borrador; autenticación/ownership siempre verificados en servidor).
- `proforma`: entero **opcional**: solo si la proforma ya existe. Su estado permitido debe coincidir con el guardado integral de PRF-03 (`BORRADOR` o `EN_REVISION`) y su propietario/moneda se verifican en servidor.
- `moneda_codigo`: `BOB` o `USD`, necesaria para una proforma no guardada; si se proporciona con una existente debe coincidir con la moneda real. Nunca convertir moneda implícitamente.
- **exactamente uno**: `audio` o `texto`. No admitir `proforma_detalle`: el dictado sirve solo a una línea nueva.
- `captura_origen`: ID opcional de otra captura asistida de la misma sesión/actor para reinterpretar un texto corregido; nunca reescribe el ASR ni el `resultado_raw` anteriores.

Respuesta conserva `{id, estado, intento_id, numero_intento, reutilizada}` y los errores autorizados 400/401/403/404/409/415. El servidor crea evidencia técnica de captura, **no** proforma ni detalle.

### 3.2 `GET /api/v1/capturas/asistidas/{id}/` — 200

Devuelve estado de procesamiento, identificadores de intento/captura, `texto_transcrito_original`, `resultado` (`REQUIRES_REVIEW`, `NO_PROPOSAL`, `ERROR` o `PROCESSING` según corresponda), **propuesta temporal validada** o `null`, `pendientes` accionables, metadatos de versión/errores seguros y referencia auditable a la evidencia original.

Solo una propuesta que identifique **un único mueble nuevo** podrá sustituir el formulario. Nombre faltante, propuesta nula, fallo de validación/proyección o multiproducto **no** sustituyen el estado local. Campos opcionales, cantidad o precio ausentes pueden quedar sin llenar para corrección manual posterior. No transmitir rutas de audio ni secretos.

### 3.3 `POST/PUT /api/v1/proformas/[{id}/]integral/` — existente, ampliación aditiva

Cada elemento de `detalles` que se está creando desde asistencia podrá incluir `captura_asistida_id` (entero **opcional**, metadato de asociación, **no** parte de `datos_tecnicos`). No se aceptará en líneas preexistentes ni en ítems de catálogo. Durante la **misma transacción** que crea el detalle y su ficha, backend verifica que captura: pertenece al actor; corresponde a la misma sesión/contexto/proforma; terminó correctamente; produjo propuesta válida; no ha sido incorporada antes; tiene moneda compatible; fue usada solo para una línea nueva. El servidor registra corrección humana y asociación `Captura.proforma_detalle` **solo al guardado integral exitoso**.

Las líneas manuales no llevan `captura_asistida_id`; las capturas descartadas no lo llevan nunca. Repetición idempotente del guardado integral no crea registros nuevos. Preservar `revision_esperada` y hash/idempotencia del endpoint existente.

**Contratos a concretar con OpenAPI antes de programar clientes:** DTO de proyección y advertencia, nuevas rutas y errores; añadir pruebas positivas y negativas. No crear endpoints para guardar cada cambio ni un `/confirmar/` intermedio.

## 4. Mapeo normativo de propuesta → PRF-03

| Origen NLP | Destino comercial/técnico | Regla obligatoria |
| --- | --- | --- |
| Nombre y tipo candidato | `detalle.nombre`, `especificacion.tipo_mueble` | Tipo: buscar catálogo autorizado; sin match inequívoco, dejar sin seleccionar y conservar término. No dar de alta tipo automático. |
| Cantidad principal | `detalle.cantidad` | Positivo, entero y referido al **mueble comercial**. |
| Unidad comercial | `detalle.unidad` | Solo `PIEZA`/`JUEGO` según evidencia y reglas PRF-03; no inferir `JUEGO` por la sola presencia de componentes. Si no consta, mantener selección editable inicial diferenciada de un valor detectado. |
| Precio unitario explícito | `detalle.precio_unitario` | Decimal exacto y moneda de proforma. No convertir `TOTAL_NEGOCIADO` a unitario silenciosamente. Si falta: campo vacío, vendedor lo completa antes de incorporar. |
| Descuento | `detalle.descuento` | Conservar solo valor dictado inequívoco; valor inicial UI permitido `0.00` no debe presentarse como extracción IA. |
| Dimensión con eje/unidad claros | `datos_tecnicos.caracteristicas_generales.dimensiones[clave]` | `{valor, unidad}` compatibles. No inferir eje de `140×140`, unidad de `60,50`, ni redondear para aparentar precisión. |
| Color/material general | Características generales | No propagar implícitamente a todos los componentes. |
| Grupo identificado | `datos_tecnicos.conjuntos[]` | UID opaco nuevo, máximo 10, no crear grupo vacío. |
| Componente identificado | `datos_tecnicos.componentes[]` | UID opaco único, nombre, vínculo opcional `conjunto_uid`, cantidad interna solo si está asociada, máximo 40. |
| Material/espesor/color de pieza | Campos básicos del componente respectivo | Requiere evidencia de asociación, no orden arbitrario. |
| Atributo técnico | `atributos[]` del mueble/componente | Resolver sinónimos con catálogo; preservar `codigo` y `nombre` snapshot. Si no existe, permitir atributo personalizado local sin alta global. |
| Accesorio independiente | `datos_tecnicos.accesorios[]` | String con cantidad contextual si corresponde; no duplicar en atributo del componente ni crear otra línea. |
| Dato ambiguo/no vinculado | `pendientes` de asistencia y, cuando corresponda, `advertencias`/`observaciones` en ficha | Un aviso concreto y accionable. Se permite continuar con información técnica opcional pendiente. |
| Transcripción | Evidencia `Captura`/`IntentoCaptura`; `descripcion_original` cuando corresponda | No sustituir texto original por corrección, no persistir audio. |

**Advertencias:** no hay score por campo. Eliminar avisos de UI cuando la corrección resuelve el problema. Un valor reconocido normalmente no exige confirmación.

## 5. Estados y transiciones

`IDLE` → `CONFIRM_REPLACE` **solo si borrador modificado** → `RECORDING` → `PROCESSING` → `READY_PROPOSAL` → **sustitución atómica del objeto del nuevo mueble** → `EDITING` → `ADDED_LOCALLY` → `SAVED_INTEGRAL`.

Ramas de error/cancelación/`NO_PROPOSAL`: conservar estado y datos previos; la respuesta tardía de una generación reemplazada no puede aplicarse. Si el usuario descarta la propuesta después de procesar, tampoco existe escritura comercial. La captura técnica puede permanecer como evidencia autorizada, nunca audio persistente.

El botón de voz se muestra **solo** para el objeto de nueva línea; editar una línea ya agregada (aunque aún no guardada comercialmente) se hace manualmente, conforme a PRF-04.1. Duplicar una línea prepara una nueva línea comercial, pero no habilitar edición por voz de su original. Si se habilita voz para la nueva copia, se aplican exactamente las mismas reglas de reemplazo integral y confirmación.

## 6. Ejemplos de aceptación de dominio

1. «Seis veladores de dos cajones, 45 ancho, 45 profundo, 60 alto centímetros, melamina de 18 milímetros, rieles telescópicos, 750 bolivianos por unidad»: **6** PIEZAS comerciales y **2** cajones internos; no se crean seis ni dos detalles independientes.
2. «Escritorio en L de dos alas 140 por 140, tapa MDP 25 mm, panel frontal 18 mm, estructura metálica epoxi»: preservar lados ambiguos sin imponer ancho/profundidad; no cruzar espesores por componente.
3. «Un juego de sillones con dos módulos laterales, dos centrales y seis almohadones»: **1 JUEGO** y cantidades de componentes/accesorios, no 11 líneas comerciales.
4. «43 cm de ancho»: completar sin aviso; «43 de ancho» sin unidad: conservar dato sin unidad inventada y presentar problema concreto.
5. «Tres escritorios, total 100 bolivianos»: si solo se dictó **total**, no autogenerar precio unitario; dejarlo para el vendedor.
6. «Dos escritorios y tres veladores»: `NO_PROPOSAL` para captura singular y ningún reemplazo de formulario.

## 7. Gates coordinados para integrar

- JSON NLP y versión compatibles, schema snapshots y evidencia original inmutable.
- DTO servidor de proyección validado, OpenAPI publicado, cliente TS regenerado, tests de compatibilidad strict.
- Pruebas Django/PostgreSQL del enlace en la transacción integral; cero líneas al capturar/agregar localmente; 400/403/409 de contratos y permisos; cierre atómico.
- Tests Vue/Vitest de sustitución total, re-key del formulario, modal, fallos y respuestas antiguas.
- E2E navegador + PostgreSQL + Redis/Celery + ASR real sobre audio de prueba + NLP empaquetado; mediciones WER/NER/JSON/correcciones separadas (sin falsificar evidencia de calidad productiva).
- Revalidación en ambos sentidos de commits **finales integrados** (`nlp → backend`, `backend → frontend`) y CI de `main` post-merge.

## 8. Secuencia de entregas verificables

**T0: Contratos compartidos** → **T1: corpus y referencias de salida** → **T2: NLP mejorado/híbrido evaluado** → **T3: backend de capturas asistidas + proyección** → **T4: integración frontend sin escrituras** → **T5: vínculo/medición atómicos al guardado integral** → **T6: QA E2E/CI/performance/post-merge**. Cada entrega con pruebas y diffs propios. El candidato híbrido no bloquea el resto del recorrido si no pasa los gates: se conserva `RULES_ONLY` mejorado.

## 9. Exclusiones y restricciones

No incorporar voz para sillas/pisos/otros; no modificar edición de muebles existentes; no alterar permisos generales de catálogos; no crear SKU, stock, OT, pedidos ni aprobaciones desde NLP; no respaldar audio; no generar números de confianza en UI; no usar un LLM externo como dependencia obligatoria; no guardar una proforma automáticamente; no asumir rendimiento de NER/ASR no medido.
