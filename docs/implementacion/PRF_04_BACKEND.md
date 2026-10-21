# HOMEX — PRF-04: especificación técnica backend Django/PostgreSQL

**Estado:** propuesta técnica para revisión; sin implementación. Aplica el contrato `PRF_04_CONTRATO_COMPARTIDO.md` y decisiones funcionales PRF-04.1–04.5 aprobadas.

**Baseline:** `homex-backend/main@0d412f90edabcad41b69620ba783aed6d86c8119`, comprobado 21-10-2026.

## 1. Diagnóstico y riesgos comprobados

1. `apps/capturas/models.py`: `Captura.proforma` es FK obligatoria `PROTECT`, aunque un editor PRF-03 puede no haber guardado aún ninguna proforma. `IntentoCaptura` y `TrabajoOutbox` proporcionan pipeline asíncrono/evidencia.
2. `apps/capturas/services.py`: `_validar_proforma` exige `BORRADOR`, pero el servicio integral `apps/proformas/services.py::_exigir_proforma_editable` admite `BORRADOR` o `EN_REVISION`. La nueva captura debe respetar los **mismos estados que el editor PRF-03** sin relajar aprobadas/bloqueadas.
3. `apps/capturas/pipeline.py`: obtiene moneda mediante `captura.proforma.moneda.codigo` y mapea parte de la propuesta completa a `ItemIA` v1 (aplana componentes). Esto fallará en captura de proforma inexistente y no es suficiente para PRF-03; el `IntentoCaptura.resultado_raw` sí conserva evidencia.
4. `apps/capturas/hitl.py::confirmar_captura` inserta inmediatamente `DetalleProforma`, `EspecificacionMueble`, `ItemHumano` y `EvaluacionNLP`: no puede reutilizarse como acción del nuevo flujo. Debe mantenerse el contrato histórico para consumidores existentes, con **rechazo** de captura de modo asistido en dicho endpoint.
5. `apps/proformas/services.py::crear_proforma_integral` y `actualizar_proforma_integral` ya gestionan transacciones, revisión, idempotencia y escritura de fichas; es allí donde debe incorporarse la vinculación diferida y la comparación humana de capturas asistidas.
6. Migración `capturas.0005` mantiene trigger para crear trabajo outbox y protege intentos terminales e `ItemIA`; migración `0006` protege `ItemHumano` y `EvaluacionNLP`. Nuevas migraciones deben conservar y probar estos invariantes, sin operaciones destructivas sobre históricos.

## 2. Solución recomendada: captura asistida independiente de proforma guardada

Extender `Captura` **aditivamente**, reutilizando sus intentos/worker/outbox/evidencia, no duplicar pipeline:

- `modo_captura` con valor legado por defecto y variante `ASISTIDA_CREACION_MUEBLE`.
- `Captura.proforma` acepta `NULL` **solo** en asistidas con proforma aún inexistente; restricción DB y validación API que proteja el modo legado. Para existentes, FK intacta y permisos reales.
- `sesion_borrador` UUID opcional, obligatorio en asistida, asociado al usuario y a una única sesión local autenticada. No confundir UUID con permiso: validar actor y contexto siempre.
- `moneda_contexto_codigo` (`BOB`/`USD`) conservado para las asistidas sin proforma. Para existentes resolver la moneda real del servidor y verificar coincidencia de contexto.
- `captura_origen_id` auto-FK opcional para reinterpretaciones a partir de texto corregido; solo misma sesión/actor. Nunca alterar los bytes o texto originales de intentos cerrados.
- `proforma_detalle` sigue NULL hasta el guardado integral; rechazar adjuntar una captura a más de una línea.

**Alternativa técnica permitida si resulta menor y se demuestra mediante diff/tests:** entidad separada `CapturaAsistida` que reutilice `IntentoCaptura`, outbox y locks con la misma semántica. No se admite duplicar lógica de procesamiento ni crear una proforma fantasma para soportar audio.

Actualizar migraciones, checks de DB, defaults, fixture históricos, serializers y pruebas. Si una migración de `nullable` afecta restricciones o triggers, demostrar upgrade/rollback sobre datos previos con migración aditiva.

## 3. Contratos HTTP y seguridad

Implementar rutas propuestas de `PRF_04_CONTRATO_COMPARTIDO.md`:

- `POST /api/v1/capturas/asistidas/`: UUID idempotente, sesión UUID, `proforma` opcional, `moneda_codigo`, audio xor texto y `captura_origen` opcional. 202, 400/401/403/404/409/415 según corresponda.
- `GET /api/v1/capturas/asistidas/{id}/`: estado, transcripción original, resultado técnico válido, campos de proyección PRF-03 y pendientes accionables. Sin exponer rutas temporales de audio, datos de otro usuario, stack traces o evidencia interna innecesaria.
- Endpoint histórico `POST /api/v1/capturas/{id}/confirmar/` **no** incorpora asistidas; conserva comportamiento anterior para capturas históricas.

