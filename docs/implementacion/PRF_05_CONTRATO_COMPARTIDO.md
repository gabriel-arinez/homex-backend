# HOMEX — PRF-05: contrato compartido de cliente, condiciones, revisión y emisión

**Estado:** especificación técnica aprobada funcionalmente; no acredita implementación. Alcance PRF-05.1 a PRF-05.5, aprobado el 21-10-2026. Los documentos compañeros son `PRF_05_BACKEND.md` y `PRF_05_FRONTEND.md`.

**Línea base documental inspeccionada:** backend `main@13818154d95b539e26244b83616c893a8cedb8a2`; frontend `main@89a74aa6d1b7e3308e5b6e3265ac18b7e788b078`. Codex debe obtener los HEAD y contratos nuevos antes de tocar código. PRF-04 está en perfeccionamiento paralelo: preservar sus contratos e integrar sobre el código efectivamente presente, no sobre estos SHA históricos.

## 1. Alcance aprobado y límites

- `PRF-05.1`: cliente existente, cliente nuevo y cliente pendiente; buscador con paginación, identificación humana y sugerencias informativas de posibles duplicados que respetan alcance de usuario; cliente nuevo sigue siendo local hasta el guardado integral.
- `PRF-05.2`: título, moneda, adelanto, plazo, validez y observaciones; distribución en cuatro filas y advertencias/certificación de revisión de precios ante cambio de moneda; adelanto referencial **no** es cobro.
- `PRF-05.3`: previsualización integral de solo lectura del **borrador local actual**, con cliente, productos, ficha técnica desplegable, descuentos, desglose monetario y condiciones; navegación directa a editar cada sección.
- `PRF-05.4`: guardar, revisar, confirmar y emitir para revisión. `emitir` mueve `BORRADOR` a `EN_REVISION`; aprobar es posterior y distinto, y en PostgreSQL puede crear pedido/efectos de stock. Emisión **no** envía PDF ni genera pedido.
- `PRF-05.5`: cobertura funcional, API, seguridad, concurrencia, E2E real, accesibilidad, contrato, regresiones y gates CI; no declarar completado sin evidencia.
- No implementar nuevas tablas de pagos, depósitos, descuentos globales, tipo de cambio, expiración automática, envíos por correo/WhatsApp, enlaces públicos, firma, documentos nuevos, aprobación automática ni flujo de pedidos/OT/inventario. PRF-06 conserva gestión y documentos posteriores.
- Conservar reglas comerciales e históricas AP3/AP4/AP5/AP6/PRF-01/02/03/04, sin inferir precios, atributos, cantidades o conversiones. `TOTAL_NEGOCIADO`, `CAJA`, snapshots de clientes y el JSON abierto `datos_tecnicos` no se reinterpretan.

## 2. Autoridad, endpoints y estados

La escritura comercial usa exclusivamente las rutas **existentes**:

- `POST /api/v1/proformas/integral/`: crea cliente nuevo opcional, cabecera, líneas y fichas en una transacción; recibe `clave_idempotencia` UUID y `emitir=false|true`; retorna `Proforma` con estado, revisión, líneas y total calculado en backend.
- `PUT /api/v1/proformas/{id}/integral/`: sincroniza íntegramente proforma editable; exige `revision_esperada` calculada sobre agregado guardado; 400 si falta, 409 si es obsoleta. No reemplazar datos locales automáticamente en 409.
- `GET /api/v1/proformas/{id}/`: lectura autoritativa del agregado, snapshots y campos de revisión.
- `GET /api/v1/clientes/` con búsqueda, filtros, paginación y alcance real; `GET /api/v1/clientes/{id}/` solo para usuario autorizado; se reutiliza para selección y coincidencias, sin directorio global adicional.
- `POST /api/v1/proformas/{id}/enviar/`: transición histórica de `BORRADOR` a `EN_REVISION` desde detalle; mantenerla coherente con el guardado integral, sin convertirla en aprobación ni saltarse validaciones.
- `POST /api/v1/proformas/{id}/aprobar/` y acciones posteriores conservan su comportamiento, separados de PRF-05. No introducir rutas nuevas por conveniencia visual.
- `GET /api/v1/proformas/{id}/documento-pdf/` se mantiene; no convertir la revisión local en PDF ni descargar un archivo automáticamente.

**Transiciones:** nueva sin persistir → `BORRADOR` por guardar; nueva o `BORRADOR` → `EN_REVISION` al emitir correctamente; `EN_REVISION` admite edición actualmente autorizada con `emitir=false`, pero **no** se vuelve a emitir; `APROBADA` y estados no editables respetan reglas históricas. Una llamada `emitir=true` sobre `EN_REVISION` no debe aparentar nueva emisión: impedirla claramente en frontend y rechazarla de forma contractual desde backend (409), manteniendo las actualizaciones permitidas vía `emitir=false`. Aprobación posterior no es etapa de PRF-05.

## 3. Contrato de cliente PRF-05.1

