# PRF-01 — Contrato backend y protección comercial (AP3–AP6.1)

**Estado del documento:** especificación funcional y técnica aprobada; implementación pendiente.  
**Programa:** perfeccionamiento de la experiencia comercial HOMEX, fase 01, puntos PRF-01.1 a PRF-01.8.  
**Repositorio:** homex-backend, rama principal `main`.  
**Documento complementario:** `homex-frontend/docs/implementacion/PRF_01_FRONTEND.md`.  
**Línea base consultada:** `main` en `a5ed73d8d81f54144385d655f228c4504c437aa8` (16-10-2026 UTC). Revalidar antes de modificar.

## 1. Propósito y regla de decisión

La fase PRF-01 prepara fundamentos visuales, responsividad, formularios, lenguaje comercial, validaciones preventivas, mensajes, presentación fiel de datos y protección contra regresiones. No es una nueva implementación de proformas ni una refactorización del dominio.

El backend es la **fuente autoritativa** de reglas comerciales, precios y totales persistidos, permisos, transacciones, revisiones, estados e integridad PostgreSQL. No duplicar estas responsabilidades en el frontend. Como el grueso de PRF-01 es visual y preventivo, **no realizar cambios de backend por inercia**: corregir o ampliar backend exclusivamente ante una brecha reproducible respecto de una regla aprobada, con prueba que primero demuestre el fallo.

Si una necesidad corresponde a PRF-02 (catálogo), PRF-03 (muebles personalizados), PRF-04 (voz/NLP/HITL), PRF-05 (formalización y condiciones) o PRF-06 (gestión y documentos), registrar la dependencia y aplazar la transformación funcional. No adelantar estas fases.

## 2. Superficies reales de referencia

- `apps/proformas/services.py`: creación, edición y reglas comerciales.
- `apps/proformas/api/serializers.py` y `apps/proformas/api/views.py`: validación y exposición del contrato.
- `apps/proformas/models.py`, `apps/proformas/validacion_tecnica.py` y `apps/proformas/revision.py`: modelo, ficha técnica y token de revisión.
- `apps/clientes/validacion.py`, `apps/clientes/services.py`: identidad, alcance y registro de clientes.
- `apps/catalogo/`: productos, variantes, familias, promociones y unidades.
- `apps/pedidos/`, `apps/movimientos_stock/` y `apps/documentos/`: aprobación, pedidos, movimientos y documentos, sólo para verificar conservación.
- `apps/capturas/`: integración y confirmación HITL, sólo para regresión de compatibilidad.
- `docs/implementacion/AP3_PROFORMAS_INTEGRALES.md`, `AP6_IMPLEMENTACION.md`, `AP6_1_INVENTARIO.md` y OpenAPI versionado: decisiones y evidencia de referencia.
- `docs/implementacion/CONTRATO_FE04_PROFORMAS.md` es documentación histórica. Resolver discrepancias con código vigente, migraciones y pruebas actuales antes de asumir cualquier restricción.

### Contrato integral existente que no se debe romper

- `POST /api/v1/proformas/integral/` crea la cabecera, un cliente nuevo opcional, líneas y fichas de manera atómica; `emitir=false` guarda borrador; `emitir=true` solicita emisión con requisitos completos.
- `PUT /api/v1/proformas/{id}/integral/` sincroniza una proforma editable; debe conservar IDs y semántica de omisión explícita de líneas y fichas según el contrato actual.
- `clave_idempotencia` protege reintentos del primer guardado. El mismo payload y clave debe reproducir su resultado; el uso incompatible de la clave debe seguir provocando conflicto.
- `revision_esperada` protege contra sobrescrituras concurrentes; 400 para ausencia exigida y 409 ante obsolescencia, con rollback y conservación del trabajo local en el frontend.
- La creación o modificación integral no debe dejar transacciones parciales, consumir numeración por sólo navegar o crear clientes huérfanos por errores.
- `BORRADOR` y `EN_REVISION` tienen capacidades de edición descritas por AP3/AP6; otros estados respetan su propia semántica. No tomar la regla anterior de FE04 como autoridad vigente.
- Los históricos `TOTAL_NEGOCIADO` y `CAJA` no se recalculan, convierten ni reinterpretan automáticamente. Para nuevas líneas el modo es `PRECIO_UNITARIO`.
- Los triggers y servicios PostgreSQL conservan autoridad sobre descuentos, importes, snapshots, stock y sus efectos.
- `datos_tecnicos` es un único JSON comercial abierto, no el contrato externo NLP v1: preservar claves y atributos desconocidos; no introducir `schema_version` en el JSON comercial.
- El catálogo admite variante real y familia pendiente con distintas consecuencias; una familia pendiente no equivale a reservar stock.
- Los clientes se validan según identidad, tipo, estado y alcance del vendedor; administración mantiene los permisos que le correspondan.
- Aprobación, pedido, cancelación, ventas, reversas y movimientos de stock continúan siendo operaciones autoritativas, protegidas e idempotentes según su propio contrato.
- No exponer a taller importes, fichas o campos ocultos por permisos actuales; conservar el aislamiento entre vendedores.

