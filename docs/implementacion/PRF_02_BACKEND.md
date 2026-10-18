# PRF-02 — Especificación definitiva BACKEND: catálogo, variantes y proformas HOMEX

**Estado funcional:** PRF-02.1–PRF-02.7 DEFINIDOS Y APROBADOS por el usuario (18-10-2026).
**Estado de ejecución:** especificación; NO constituye implementación ni evidencia de tests.
**Baseline verificada:** backend main ce45a08f490b209d2091886272e891f02e0f6639; frontend main f8994b0aa4df215c5422f47190257f93914443b1. Reexaminar SHAs y estado Git antes de programar.
**Documento par obligatorio:** homex-frontend/docs/implementacion/PRF_02_FRONTEND.md.
**Precedentes:** docs/implementacion/PRF_01_BACKEND.md; contratos y tests vigentes de AP3/AP4/AP5/AP6/AP6.1, PostgreSQL/migraciones y OpenAPI.
**Ámbito:** respaldo mínimo, autoritativo y probado para las siete decisiones de catálogo y líneas comerciales.

> Mandato: no reinventar arquitectura ni redefinir el dominio. Implementar solamente brechas PRF-02 sustentadas en código/pruebas reales. Conservar dominios, permisos, datos históricos, cambios de estado y transaccionalidad PostgreSQL. Coordinar todos los cambios públicos con el frontend; Codex no decide reglas nuevas por sí solo.

## 0. Invariantes del negocio obligatorios

1. **Producto** es el maestro de cada SKU/variante, con categoría, familia opcional, precio de lista, unidad de stock, stock e identidad propios. Tiene fichas opcionales por categoría (ProductoSilla / ProductoPiso) y DescuentoProducto. No crear otro catálogo maestro dentro de proformas.
2. **FamiliaProducto** contiene código, nombre, descripción y activo; **no almacena categoría ni unidad**. Familia no equivale a SKU, no tiene stock unitario ni precio de variante; tampoco garantiza por esquema que todos sus SKU sean de la misma categoría.
3. **DetalleProforma** puede representar SKU concreto o familia pendiente. Familia pendiente válida en BORRADOR y EN_REVISION sin reserva ni SKU inventado; aprobación con pendiente está prohibida por reglas transaccionales. Resolver significa actualizar la **misma** línea, preservando ID, datos comerciales y características escritas cuando sean compatibles.
4. La variante SKU es única por proforma; no crear duplicados ni fusionar precios/cantidades de acuerdos diferentes. Backend + PostgreSQL siguen autoridad de conflictos y validaciones, nunca solo Vue.
5. SILLA=PIEZA; nuevo PISO_FLOTANTE=M2 con precisión 4 decimales conforme a contrato; OTRO=PIEZA/JUEGO/BARRA. CAJA es **histórica**, no se crea como unidad de nuevos pisos ni se convierte implícitamente desde m²; m2_por_caja es dato descriptivo. Mueble a pedido admite PIEZA/JUEGO según esquema, no SKU catálogo.
6. Precio de catálogo en BOB y promoción vigente incluidos en precio_catalogo_vigente. Precio unitario cotizado negociable de línea; descuento de línea es importe monetario **total**, no porcentaje ni duplicación de promoción. Para USD, precio **explícito**, sin conversión de BOB. Nuevas líneas PRECIO_UNITARIO con precio >0; cantidad >0; descuento entre cero e importe bruto. Importes definitivos PostgreSQL.
7. Preservar modo histórico TOTAL_NEGOCIADO y snapshots reales de precio/promoción de línea; no convertir datos antiguos ni reconstruir un unitario inexistente. No afirmar snapshot histórico completo de todas las propiedades de maestro: modelo actual no lo conserva.
8. Consultar, cotizar o guardar borrador no reserva ni consume stock ni crea pedido, venta, movimiento u OT. Aprobación conserva reglas de stock/venta, permisos, concurrencia e idempotencia ya implementadas.
9. Lectura de catálogo para vendedores autorizados. Mutación de maestro requiere EsAdministradorComercial. Actualizaciones de producto exigen If-Match/revisión actual y conflicto 409 cuando corresponda. Conservar ownership y no exponer datos de otras proformas/vendedores.
10. POST /api/v1/proformas/integral/ y PUT /api/v1/proformas/{id}/integral/ continúan transaccionales y con clave_idempotencia, revision_esperada, IDs estables y restricciones de estado. No guardar proforma para navegar o crear maestro.
11. No editar migraciones publicadas; no tocar lógica de NLP, audio, despliegue, pedidos, recibos, OT, movimiento stock ni roles. La **única** intervención documental prevista en PRF-02 es la etiqueta mínima de variante pendiente en PDF, preservando el diseño existente.
12. No deshabilitar tests, no modificar datos históricos ni inventar categorías/unidades/atributos o URLs.