- `cliente` referencia ID visible/autorizado o `null`; `cliente_nuevo` es objeto nuevo o `null`; no aceptar ambos al mismo tiempo. `clienteMode=pendiente` no inventa un cliente ni fuerza registro.
- Empresa: tipo `EMPRESA`, razón social y nombres/apellidos del contacto requeridos por la validación actual. Persona: tipo `PERSONA` y nombres/apellidos. Celular, dirección y observaciones continúan opcionales; no añadir CI, NIT, correo, contactos múltiples ni identidad empresarial obligatoria.
- Selección existente: buscar por nombres, apellidos, empresa, celular (capacidad ya disponible), recuperar páginas siguientes y mostrar un resumen humano distinguible; no presentar solo ID. Cliente inactivo previamente referenciado conserva lectura histórica, pero una selección nueva debe verificar vigencia/propiedad.
- Cliente nuevo permanece en borrador local hasta el guardado integral. El backend lo crea junto a la proforma, nunca durante escritura de campos ni al navegar. Ante error, rollback de cliente y proforma, sin duplicados por reintento.
- Coincidencias de posibles duplicados: recomendaciones no bloqueantes obtenidas exclusivamente de clientes accesibles al actor. No introducir unicidad artificial ni difundir datos ocultos de otro vendedor.
- Alternar origen del cliente conserva otros apartados y previene pérdida silenciosa de lo introducido; no mutar ficha maestra desde el editor.

## 4. Contrato de condiciones PRF-05.2

La disposición responsive es obligatoria en escritorio, y en móvil se apila conservando exactamente el orden:

1. Fila 1: **Título** (ancho completo).
2. Fila 2: **Moneda** a la izquierda y **Adelanto (%)** a la derecha.
3. Fila 3: **Plazo de entrega** a la izquierda y **Validez de oferta (días)** a la derecha.
4. Fila 4: **Observaciones comerciales** multilínea (ancho completo).

Campos preexistentes: `titulo` opcional hasta 250 caracteres; `moneda_codigo` `BOB`/`USD`; `porcentaje_adelanto` decimal opcional de 0 a 100 inclusive, escala 2; `plazo_entrega` texto opcional hasta 100; `validez_oferta` entero opcional mayor o igual a 1; `observaciones` texto opcional y multilineal. No imponer obligatoriedad no pactada ni deducir días de vencimiento.

**Protección de moneda:** no hay cotización cambiaria ni conversión automática de ningún precio/descuento/histórico. Si existen líneas y se cambia moneda, señalar junto a esa fila que los números conservan su magnitud; invalidar la revisión de importes y, mientras esté pendiente, bloquear guardar/emitir y no mostrar total ni adelanto como estimación comercial fiable en la moneda nueva. La confirmación requiere revisión explícita de los precios y descuentos de **todas** las líneas en la moneda seleccionada; no debe bastar una bandera antigua si varía posteriormente moneda, precios/descuentos u otro dato monetario relevante. La certificación debe asociarse al snapshot actual de moneda y líneas (firma/fingerprint local comprobable, no backend nuevo); corregir producto y volver conserva borrador. Para líneas `TOTAL_NEGOCIADO`, no recomponer precio unitario ni convertir importes históricos.

**Adelanto:** debajo del porcentaje, mostrar importe referencial de adelanto solo si hay total local válido, monto positivo o cero según condiciones comerciales, y revisión de moneda completada. Se usa porcentaje aplicado a total estimado, con redondeo exclusivamente ilustrativo y etiqueta expresa «referencial»; jamás registrar pago, descontarlo del total, cambiar estado de cobro ni declararlo monto persistido. Si faltan precios o la moneda está pendiente, ocultar importe o mostrar «Pendiente».

## 5. Contrato de revisión integral PRF-05.3

Sección `Revisar` solo lectura, alimentada por datos **actuales** del editor local; navegar hacia ella no crea número, proforma, cliente, línea ni captura. Contiene:

- Identificación: título, estado real (sin guardar/borrador guardado/en revisión) y moneda.
- Cliente: nombre o razón social, contacto, celular cuando exista, y estado pendiente/nuevo sin persistir; no mostrar ID como nombre.
- Líneas: tipo, nombre, descripción, cantidad y unidad, precio unitario **cuando corresponda**, descuento explícito, total de línea y tratamiento legible de variantes/familias pendientes.
- Ficha técnica de mueble a pedido: disponible en desplegable por línea, con dimensiones y unidades, características generales, grupos, componentes/cantidades internas, materiales, espesores, colores, acabados, accesorios, atributos dinámicos y observaciones; conservar claves desconocidas en estado/payload. Los datos PRF-04 corregidos manualmente se ven del mismo modo; no renderizar JSON crudo.
- Resumen económico: subtotal, descuentos acumulados, total en moneda; solo estimaciones si derivan válidamente de líneas locales (no inventar cero por ausencia). Cuando esté `persisted` y sin cambios, mostrar valores autoritativos recibidos de PostgreSQL; si se editó, distinguir importe guardado previo de estimación nueva. Redondeos monetarios según política existente; no sumar monedas distintas.
- Condiciones: moneda, adelanto %, referencia informativa si calculable, plazo, validez, observaciones, conservando la diferencia entre dato vacío y «a elección».
- Acciones de corrección: volver a Productos, Cliente o Condiciones y enfocar línea cuando sea factible, sin editar datos dentro de la revisión ni perder cambios locales.
- Lista accesible de pendientes de emisión y ubicación para resolverlos. El resumen «Copiar» es texto manual fiel al estado visible, no envío automatizado.

