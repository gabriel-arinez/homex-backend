# HOMEX — PRF-05: especificación técnica backend Django/PostgreSQL

**Estado:** requisitos PRF-05.1–05.5 aprobados; documento de implementación, no evidencia de código terminado. Norma transversal `PRF_05_CONTRATO_COMPARTIDO.md` (copia idéntica en backend y frontend).

**Baseline inspeccionada:** `main@13818154d95b539e26244b83616c893a8cedb8a2`, 21-10-2026. Hay implementación PRF-04 en curso por otro proceso; obtener HEAD actualizado, cambios abiertos/PRs y contratos antes de programar, fusionando sin perder PRF-04.

## 1. Diagnóstico real comprobado

- `apps/proformas/api/serializers.py::ProformaIntegralSerializer` acepta `cliente` o `cliente_nuevo`, `emitir`, `revision_esperada`, cabecera, moneda y líneas; validación de emisión exige cliente y líneas. `validez_oferta` entero >=1; `porcentaje_adelanto` decimal 0..100; `moneda_codigo` BOB/USD. Son opcionales salvo moneda. No crear campos nuevos sin evidencia.
- `apps/proformas/services.py::_crear_proforma_integral` crea cliente, cabecera y detalles en una transacción y transiciona mediante `enviar_proforma` si `emitir=true`. `crear_proforma_integral` protege replay con UUID y hash de payload; la numeración se asigna únicamente al persistir.
- `apps/proformas/services.py::actualizar_proforma_integral` utiliza `_proforma_bloqueada` y `revision_proforma` para comparar el agregado; permite cambios en `BORRADOR` y `EN_REVISION`; actualiza cliente/moneda/detalles y valida contenido emitido. Actualmente, `emitir=true` sobre `EN_REVISION` no ejecuta una nueva transición pero no la rechaza, permitiendo éxito aparente en UI: cerrar brecha con rechazo explícito y prueba. `emitir=false` debe seguir permitiendo edición vigente de `EN_REVISION`.
- `enviar_proforma` acepta solo `BORRADOR` y cambia a `EN_REVISION`. La vista de detalle usa el endpoint histórico `/enviar/`; comprobar que comparte todos los invariantes con la emisión integral y que una carrera/estado inválido nunca deja revisión inconsistente.
- `apps/clientes/api/views.py::ClienteViewSet` tiene búsqueda sobre nombres, apellidos, empresa, celular; filtros `activo`/`tipo_cliente`, paginación y aislamiento por creador salvo roles autorizados. `apps/clientes/validacion.py` exige nombres/apellidos; empresa añade razón social. `apps/clientes/services.py` tiene revisión/soft delete.
- `apps/proformas/api/serializers.py::ProformaSerializer` publica `cliente_resumen` con snapshot histórico; `apps/proformas/revision.py` calcula huella sobre cabecera, líneas y fichas. No sustituir el snapshot por datos actuales del catálogo/cliente.
- `apps/pedidos/services.py::aprobar_proforma` dispara cambio a `APROBADA`, pedido y efectos delegados a PostgreSQL; nunca llamar desde PRF-05 al emitir. `apps/documentos/pdf.py` ya incluye plazo, validez, adelanto y observaciones si existen; no modificar su lógica por un cambio de formulario.
- Cobertura base: `tests/api/test_ap3_proformas_integrales.py`, `test_ap3_auditoria_regresiones.py`, `test_ap4_clientes.py`, `test_ap4_auditoria_regresiones.py`, `test_fe04_contrato_proformas.py`, `tests/integration/test_ap3_concurrencia.py`, `test_ap4_integridad_clientes.py`, `tests/api/test_prf03_configurador.py`.

## 2. Política obligatoria de intervención

El grueso de PRF-05 es visual y de orquestación **frontend**. Clasificar cada necesidad como (A) resuelta por API vigente, (B) representación frontend, (C) brecha reproducible de backend. Solo (C) habilita cambio funcional de backend, con una prueba de fallo previa; no añadir migrations ni endpoints por inercia. Preservar APIs legacy y contratos OpenAPI, reglas PostgreSQL de descuentos/redondeos/estado/stock, aislamiento entre vendedores y esquema `datos_tecnicos` único y abierto.

Antes de aplicar cambios, identificar si PRF-04 ya incorporó `captura_asistida_id`, nueva proyección, vínculo de evidencia o modificaciones a la sincronización integral. Toda extensión PRF-05 debe mantener esos campos y efectos intactos. No reescribir serializers o servicios desde una línea base anterior si hay cambios concurrentes.

## 3. PRF-05.1 — Cliente integrado