## 1. Baseline real y brechas de ejecución

| Área | Realidad constatada | Trabajo previsto |
|---|---|---|
| apps/catalogo/models.py | Producto por SKU; familia opcional sin categoría/unidad; fichas silla y piso; precio, unidad y stock en producto | Preferir **sin nuevas tablas/migraciones** |
| apps/catalogo/api/views.py | ProductoViewSet DRF SearchFilter por sku/nombre; get_queryset soporta activo/categoria/familia | Añadir filtros de categoría específicos y asegurar filtro antes de paginar |
| apps/catalogo/api/serializers.py | ProductoFiltrosListadoSerializer solo activo, categoria, familia. ProductoSerializer expone SKU, ficha, precio vigente, stock, demanda, disponibilidad | Validar filtros nuevos y coherencia de respuesta |
| apps/catalogo/services.py | demanda_pendiente_por_producto() se ejecuta al formar demanda y disponibilidad por SKU | Medir y corregir N+1 si confirmado |
| apps/proformas/models.py | Detalle con producto o familia, precio unitario, descuento, importe_negociado, snapshot promo | Conservar IDs y campos históricos |
| apps/proformas/api/serializers.py | Valida precio nuevo >0, descuento, SKU duplicado, estado/emisión | Añadir cobertura de resolución pendiente y categoría/unidad si hace falta |
| apps/proformas/services.py | agregar_detalle, actualizar_detalle, _sincronizar_detalles, precio BOB/USD y snapshots | No sobrescribir negociación; probar actualización pendiente → SKU |
| apps/proformas/migrations/0007_ap6_unidades_redondeo.py y posteriores | Triggers PostgreSQL por tipo/stock/unidad, CAJA histórica, validación SKU/familia | No editar migraciones aplicadas; cualquier corrección nueva compatible |
| apps/documentos/pdf.py | Renderiza nombre, descripción, cantidad, precio, descuento y total; no etiqueta explícita pendiente | Etiquetar pendiente en documento sin rediseñar PDF |
| docs/openapi.yaml | Contrato publicado consumido por Vue y cliente generado | Sincronizar ante parámetros o campos nuevos |

Los cambios de frontend no sustituyen controles reales backend; solo muestran y previenen errores.

## 2. PRF-02.1 — Dos caminos con un solo contrato comercial

- Camino **Producto de catálogo**: consultar silla, piso u otro mediante maestro existente y transferir SKU concreto al formulario comercial del editor; no crear endpoint duplicado para «catálogo de proforma».
- Camino **Mueble a pedido**: línea MUEBLE_MEDIDA con ficha EspecificacionMueble, sin producto ni familia de catálogo. El formulario completo pertenece a PRF-03; asistencia de voz opcional PRF-04. Backend actual debe mantenerse compatible.
- Consultas a catálogo no ejecutan escritura en proformas ni stock. Crear producto sí escribe maestro; la proforma solo se escribe al Guardar borrador o Emitir.
- No forzar cliente ni emitir antes de permitir elaborar borrador. Revisar requisitos exactos de emisión/aprobación en servicios actuales.