Resolver autenticación y autorización bajo `EsVendedor`, propiedad de actor, proforma/contexto y tipos de captura. Vendedor no accede a capturas de otro; permitir políticas administrativas ya existentes, sin conceder permiso de catálogo general ni transiciones comerciales.

- Estado de proforma existente: `BORRADOR`/`EN_REVISION` comprobados al recibir **y nuevamente al vincular/guardar**; `APROBADA`, `NO_CONCRETADA` y otros bloqueados denegados.
- Nueva proforma: **no se creará** para conseguir FK ni antes de la acción de guardado integral. La captura técnica sí se registra con usuario, idempotencia, sesión y moneda de referencia.
- Política de reintentos consistente con `ejecucion_token` y outbox actual; entrega duplicada no repite procesamiento ni crea otra propuesta. Una captura de distinto contenido no reusa la misma idempotencia.

### Respuesta temporal tipada, sin otro formato comercial

La salida provisional se genera en **servidor** mediante proyección determinista de `IntentoCaptura.resultado_raw` y atributos reales de catálogo; preservar snapshot/versión de proyección en el intento si es necesario para que no cambie entre lecturas. Contiene:

- `estado`, `texto_transcrito_original`, `resultado_ia` y `advertencias` tipados.
- `propuesta_configurador`: `{comercial: {nombre, cantidad, unidad_codigo, precio_unitario, ...}, especificacion: {tipo_mueble, datos_tecnicos, observaciones}, pendientes: [...]}` o `null`.
- Versión de proyección y motor NLP que produjo evidencia. Puede conservar campos comerciales aún **incompletos**: precio unitario ausente queda vacío, nunca sustituido por total inferido.
- `descripcion_original` y spans/candidate refs verificables y trazables. El estado `REQUIRES_REVIEW` indica propuesta revisable, no aprobación comercial.

Evitar exponer el `resultado_raw` íntegro si no es indispensable para UI; backend es fuente de verdad. Un `NO_PROPOSAL`, error, propuesta sin único mueble reconocible o proyección incompatible **no** autoriza reemplazo local.

## 4. Proyector NLP → ficha PRF-03

Añadir módulo dedicado testeable, por ejemplo `apps/capturas/proyeccion_prf03.py`; **no** traducir a JSON textual en Vue. Sus entradas serán `ExtractionResult` de versión soportada y catálogos del backend, y su salida objeto comercial/técnico validado:

- Separar `cantidad` comercial y cantidades de partes, con material/espesor/color/dimensiones por `component_ref`, no por posición.
- Traducir medidas explícitas con unidades separadas; no inventar ejes ni aceptar conversiones no exactas. Dimensiones adicionales bajo `caracteristicas_generales.dimensiones`, sin exigir las 3 principales.
- Resolver tipos/atributos vía lectura de catálogos y sinónimos: match inequívoco o valor local/pendiente según corresponda; prohibir creación automática de entradas globales. Nuevos grupos requieren componentes, UID únicos opacos y límites <=10 / <=40.
- `PRECIO_UNITARIO` nuevo obligatorio **solo al confirmar localmente/agregar línea**, no para producir proyección inicial. Si NLP devuelve `TOTAL_NEGOCIADO`, mantener importe reconocido en evidencia/pendientes, sin derivar precio unitario para guardar.
- Valor no asociado permanece `pendiente`/observaciones; no distribuir globalmente características específicas ni duplicar un herraje como accesorio separado.
- `datos_tecnicos` sin `schema_version`, compatible con `validar_datos_tecnicos`; no insertar campos desconocidos por ignorancia de asignación. Preservar terminología descriptiva útil en campo local cuando el atributo no esté en catálogo.

Los casos gold `expected` revisados del repo NLP deben probar el proyector, con referencias exactas: velador, escritorio con piezas, modular en JUEGO, vitrina multi-material, ambiguos, multiproducto y solo precio total.

## 5. Guardado integral y vínculo de evidencia (T5)

Agregar al `DetalleIntegralSerializer` el campo **opcional y solo escritura** `captura_asistida_id` para **nuevas** líneas `MUEBLE_MEDIDA`. No admitirlo en detalle con `id`, ni en sillas/pisos/otros. Nunca guardarlo dentro de `datos_tecnicos`.

En `apps/proformas/services.py::_sincronizar_detalles`, una vez creado detalle/ficha y **en la misma transacción integral**:

1. Bloquear `Captura`/`IntentoCaptura` necesarios (`select_for_update`) y validar propietario, sesión, modo, estado terminal, unicidad de uso, moneda y pertenencia al contexto/proforma.
2. Revalidar proforma editable, ficha actual y `revision_esperada` mediante la transacción integral existente; permitir nueva proforma aún no creada **solo dentro** de esta operación.
3. Asociar `Captura.proforma` y `proforma_detalle`; registrar **una** corrección final (`ItemHumano` o ampliación aditiva equivalente) con snapshot semántico profundo, asociada a evidencia inmutable; registrar métrica `EvaluacionNLP` versionada, coherente con la ficha completa y no solo con los campos planos antiguos.
4. No recalcular negocio desde resultados IA: validar precios/descuentos/moneda, respetar PostgreSQL como autoridad. No crear Pedido/stock/OT ni aprobar proforma.
5. Cualquier validación fallida debe revertir **toda** la escritura comercial y el vínculo/medición; la captura procesada previa puede seguir en estado técnico final, pero jamás aparecer como línea incorporada.
6. Reintentos de guardado con misma clave/hash de la API existente deben converger sin duplicación, y modificaciones posteriores de ficha se conservan como edición manual, sin reejecutar la captura.

**Punto sensible:** `ItemIA` v1 solo almacena proyección plana y `ItemHumano`/`EvaluacionNLP` son inmutables por triggers. Para medir relaciones complejas, ampliar **aditivamente** snapshot de resultado humano o incorporar registro semántico complementario inmutable; conservar intacta la evidencia antigua. Comparar rutas estructurales y cantidad de correcciones; no llamar F1/precisión NER a la comparación comercial HITL.

## 6. Cancelación, abandono y limpieza

- Cancelar antes de subir audio → ninguna captura creada. Cancelar luego de subir/procesar → captura técnica marcada/desasociada para que ninguna respuesta tardía sea aplicable; nunca guardar detalle. No interrumpir incorrectamente un intento en curso protegido por fencing.
- Mantener borrador local aunque worker/Redis/red fallen. Respuestas tardías ignoradas por frontend mediante identificador de generación; servidor verifica una única vinculación.
- Ejecutar eliminación del audio temporal en éxito y fallo según política y TTL existente; verificar rutas `.part`, copias `.asr-*`, reconciladores y limpieza de huérfanos. Sin backup, media, URL o registro de bytes de audio.
- Definir retención/depuración de capturas técnicas no utilizadas conforme a la política de privacidad vigente, sin inventar duración en esta especificación ni borrar pruebas históricas sin criterio aprobado.

## 7. Matriz de pruebas backend indispensable

**API/autenticación:** 202 audio/texto, 400 formatos/ambos inputs, 401/403 actor, 404 captura ajena, 409 clave con contenido distinto, cambio de actor/moneda/sesión, estados no editables, captura no finalizada, `NO_PROPOSAL`, modo histórico incompatible.

**PostgreSQL/migraciones:** nueva sesión sin proforma, proforma existente `BORRADOR`/`EN_REVISION`, NULL solo asistida, upgrade datos previos, triggers inmutables, outbox única, sin `proforma` fantasma.

**Proyector:** componentes relacionados, cantidades, medidas, JSON validado, atributos local/catálogo, precio total, evidencias pendientes, 10/40, campos ambiguos no adjudicados.

**Guardado:** cero `DetalleProforma`/`EspecificacionMueble` antes del integral; un detalle+ficha+vínculo+corrección+evaluación al guardar, rollback si falla al final, reintento idempotente, un solo uso por captura, no modificar otros ítems, `revision_esperada` 409 conserva borrador frontend.

**Concurrencia/resiliencia:** doble petición simultánea, repetición outbox, worker tardío, caída Redis, fallo NLP/ASR, cancelación en proceso, salida no utilizable, cambio de estado/moneda entre captura y guardado; sin escrituras comerciales prematuras.

**Privacidad:** eliminación audio y temporales, acceso propietario, logs sin voz/credenciales/rutas, actor administrativo limitado.

## 8. Archivos y gates

Posibles archivos a modificar: `apps/capturas/{models,services,pipeline,api/{serializers,views},hitl}.py`, nuevo proyector, migración nueva; `apps/proformas/{services,api/serializers}.py`, `apps/proformas/validacion_tecnica.py` **solo si la compatibilidad exige modificación aditiva**, `docs/openapi.yaml`, tests y fixtures. Mantener API anterior y migraciones históricas intactas; agregar nuevas migraciones.

Verificación: `uv sync --locked --extra dev`, `make check`, `make lint`, `make format`, `make schema` (regenerar/diff OpenAPI), `uv run pytest -ra` PostgreSQL, `uv run pytest -ra -m concurrency` con PostgreSQL, pruebas reales de worker Redis/Celery, `git diff --check`, CI post-merge. Regenerar cliente frontend y comparar contratos.

## 9. Entregables

**T3:** API de captura asistida + sesión sin guardar + proyección, con test de zero commercial writes. **T5:** vínculo íntegro al guardar + comparación final + migración y rollback + concurrencia. **T6:** suite coordinada real y compatibilidad exacta con wheel NLP/frontend.

Cada entrega debe incluir commit/PR, diff, rutas/versiones definitivas, pruebas, evidencias de CI, posibles brechas pendientes y comandos de reproducción; no declarar implantación productiva si falla cualquier gate crítico.