- Reutilizar `GET /api/v1/clientes/`, paginación y `search`; no ofrecer una API global de coincidencias, no filtrar después de recibir datos ajenos. Si hace falta un refinamiento de búsqueda, medir y demostrar brecha sin debilitar autorización.
- Personas `PERSONA`: nombres y apellidos. Empresas `EMPRESA`: razón social, nombres y apellidos del contacto. Celular, dirección y observaciones permanecen opcionales. Tipo válido activo en nueva alta; el tipo de cliente existente no se modifica con la cotización.
- El campo `cliente` identifica un cliente vigente y autorizado; `cliente_nuevo` representa creación transaccional diferida. Ambos simultáneamente → error de validación. Un borrador sin cliente es válido si sus líneas cumplen reglas; emisión sin cliente debe fallar antes de cualquier efecto.
- El cliente nuevo se crea **dentro de** transacción integral existente. Si falla alguna línea, ficha, condición o transición, se revierte también el cliente nuevo; replay idéntico con `clave_idempotencia` no lo duplica. El snapshot del cliente se conserva al emitirse y no se altera por su posterior modificación o desactivación.
- Las sugerencias de duplicados serán informativas en Vue usando resultados visibles; backend no impondrá unicidad de nombre/empresa/celular ni registrará cliente mientras el usuario escribe. Comprobar que 404/403 no filtran existencia de cliente de otro vendedor.
- No introducir campos obligatorios de CI, NIT, correo, teléfonos adicionales ni métodos KYC.

## 4. PRF-05.2 — Condiciones comerciales y moneda

Persistir sin cambiar nombres ni precisión existentes:

- `titulo`: `CharField` opcional <=250.
- `moneda_codigo`: BOB/USD; referencia real `ValorCatalogo MONEDA`.
- `porcentaje_adelanto`: `Decimal(5,2)` opcional 0..100 inclusive; cero explícito válido, nulo distinto de cero. No ejecutar cobro ni descontar anticipo del total.
- `plazo_entrega`: texto libre opcional <=100, «días hábiles» u otras condiciones sin parsing automático.
- `validez_oferta`: entero positivo opcional; no calcular fecha de vencimiento ni introducir procesos automáticos.
- `observaciones`: texto opcional, persiste multilínea sin truncamiento artificial.
- La distribución visual (título; moneda+adelanto; plazo+validez; observaciones) corresponde al frontend; no reordenar columnas del modelo.

**Moneda:** PostgreSQL mantiene importes almacenados en la moneda elegida y **no** proporciona conversión automática. La advertencia y revisión de precios/descuentos mediante fingerprint local es de Vue; backend valida códigos y datos monetarios recibidos. No agregar tipo de cambio, autoconversión, modificación retrospectiva de `TOTAL_NEGOCIADO` o `CAJA` ni endpoint de «validar moneda revisada». Asegurar que la API continúe calculando únicamente sobre los valores declarados, sin reinterpretarlos como conversión.

**Estimación del adelanto:** UI derivada del total fiable y porcentaje actual, estrictamente referencial. No persiste `monto_adelanto` ni crea pago. No mover autoridad monetaria del backend a JavaScript. Conservar subtotal, descuento total, total y modo histórico según PostgreSQL.

## 5. PRF-05.3 — Fuente de verdad para revisión

No crear endpoint especial de previsualización de borrador. La revisión previa al primer guardado usa objeto local Vue; la revisión de proforma guardada usa datos locales modificados y referencia a `GET` persistido, distinguiendo lo estimado de lo real.

Comprobar que la respuesta `ProformaSerializer` y los tipos OpenAPI vigentes ofrecen: cabecera, cliente resumido y snapshots históricos, estado, moneda, revisión, detalles con unidad/tipo y precios, descuentos, total, `especificacion.datos_tecnicos` completo y observaciones. No ocultar ni eliminar claves JSON no reconocidas al serializar; preservar cantidades comerciales independientes de `cantidad_interna` técnica.

Si falta un dato imprescindible que ya existe en DB, añadirlo de modo compatible, con test de contrato y regeneración OpenAPI. No copiar un snapshot comercial a partir de la ficha maestra actual; una variante pendiente no reserva stock. No crear PDF o documento nuevo para `Revisar`.

## 6. PRF-05.4 — Emisión consistente e inequívoca

**Contrato crítico:** `emitir=true` está permitido exclusivamente al crear proforma nueva o al actualizar `BORRADOR`. Para un `EN_REVISION` editable, enviar `emitir=true` debe devolver **409** con error estable sobre `estado` (u otra clave pública acordada) y rollback total; enviar `emitir=false` conserva la edición permitida. Estados `APROBADA`, `NO_CONCRETADA` u otros no editables continúan denegados bajo reglas actuales.

Implementación mínima sugerida: en `actualizar_proforma_integral`, tras bloqueo de cabecera y validación de `revision_esperada`, rechazar `emitir=true` si estado actual no es `BORRADOR` **antes** de crear `cliente_nuevo` o tocar cabecera/detalles. Conservar toda verificación actual de pertenencia de líneas, fichas, PRF-04 y estados; aplicar una prueba transaccional que demuestre cero escrituras ante rechazo.

En el primer guardado con emisión, validar cliente, detalle(s), precio nuevo positivo, descuentos, cantidad/unidad, catálogo, ficha técnica y resultado comercial mayor que cero mediante reglas ya vigentes; la confirmación de Vue no reemplaza validación servidor. Revisar `enviar_proforma` y endpoint histórico `/enviar/` frente a requisitos de emisión; cerrar brechas solo si se reproducen, sin agregar autorizaciones nuevas y preservando triggers.