## 3. PRF-02.2 — Contrato de filtros del catálogo

Extender ProductoFiltrosListadoSerializer y ProductoViewSet de forma coordinada con frontend y schema OpenAPI.

| Categoría | Parámetro API propuesto | Campo real Django |
|---|---|---|
| Global | search, activo, categoria, familia | sku/nombre, Producto.activo, categoria_id, familia_id |
| SILLA | marca | productosilla__marca_id |
| SILLA | modelo | productosilla__modelo (definir búsqueda textual controlada) |
| SILLA | color_primario | productosilla__color_primario_id |
| PISO_FLOTANTE | marca | productopiso__marca_id |
| PISO_FLOTANTE | tipo | productopiso__tipo_id |
| PISO_FLOTANTE | material | productopiso__material_id |
| PISO_FLOTANTE | diseno | productopiso__diseno_id |
| PISO_FLOTANTE | acabado | productopiso__acabado_id |
| PISO_FLOTANTE | espesor_mm | productopiso__espesor_mm con Decimal |
| OTRO | unidad_stock | unidad_stock_id |

Estos nombres son **propuesta técnica de claves**, a validar antes de fijar el contrato definitivo con frontend. Deben ser estables, documentados y probados, no meras rutas ORM filtradas sin validación.

- Para FKs validar ID y concepto: MARCA, COLOR, TIPO_PISO, MATERIAL_PISO, DISENO_PISO, ACABADO_PISO, UNIDAD_MEDIDA. Definir comportamiento frente a opciones históricas/inactivas sin romper consulta de históricos. Modelo con coincidencia textual definida; espesor Decimal exacto, no float.
- Validar combinaciones: filtros de SILLA con categoría PISO no deben dar resultados inesperados; devolver error claro 400 ante entrada inválida. Si no hay categoría, definir comportamiento determinista y probarlo.
- Filtros **SQL antes de paginación**, conteo real y orden estable, conservando contrato activo/categoria/familia/search previo y consulta administrativa de inactivos.
- No añadir color de piso inexistente ni campos sin correspondencia en modelos. Variantes de familia distintas siguen SKU individual; el stock/demanda es referencial, no reserva.
- Paginación real, consulta optimizada de relaciones relacionadas, imágenes mediante campos existentes; ninguna API nueva de media por motivo cosmético.

**Rendimiento:** ProductoSerializer llama a demanda_pendiente_por_producto() desde get_demanda_pendiente() y get_disponibilidad_referencial(), potencialmente dos agregaciones por SKU por página. Medir SQL con un catálogo representativo, comprobar crecimiento y, si es problema, sustituir por anotación/consulta agrupada u otra mejora segura sin alterar sumas decimales ni estados EN_REVISION/ENVIADA. Registrar consultas/tiempos antes-después y prueba antirregresión. No instalar buscadores ni cachés sin evidencia.

## 4. PRF-02.3 — Precio, unidad y descuento de línea de catálogo

- SKU específico determina tipo_item coherente con categoria, unidad=unidad_stock; backend/PostgreSQL valida ambos. Presentación de maestro actual no sustituye el precio negociado ni modifica maestro.
- PRECIO_UNITARIO nuevo exige precio >0, cantidad >0, descuento >=0 y <= cantidad*precio; precisión de Decimal PostgreSQL; total provisional frontend es solo estimación. Precio sin valor no se asume cero válido.
- BOB: si la línea **nueva** no trae precio explícito y backend permite completar, propone precio_catalogo_vigente. USD exige valor de vendedor, no convierte automáticamente. Promoción ya aplicada en precio_vigente, descuento adicional de línea inicia cero; evitar doble descuento.
- Editar línea, resolver pendiente o cambiar SKU nunca reemplaza importe negociado por precio vigente de maestro. Una acción comercial explícita del vendedor puede introducir nuevo valor; backend lo valida normalmente.
- Promoción/fechas y snapshots precio_antes_snapshot/precio_ahora_snapshot: comprobar rutas de agregar_detalle vs actualizar_detalle, respetar la representación histórica. Probar promo vigente, inactiva, vencida y cambio posterior de precio catálogo.
- Stock cero: cotizar se permite con advertencia frontend, sujeto a controles de aprobación. No crear reserva, movimientos ni recálculo falso de disponibilidad.
- Histórico TOTAL_NEGOCIADO y CAJA no deben convertirse en PRECIO_UNITARIO/M2 o reconstruirse por división. Rechazar conversiones no autorizadas.