## 6. Contrato de formalización PRF-05.4

- `Guardar borrador` visible durante creación, `Guardar cambios` en proforma persistida editable. Ambas acciones explícitas; navegar/abrir desplegables/modal/revisar no escribe.
- `Emitir proforma` como CTA solo en `Revisar` y solo para creación o `BORRADOR`. En `EN_REVISION` mostrar guardado de cambios según permisos, nunca nueva emisión ni mensaje de «emitida» ante PUT sin transición. Estados finales no se editan con este flujo.
- Antes de emitir: validar cliente, ≥1 línea válida, precio unitario nuevo mayor que 0, unidades/cantidades/descuentos vigentes, validez/adelanto si presentes, coherencia técnica y moneda revisada. Backend/PostgreSQL conservan última palabra. Total emitido debe ser positivo conforme invariantes existentes, sin falsos ceros.
- Modal único de confirmación: identificar cliente, número de líneas y **total estimado** o confirmado según procedencia, estado de destino `EN_REVISION` y explicación de que no crea pedido ni envía documentos. «Volver a revisar» cierra sin escritura, «Confirmar emisión» ejecuta un único guardado integral con `emitir=true`. Sin checkbox adicional.
- Si formulario/cotización cambian después de abrir modal o llega actualización de revisión, invalidar confirmación y pedir revisión fresca, nunca emitir payload distinto del confirmado. Bloquear doble clic/petición pendiente, no alterar UUID para un retry semánticamente igual tras timeout sin conocer resultado.
- Solo tras respuesta exitosa del backend que confirme `EN_REVISION`, mostrar número real y navegar al detalle; no declarar éxito por HTTP genérico con estado distinto. Los 400/403/404/409 y fallo de red preservan trabajo y son explicables, sin falsa emisión.
- Si una emisión pudo haber sido procesada pero no se recibió respuesta, consultar autoridad antes de reintentar; en creación utilizar misma clave/payload para replay; en actualización usar token de revisión para evitar reejecución ciega.

## 7. Pruebas cruzadas y condición de cierre PRF-05.5

- Matriz mínima: cliente existente paginado, empresa/persona, pendiente, cliente ajeno, cliente inactivo histórico, sugerencia duplicado no bloqueante, rollback, replay idempotente, cliente nuevo concurrente, cambios locales al alternar.
- Condiciones: campos vacíos/opcionales, valores extremos e inválidos; cada fila en desktop y orden móvil; moneda con/sin líneas; dos cambios sucesivos BOB/USD; revisión invalidada ante cambio posterior de precio/descuento; total pendiente; adelanto 0/50/100 y total nulo.
- Revisión: productos catálogo/pendientes, muebles PRF-03, propuesta PRF-04 aplicada y modificada, componente por conjunto, atributos desconocidos, descuentos, histórico `TOTAL_NEGOCIADO`/`CAJA`, estado local ≠ guardado, navegación sin writes, copiar resumen.
- Formalización: modal cancelado sin escrituras, estado BORRADOR→EN_REVISION, cliente faltante/importe inválido, pendiente monetario, doble clic, timeout con consulta/retry idempotente, 409 después de cambio externo, editar EN_REVISION con `emitir=false`, rechazar emitir EN_REVISION con `emitir=true`, aprobación distinta sin efectos automáticos.
- Pruebas Vue unitarias/componentes + API Django PostgreSQL real; Playwright end-to-end con API y base reales (no solo mocks), regresiones AP3/AP4/AP5/PRF-01/02/03/04 según integración instalada.
- Accesibilidad: 360, 390, 768, 1024 y 1440 px, claro/oscuro, teclado, foco de modal, mensajes `role=alert`/`status`, sin overflow horizontal, textos extensos. No introducir nuevas librerías sin motivo.
- Ejecución: comparar contratos OpenAPI backend ↔ tipos generados frontend, migraciones `makemigrations --check`, pytest, lint, build, format, Vitest, Playwright, integración PostgreSQL y gates CI; evidencias por requisito y SHA de cada repo.
- Reporte: matriz PRF-05.1–05.5 → cambio → prueba → resultado, commits, PRs, CI, comandos locales exactos, incompatibilidades y brechas. No declarar terminado por compilar ni mientras exista un gate crítico rojo. Documentar fallos ajenos al alcance y resolverlos coordinadamente si bloquean cierre.

## 8. Secuencia recomendada

`T0`: línea base real y compatibilidad PRF-04 / contratos. `T1`: cliente contextual. `T2`: condiciones y protección de moneda. `T3`: revisión integral. `T4`: modal y emisión segura. `T5`: validación real E2E, regresión y CI.

No realizar desarrollo funcional de PRF-06 ni cambiar infraestructura productiva, permisos, estados comerciales o autoridad de PostgreSQL. Si la implementación PRF-04 concurrente modifica estos módulos, integrar sin borrar sus aportes y probar ambos recorridos.