**Separación de efectos:** `BORRADOR → EN_REVISION` no debe generar pedido, movimiento de inventario, venta, aprobación, archivo descargado ni cambio automático de otra fase. `aprobar_proforma` permanece posterior y separado; jamás se invoca de forma automática desde emisión. Una doble aprobación sigue controlada por el comportamiento vigente; PRF-05 no toca stock.

**Errores y retries:** mantener 400 para errores de payload y 409 para estado/concurrencia/replay incompatible, 404/403 según aislamiento, y transacción atómica en DB. Crear proforma usa `clave_idempotencia` con hash del payload; replay igual devuelve misma proforma, payload distinto con misma clave es conflicto. En PUT seguir exigiendo `revision_esperada` del agregado bajo bloqueo; la segunda escritura obsoleta debe fallar sin eliminar cambios de otro actor ni una ficha confirmada por NLP/HITL. No fabricar estado de éxito en respuesta.

## 7. Matriz obligatoria PRF-05.5 (backend + integración)

**Cliente:** persona/empresa válida e inválida; sugerencias solo sobre queryset permitido; cliente ajeno/inactivo; snapshot histórico; borrador sin cliente; emisión sin cliente 400; cliente nuevo en integral con error posterior y rollback de todas las entidades; replay con UUID igual/diferente; sin nuevos clientes por navegar.

**Condiciones:** monto de adelanto 0/100 y decimales válidos; valor negativo/ >100/fuera de precisión; validez nula, positiva, cero, negativa o fraccionaria; campos vacíos y opcionales; cambios BOB/USD sin conversión; conservación literal de observaciones largas y títulos/plazos en límites; documentos existentes reciben campos reales.

**Revisión:** GET conserva nombres/snapshots, descuentos, cantidades/unidades, modos `PRECIO_UNITARIO` y `TOTAL_NEGOCIADO`, fichas anidadas, atributos desconocidos y `CAJA` histórico. Envío de lineas integrales mantiene IDs/semántica de omisión, incluido vínculo opcional de captura PRF-04 cuando esté presente.

**Emisión:** POST integral `emitir=false`, POST integral `emitir=true`, PUT BORRADOR→EN_REVISION, PUT EN_REVISION `emitir=false` y `emitir=true` (rechazo 409), /enviar/ BORRADOR e intento repetido, sin líneas/sin total/cliente inválido, 409 de revisión, doble clic concurrente, idempotencia y rollback ante fallos. Ningún evento de emisión crea Pedido ni afecta stock; aprobación separada sigue siendo funcional.

**Regresiones:** AP3/AP4/AP5, FE04, PRF-01/02/03 y PRF-04 (si está integrada), de PostgreSQL, permisos, inventario, trabajadores/capturas y documentos sin intervención funcional en esos módulos. Probar PostgreSQL real, concurrente y transacciones; las pruebas SQLite no demuestran triggers.

## 8. Entregas recomendadas y comandos

- `T0`: inspeccionar HEAD, contratos, migraciones, CI, PRF-04 en curso; matriz de brechas real; tests que fallen antes de parchear.
- `T1`: mantener/perfeccionar contratos de cliente solo si hay fallo reproducible.
- `T2`: validar condiciones existentes con regresiones, corregir brechas reales sin nuevas obligaciones.
- `T3`: validar serialización íntegra para revisión comercial y datos técnicos PRF-03/04.
- `T4`: eliminar éxito falso de `emitir=true` en `EN_REVISION` y comprobar /enviar/, idempotencia, permisos y transiciones.
- `T5`: ejecutar todas las pruebas backend y E2E conjunto con frontend, corregir gates y documentar evidencia.

Ejecutar desde repositorios reales: `uv run ruff check .`, `uv run ruff format --check .`, `uv run python manage.py check`, `uv run python manage.py makemigrations --check --dry-run`, `uv run pytest -ra` en PostgreSQL, pruebas de concurrencia, OpenAPI drift según CI y `git diff --check`. Consultar `.github/workflows/ci.yml` para comandos exactos y servicios. Si la brecha requiriera schema/serializer nuevo, regenerar OpenAPI desde backend y cliente tipado en frontend; **no editar generated API manualmente**.

Al finalizar, informar por cada requisito qué archivo cambió o por qué no hizo falta, resultado de prueba, commits, PRs, estados CI y comandos de reproducción; no declarar verde un job sin verificar ejecución real. Si persisten fallos de seguridad/dependencias, clasificarlos y resolver su bloqueo mediante cambios mínimos coordinados.

**Exclusiones reiteradas:** no modificar `apps/pedidos/`, `apps/movimientos_stock/`, `apps/documentos/`, `apps/capturas/`, `homex-nlp` ni despliegue productivo por inercia. No añadir lógica de aprobación al guardado integral ni generar un pedido antes de la aprobación separada.