## 5. PRF-02.4 — Familia pendiente y resolución sin pérdida

### Captura válida de pendiente

Una línea pendiente del catálogo almacena producto=NULL, familia_producto activa, nombre/descripción comercial, tipo_item congruente con la categoría del recorrido, unidad válida, cantidad positiva, precio unitario >0 y descuento válido. La familia no trae categoría/unidad, por lo que el tipo_item y la unidad **deben validarse directamente** para una línea nueva sin SKU: SILLA/PIEZA, PISO_FLOTANTE/M2 y OTRO/PIEZA/JUEGO/BARRA. La protección adicional debe preservar CAJA histórica, sin rechazar una operación inocua sobre registros heredados.

La familia puede estar activa y tener cero variantes disponibles. No inventar producto para completar pendiente. La emisión EN_REVISION con esta línea sigue permitida si los otros requisitos comerciales se cumplen.

### Resolución a variante

El PUT integral recibe el ID de línea original y SKU elegido; **actualiza la misma DetalleProforma**. Requiere producto existente/activo para la nueva asignación, mismo tipo/categoría, unidad compatible, familia correcta y SKU no incorporado ya en otra línea. Los campos precio negociado, descuento, cantidad válida, nombre/descripcion y especificación permanecen salvo cambio explícito y consciente. Si una unidad no coincide, rechazar conversión automática y solicitar revisión humana de cantidad y precio.

Un SKU sin familia no resuelve automáticamente una pendiente con otra familia. Dos pendientes resueltas al mismo SKU deben fallar sin fusionar contratos. No alterar detalles de proforma APROBADA. La aprobación con cualquier pendiente continúa bloqueada en PostgreSQL, antes de reservar/descontar stock o crear pedido.

**Caso con riesgo de código:** agregar_detalle puede adjuntar snapshots promoción, pero actualizar_detalle sigue flujo distinto; probar con base real y corregir brecha solo si se reproduce, sin recalcular retroactivamente precio pactado.

## 6. PRF-02.5 — Identidad, eliminación integral y no regresión

La lista, modal solo lectura, menú de tres puntos, stack local deshacer y formularios completos son principalmente responsabilidad frontend.

- Backend conserva integridad de ID de cada detalle cuando frontend edita la misma línea; _sincronizar_detalles no debe convertir edición en borrar+crear ni olvidar especificaciones.
- Eliminar en navegador es local hasta PUT integral explícito. Si el usuario hace deshacer, se reintegra la línea original con ID y ficha. No añadir papelera permanente.
- Una proforma EN_REVISION no puede quedarse sin contenido/requisitos requeridos mediante guardado integral; rollback íntegro ante error. Una línea histórica TOTAL_NEGOCIADO no pierde sentido por reconstrucción.
- Duplicar solo MUEBLE_MEDIDA abre formulario de creación independiente, y al confirmar debe tener alguna modificación respecto original; no duplicar SKU maestro. Backend mantiene reglas de ficha independiente, integridad y unicidad.
- Validar propiedad/autorización al escribir cada línea/archivo, y concurrencia cuando otra pestaña o petición altera la cotización.

## 7. PRF-02.6 — Creación/edición de maestro en contexto de proforma