## 3. Acuerdos PRF-01 aplicables a backend

| ID | Requisito y tratamiento backend |
| --- | --- |
| PRF-01.1 | Mantener API, modelo, seguridad, servicios y migraciones existentes. No introducir arquitectura nueva por un ajuste de presentación. |
| PRF-01.2 | Sin cambio de dominio. Confirmar que las respuestas existentes permiten render responsive sin paginación rota ni consultas innecesarias. |
| PRF-01.3 | Mantener la validación autoritativa del servidor y errores por campo cuando el contrato los provee. No sustituirlos por validación exclusiva en Vue. |
| PRF-01.4 | Los textos orientados al usuario se interpretan en frontend; no cambiar nombres de campos, códigos de estados ni valores de catálogo para embellecer etiquetas. |
| PRF-01.5 | Evitar nuevas líneas con precio unitario ausente, inválido o no positivo; respetar precisión de cantidades, descuentos válidos (incluido cero), moneda, unidad de stock y requisitos de emisión. Conservar borradores parciales válidos sin forzar cliente ni emisión prematura. Verificar brecha real antes de añadir reglas. |
| PRF-01.6 | Errores tipificados, 400/403/404/409 y transacciones deben permanecer distinguibles; nunca responder éxito falso, crear duplicados ni omitir información necesaria para recuperación. Deshacer eliminación provisional es local al frontend, no una operación de base de datos nueva. |
| PRF-01.7 | Persistir y devolver fielmente ceros válidos, nulos, vacíos y pendientes; no convertir ausencia de precio en cero, ni transformar «A elección» en «No especificado». El total persistido y los importes históricos siguen siendo autoritativos. |
| PRF-01.8 | Mantener estado, permisos, concurrencia, idempotencia, integridad de datos, historial, documentos y compatibilidad con NLP y despliegue; agregar regresiones sólo donde exista brecha en la cobertura real. |

### Distinciones obligatorias de validación

1. **Borrador incompleto no es operación inválida.** Puede faltarle cliente o condiciones que sólo son obligatorias al emitir; no puede consolidar una línea nueva comercialmente inválida. Para nuevos detalles, precio unitario explícito y positivo, cantidad positiva según unidad, descuento dentro de reglas vigentes.
2. **Cero no es ausencia.** Descuento cero es válido; un precio no informado no se representa como Bs 0,00 ni se acepta automáticamente como gratuito. No inferir importes.
3. **M2 frente a unidades enteras.** Mantener precisión decimal (cadenas decimales y reglas actuales) y unidades de inventario; sin conversión improvisada.
4. **Catálogo y promociones.** El producto puede proponer un precio y la promoción aplica conforme a servicios existentes; el vendedor conserva las atribuciones de negociación autorizadas. No duplicar descuentos ni alterar snapshots.
5. **Datos técnicos.** Diferenciar declarado «a elección», desconocido/no indicado, vacíos deliberados y atributos ya persistidos. No eliminar claves JSON ajenas al formulario. La ficha técnica por componentes debe permanecer compatible con la representación actual.
6. **Seguridad y errores.** No revelar recursos ajenos; respetar 403/404 apropiados y no transformar conflictos en 500 ni en éxito.
7. **Históricos.** No aplicar restricciones nuevas retroactivamente a lectura de registros válidos del pasado, ni transformar `TOTAL_NEGOCIADO` a precio unitario.

## 4. Política de intervención (mínima y comprobable)

**Paso B1 — comprobar contrato actual.** Antes de editar, revisar `main` actualizado, los tests de AP3/AP4/AP5/AP6/AP6.1, migraciones, schema y contratos tipados frontend. Documentar las divergencias comprobadas con archivo, caso y respuesta reproducible.

**Paso B2 — clasificar las brechas.** Para cada problema PRF-01: (a) resolución exclusivamente frontend; (b) validación ya implementada en backend que requiere mejor representación; (c) incumplimiento real de backend. Solamente (c) habilita código backend.

**Paso B3 — cambio mínimo.** Resolver el caso (c) conservando compatibilidad de payloads, campos públicos, estados, APIs heredadas y datos existentes. No modificar migraciones publicadas. Cualquier migración aditiva nueva requiere evidencia inequívoca, análisis de rollback y verificación con datos históricos; si implica cambio de reglas, detener y pedir definición fuera de PRF-01.

**Paso B4 — contrato sincronizado.** Si hay una modificación imprescindible del esquema: regenerar OpenAPI y el cliente TypeScript por el procedimiento oficial de los repos; documentar impacto y coordinar commit del frontend. Prohibido editar código generado manualmente o inventar endpoints.

**Paso B5 — pruebas y resultados.** Ejecutar las suites focales y completas con PostgreSQL real donde corresponda. Mantener evidencia de comandos, éxito/fallo, configuración y SHA de ambas ramas. No ocultar pruebas fallidas ni cambiar aserciones para que pasen artificialmente.