- Reutilizar ProductoViewSet y ProductoSerializer actuales; no crear endpoints alternos. Alta transaccional incluye Producto y ficha/DescuentoProducto; imagen se sube en operación posterior separada; si esta falla, alta no se deshace ni se reintenta ciegamente.
- SILLA requiere ficha y unidad PIEZA; PISO_FLOTANTE requiere ficha y nueva unidad M2; OTRO admite PIEZA/JUEGO/BARRA sin ficha específica. No exigir atributos que modelos permiten nulos. Categoría y unidad_stock siguen inmutables una vez registrado.
- ProductoSilla.especificaciones acepta objeto JSON estructurado. Frontend mostrará controles comprensibles; backend conserva claves y objetos según contrato, sin borrar propiedades desconocidas por una serialización simplificadora.
- Alta crea stock=0. Operadores normales no pueden crear/modificar maestros. POST debe rechazar SKU duplicado/valor inválido sin producto parcial; PATCH/PUT exige If-Match actual (revision_producto), devuelve 409 para valor obsoleto; editar un campo no reactiva promociones inactivas.
- Retorno a proforma, borrador, ruta segura, identidad y guardado temporal ocurren frontend. No permitir que retorno cambie permisos API ni que crear maestro haga POST de proforma. Actualización de maestro no recalcula precios negociados guardados en proformas.
- Evitar enviar respuestas afirmando «snapshots históricos completos» cuando no se guardaron; mostrar datos maestros actuales correctamente identificados.

## 8. PRF-02.7 — PDF, calidad, seguridad e integración

### PDF mínimo para familias pendientes

Actualmente apps/documentos/pdf.py construye fila comercial desde nombre/descripcion, cantidad y precio, sin identificar explícitamente familia_producto sin producto. Añadir aviso textual mínimo y legible como «Variante pendiente de selección; sin SKU definitivo ni stock reservado» cuando corresponda, tanto en PDF emitido como en representación coherente de detalle; no rediseñar el generador, condiciones, numeración ni almacenaje. Proforma APROBADA no puede contener líneas pendientes según reglas existentes.

### Pruebas de API/servicios/PostgreSQL obligatorias

| Caso | Evidencia exigida |
|---|---|
| B-01 | Búsqueda SKU/nombre, activo/categoria/familia antes de paginar |
| B-02 | Filtros SILLA marca/modelo/color, combinaciones y validación |
| B-03 | Filtros PISO tipo/material/diseño/acabado/espesor con Decimal |
| B-04 | Filtro unidad OTRO sin productos de otras categorías |
| B-05 | Medición de consultas con N SKU, optimización si N+1 |
| B-06 | Alta de SILLA, PISO y OTRO, stock cero, ficha y rollback de alta inválida |
| B-07 | Permisos de vendedor/admin, edición con If-Match y 409 |
| B-08 | Edición no reactiva promo inactiva y no daña históricos |
| B-09 | Precio BOB promo vigente, sin doble descuento |
| B-10 | Precio USD explícito, sin conversiones |
| B-11 | Cantidad M2 decimal; PIEZA/JUEGO/BARRA enteros; CAJA histórica |
| B-12 | Precio nuevo ausente/cero/negativo y descuento inválido: error y rollback |
| B-13 | Familia pendiente en BORRADOR y EN_REVISION sin SKU/stock |
| B-14 | Aprobación pendiente rechazada, sin pedido ni movimiento |
| B-15 | Resolver pendiente conserva ID, precio, cantidad compatible y descuento |
| B-16 | Variante de otra familia/categoría/unidad rechazada |
| B-17 | Duplicado de SKU en otra línea: rechazo sin fusión |
| B-18 | Promoción y snapshot al resolver pendiente, precios negociados estables |
| B-19 | Eliminar última línea de EN_REVISION: integridad y rollback |
| B-20 | Idempotencia y revisión 409 al guardar íntegramente |
| B-21 | Leer y editar sin transformar históricos TOTAL_NEGOCIADO/CAJA |
| B-22 | PDF con variante pendiente claramente identificada y luego resuelta |
| B-23 | Cotizar SKU con stock cero sin reservar; aprobación valida real |
| B-24 | E2E real con **pareja de commits** frontend/backend de PRF-02 |