### Módulos expresamente fuera de cambios funcionales

- `apps/pedidos/`, `apps/movimientos_stock/`, `apps/documentos/`, `apps/capturas/`, NLP y Deploy: verificar compatibilidad; no alterar comportamiento en PRF-01.
- No desplegar, publicar versiones ni promocionar D07 RC2 o producción.
- No redefinir el modelo de datos, estados, roles, reglas de stock, promociones o estrategia de cálculo.
- No introducir rutas de persistencia automática al navegar ni endpoints nuevos para suplir problemas de interfaz.

## 5. Matriz de regresión mínima obligatoria

| Identificador | Escenario | Evidencia esperada |
| --- | --- | --- |
| B-01 | Editor abre, cambia apartados y se abandona sin guardar | Cero escrituras; sin nueva numeración |
| B-02 | Guardar borrador sin cliente | Operación permitida si el contenido persistido cumple las reglas |
| B-03 | Intentar emitir sin cliente, sin líneas o con datos inválidos | Rechazo consistente, sin escritura parcial |
| B-04 | Guardado integral válido con cliente nuevo | Transacción única y persistencia completa |
| B-05 | Error durante guardado integral | Rollback de cliente, proforma, líneas y especificaciones |
| B-06 | Doble envío/replay con clave idéntica y luego payload distinto | Reintento idempotente; conflicto para reutilización incompatible |
| B-07 | Revisión obsoleta, modificación simultánea/HITL | 409, integridad conservada, sin sobrescritura |
| B-08 | Línea de catálogo duplicada o variante con unidad no válida | Rechazo según contrato actual, sin contaminación de stock |
| B-09 | Nueva línea: unitario ausente, cero, negativo o inválido; descuento cero | Rechazo correcto del precio; descuento cero aceptado |
| B-10 | M2 fraccional y pieza/unidad entera; promoción | Precisión, descuentos, snapshots y redondeos correctos |
| B-11 | Históricos `TOTAL_NEGOCIADO` y `CAJA` | Valores intactos antes/después de lectura y edición autorizada |
| B-12 | Edición parcial de `datos_tecnicos` con claves extra | No perder componentes, características, ni atributos desconocidos |
| B-13 | Cliente ajeno, rol no autorizado o proforma de otro vendedor | Acceso restringido, sin fuga de información |
| B-14 | Aprobación, pedido, reversa/cancelación y consulta inventario | Sin cambios de semántica, sin duplicación ni escrituras ocultas |
| B-15 | Confirmación HITL existente y generación documental | Contrato preservado; original IA y datos comerciales diferenciados |

Preferir tests existentes y añadir sólo aserciones faltantes y relevantes. Archivos orientadores: `tests/api/test_ap3_proformas_integrales.py`, `test_ap3_auditoria_regresiones.py`, `test_ap4_clientes.py`, `test_ap5_catalogo_documentos.py`, `tests/integration/test_ap6_reglas.py`, `test_ap6_correcciones.py`, `tests/api/test_f083_hitl_api.py` y pruebas de inventario.

## 6. Comandos de comprobación (ajustar al entorno real)

Ejecutar desde la raíz del backend, con dependencias y servicios ya preparados:

- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run python manage.py check`
- `uv run python manage.py makemigrations --check --dry-run`
- `uv run python manage.py spectacular --file docs/openapi.yaml --validate` (validar ruta y estado del OpenAPI en el checkout)
- `uv run pytest -ra`, incluida la integración PostgreSQL configurada por el proyecto.
- `git diff --check` y revisión de migraciones y de contratos.

Además, verificar los tests reales frontend/backend en integración cuando el cambio alcance un contrato. No atribuir a la ejecución local cifras de tests históricas de documentos AP3/AP6.

## 7. Entrega de Codex y condición de cierre

- Informar diagnóstico respaldado por código y distinguir problemas preventivos de defectos reales.
- Entregar una **matriz requisito → archivo modificado (o sin cambios justificados) → prueba → resultado** para PRF-01.1 a PRF-01.8.
- Si la revisión demuestra que no hay cambios backend imprescindibles, declarar **backend sin cambios funcionales** y registrar pruebas de regresión; esto es preferible a fabricar commits de código innecesarios.
- Si sí los hay, preparar el mínimo cambio y revisión coordinada con frontend, con commits/PR separados por repo siguiendo las prácticas vigentes.
- Verificar compatibilidad con AP3–AP6.1, migraciones existentes y servicios NLP/Deploy sin modificar esos repos.
- Adjuntar SHAs finales y CI, comandos ejecutados, limitaciones reales y cualquier deuda **fuera de alcance**.
- No declarar fase terminada sólo por pasar lint/build: requiere pruebas funcionales, regresiones y aceptación del usuario.

**Regla superior:** la calidad de PRF-01 se mide por claridad y rapidez de la cotización sin sacrificar autoridad PostgreSQL, datos históricos, seguridad ni estabilidad.