No limitarse a mocks de respuesta para declarar flujo integrado; ejecutar API real + PostgreSQL. Las pruebas deben comprobar aislamiento entre vendedores, datos de clientes, roles, estados y documentos; no eliminar suites existentes.

### Gates reales de cierre

- uv sync --locked --extra dev (ajustar extras al entorno de pruebas vigente).
- uv run ruff check .; uv run ruff format --check .
- uv run python manage.py check.
- uv run python manage.py makemigrations --check --dry-run.
- uv run pytest -ra con PostgreSQL real preparado; tests de concurrencia cuando corresponda.
- uv run python manage.py spectacular --file /tmp/prf02-openapi.yaml --validate, comparar schema con docs/openapi.yaml; actualizarlo coherentemente si cambian filtros/contratos.
- Coordinar frontend: regenerar desde schema con npm run api:generate, luego npm run contract:check, tests/unit/E2E/integración y build. Nunca editar src/generated/api a mano.
- CI backend+frontend con SHAs coordinados; los jobs históricos que fijan otras revisiones no prueban PRF-02 en conjunto. No reportar tests PASS o rendimiento mejorado sin evidencia concreta.

## 9. Secuencia de ejecución Codex (coordinada con frontend)

1. Inspeccionar main actual, ramas/worktrees/estado de cambios en ambos repos; revisar tests, triggers, contratos y baseline. Documentar brechas. No partir de rutas supuestas ni destruir trabajo.
2. Definir nombres exactos de filtros junto a frontend y añadir tests API; implementar filtros SQL/paginación, validar concepto/categoría, medir costo de serialización y optimizar solo ante evidencia.
3. Reproducir casos de familia pendiente y resolución, promociones/snapshots y unidad/duplicación con PostgreSQL. Corregir únicamente fallos reales; conservar histórico, IDs y estados.
4. Incorporar marca textual mínima de variante pendiente al PDF con regresión de documentos/paginación; mantener aislamiento.
5. Generar/verificar schema y tipos coordinados con frontend; ejecutar E2E con par de commits actual, gates completos, revisión de diff/PR/CI.
6. Entregar matriz de cobertura PRF-02.1–02.7, archivos, resultados reales, SHAs/PRs, fallos abiertos y comandos reproducibles; auditoría posterior independiente y visto bueno del usuario.

## 10. Matriz de trazabilidad por decisión

| PRF | Responsabilidad backend | Política |
|---|---|---|
| 02.1 | Reutilizar producto/detalle integral y MUEBLE_MEDIDA | Sin nueva entidad |
| 02.2 | Filtros reales, paginación, SKU/atributos/unidad/precio/stock referencial | Ampliar API y OpenAPI con tests |
| 02.3 | Precio BOB/USD, descuento, promo y unidades correctas | PostgreSQL autoritativo e históricos intactos |
| 02.4 | Familia pendiente y su resolución en línea original | Validación y aprobación bajo control PG |
| 02.5 | Identidad, unicidad, eliminación integral y transacciones | Principalmente regresión backend |
| 02.6 | Maestro creado/editado con permisos, atomicidad e If-Match | Reutilizar endpoints |
| 02.7 | PDF mínimo, integración real, seguridad, performance y CI | Evidencia verificable, no promesas |

## 11. Restricciones de publicación

No usar comandos Git destructivos ni forzar push sobre ramas compartidas sin autorización. Trabajar en ramas/PR/CI de cada repositorio. No migrar datos productivos ni publicar Deploy/NLP. No reescribir migraciones aplicadas. No declarar PRF-02 «implementada» por publicar esta especificación: la aceptación exige implementación, pruebas ejecutadas y auditoría independiente del usuario.

**Resultado contractual requerido:** catálogo real filtrable, variantes identificables, familias pendientes sin reserva, preservación de negociación/ID al resolver, maestro protegido, historial íntegro y PostgreSQL como autoridad.
