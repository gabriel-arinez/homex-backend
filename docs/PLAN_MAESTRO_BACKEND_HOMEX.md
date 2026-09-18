# Plan maestro de implementación e integración — HOMEX Backend

**Fecha de revisión:** 18 de septiembre de 2026  
**Versión del plan:** 2.0 — reinicio seguro para producción  
**Repositorio:** `gabriel-arinez/homex-backend`  
**Rama rectora:** `main`  
**Baseline de código antes de ejecutar F07:** `main` después de este documento  
**Referencia SQL:** `homex_bd_final_v3.sql`  
**Baseline Python:** 3.11.15  
**Base de datos objetivo:** PostgreSQL  
**Repositorios coordinados:** `homex-backend`, `homex-nlp`, futuro `homex-frontend` y `homex-deploy`

---

# 0. Propósito de este documento

Este documento es el contrato de ejecución del backend HOMEX. Está escrito para que una persona o un agente de desarrollo como Codex pueda tomar **una fase concreta**, implementarla sin reinterpretar el dominio y demostrar objetivamente que quedó cerrada antes de avanzar.

No es una lista orientativa. Cada fase define:

1. precondiciones;
2. alcance permitido;
3. decisiones ya fijadas;
4. trabajo obligatorio;
5. trabajo prohibido;
6. pruebas obligatorias;
7. evidencia de cierre;
8. condición exacta para poder iniciar la siguiente fase.

Una fase **NO** se considera terminada porque:

- el código compile;
- una prueba local aislada pase;
- exista un commit;
- Django arranque;
- una migración funcione en una base ya preparada;
- una funcionalidad “parezca funcionar” manualmente.

Una fase solo se cierra cuando **todos sus gates obligatorios están verdes**, la evidencia está versionada y no existen fallos, skips indebidos, migraciones pendientes ni divergencias documentales.

---

# 1. Decisión de reinicio

La implementación experimental realizada en la rama `refactor` **no se fusionará ni se utilizará como fuente de código para continuar**.

El nuevo desarrollo parte de `main`.

La rama `refactor` solo sirve como evidencia de riesgos que este plan debe evitar. Entre ellos:

- traducciones mecánicas de identificadores que pueden alterar métodos nativos;
- CI que falla antes de ejecutar pruebas críticas;
- OpenAPI versionado distinto al contrato real;
- pruebas locales verdes mientras CI está rojo;
- lógica alternativa para SQLite que no representa PostgreSQL;
- refactors masivos de nomenclatura después de crear migraciones;
- documentación que afirma cierre sin evidencia completa.

**Regla:** no copiar archivos completos desde `refactor`. Si una idea técnica se reutiliza, debe implementarse nuevamente desde este plan y superar sus pruebas desde una base limpia.

---

# 2. Jerarquía de autoridad

Cuando dos fuentes parezcan contradecirse, usar este orden:

1. `homex-nlp/docs/requirements.md`: G01–G03, T01–T09, P29–P32 y reglas previas no revocadas;
2. `homex-nlp/docs/integration-django.md`;
3. `homex-nlp/docs/contract-v1.md`;
4. plan maestro vigente de `homex-nlp/refactor`;
5. este Plan Maestro Backend;
6. `homex_bd_final_v3.sql` como referencia estructural;
7. código histórico o experimental.

Las decisiones empresariales explícitas prevalecen sobre el SQL v3 cuando el propio requisito indique que v3 todavía no contiene la corrección.

**Prohibido:** resolver contradicciones inventando tablas, campos, estados o reglas no aprobadas.

---

# 3. Convención definitiva de idioma y nomenclatura

Esta decisión se congela **antes de crear migraciones comerciales**.

## 3.1. Framework e infraestructura: inglés

Se conservan en inglés los elementos propios de Django, DRF, Python y librerías externas.

Ejemplos:

- `apps/accounts`;
- `accounts.User`;
- `AUTH_USER_MODEL = "accounts.User"`;
- `models.py`, `views.py`, `serializers.py`, `urls.py`, `apps.py`, `admin.py`;
- `migrations/`, `tests/`, `settings/`, `config/`;
- `save`, `create`, `update`, `delete`, `get_queryset`, `perform_create`;
- `username`, `password`, `email`, `is_staff`, `is_active`, `is_superuser`;
- `django.contrib.auth`, JWT, OpenAPI, Celery, Redis.

Las tablas estándar creadas por Django no se renombran.

## 3.2. Dominio HOMEX: español

Las apps comerciales definitivas son:

```text
apps/
├── accounts/
├── catalogo/
├── clientes/
├── proformas/
├── pedidos/
├── movimientos_stock/
├── ordenes_trabajo/
├── recibos/
├── notas_entrega/
├── documentos/
└── capturas/
```

Nombres expresamente descartados como apps finales:

- `inventory`;
- `inventario`;
- `workshop`;
- `taller`;
- `payments`;
- `pagos`;
- `deliveries`;
- `entregas`;
- `orders`;
- `quotations`;
- `customers`;
- `catalog`;
- `documents`;
- `captures`;
- `ventas`;
- `nlp`.

La app `movimientos_stock` representa el comportamiento real de HOMEX: `productos.stock` + historial inmutable de `movimientos_stock`. No se crea un subsistema abstracto llamado inventario.

## 3.3. Entidades comerciales

Nombres Python esperados:

- `ConceptoCatalogo`;
- `ValorCatalogo`;
- `Cliente`;
- `Producto`;
- `ProductoSilla`;
- `ProductoPiso`;
- `DescuentoProducto`;
- `Proforma`;
- `DetalleProforma`;
- `EspecificacionMueble`;
- `Pedido`;
- `TransicionEstadoPedido`;
- `OrdenTrabajo`;
- `NotaEntrega`;
- `Recibo`;
- `MovimientoStock`;
- entidades de capturas equivalentes al SQL.

Los campos y acciones del negocio se nombran en español cuando son propiedad de HOMEX: `cliente`, `vendedor`, `estado`, `cantidad`, `precio_unitario`, `modo_calculo`, `aprobar`, `cancelar`, `emitir_recibo`, etc.

Los valores persistidos de catálogo/estado como `PRECIO_UNITARIO`, `TOTAL_NEGOCIADO`, `ENVIADA`, `APROBADA`, `VENTA`, `REVERSA_VENTA`, `EMITIDO` y `ANULADO` se conservan exactamente.

## 3.4. Regla anti-refactor mecánico

Está prohibido ejecutar reemplazos globales ciegos para traducir identificadores.

Antes de renombrar un símbolo debe clasificarse como:

1. símbolo de framework/librería: no traducir;
2. contrato externo: conservar;
3. dominio HOMEX: traducir según glosario;
4. símbolo interno genérico: cambiar solo si mejora claridad y sus tests cubren el cambio.

Nunca transformar métodos nativos o de librería por similitud textual. Ejemplos de símbolos que no deben alterarse: `splitlines()`, `select_for_update()`, `get_queryset()`, `update_fields`.

---

# 4. Arquitectura objetivo

HOMEX será un **monolito modular Django/DRF**.

```text
Vue
 │ HTTPS/JSON
 ▼
Django + DRF
 │
 ├── PostgreSQL  ← autoridad comercial e integridad
 │      └── outbox
 │
 ├── archivos temporales privados
 │
 └── publicador → Redis → Worker Django
                         ├── ASR
                         ├── homex-nlp fijado por versión
                         └── servicios del backend → PostgreSQL
```

Responsabilidades:

- Django: autenticación, autorización, casos de uso, API y coordinación transaccional;
- PostgreSQL: invariantes, FK, checks, triggers y concurrencia;
- Redis: transporte de trabajo, nunca fuente de verdad;
- Celery/worker: ejecución asíncrona;
- `homex-nlp`: propuesta/evidencia NLP, nunca autoridad comercial;
- Vue: presentación y corrección, nunca cálculo definitivo de stock/totales/permisos.

No se introducen microservicios por módulo.

---

# 5. Fuente operativa de la base de datos

`homex_bd_final_v3.sql` contiene actualmente:

- 24 tablas comerciales;
- 4 secuencias comerciales;
- funciones y triggers del dominio.

Las 24 tablas son:

```text
catalogo_conceptos
catalogo_valores
clientes
productos
productos_silla
productos_piso
productos_descuento
proformas
proformas_detalle
especificaciones_mueble
pedidos
transiciones_estado_pedido
ordenes_trabajo
notas_entrega
recibos
archivos_adjuntos
capturas
intentos_captura
trabajos_outbox
items_ia
items_humano
evaluaciones_nlp
mediciones_proceso
movimientos_stock
```

Secuencias:

```text
seq_proformas_numero
seq_ordenes_trabajo_numero
seq_notas_entrega_numero
seq_recibos_numero
```

## 5.1. Regla de propiedad

Después de DB-01, **las migraciones Django son la única fuente operativa del esquema**.

El SQL v3:

- se conserva como referencia;
- se utiliza para comparar estructura y comportamiento;
- no se ejecuta encima de una base ya creada por migraciones;
- no se mantiene como una segunda ruta de bootstrap.

`inspectdb` puede utilizarse para auditoría, nunca como arquitectura final `managed=False`.

---

# 6. PostgreSQL es obligatorio desde el comienzo

El backend de producción usa PostgreSQL. Por tanto:

- las pruebas ORM/API que dependan de base de datos deben ejecutarse con PostgreSQL en CI;
- SQLite no es criterio de aceptación del backend;
- no se implementará lógica comercial alternativa con `if connection.vendor != "postgresql"`;
- los tests de triggers, locks, secuencias y concurrencia siempre usan PostgreSQL real;
- las pruebas de concurrencia usan conexiones independientes.

Una prueba pura que no toca ORM puede ser unitaria y no requerir DB.

**Prohibido:** hacer pasar tests con comportamiento distinto en SQLite y asumir que eso valida producción.

---

# 7. Protocolo obligatorio de ejecución para Codex

Cada fase F07.x/F08.x se ejecuta como un lote independiente.

## 7.1. Antes de modificar código

Codex debe:

1. confirmar rama y commit base;
2. leer esta fase completa;
3. leer los requisitos G/T/P que la fase referencia;
4. inspeccionar los archivos actuales antes de modificarlos;
5. listar en el informe de fase qué archivos espera tocar;
6. ejecutar el baseline de pruebas disponible;
7. no iniciar la fase si la fase anterior no está cerrada.

## 7.2. Durante la implementación

Codex debe:

- limitarse al alcance de la fase;
- no adelantar trabajo de fases futuras;
- no introducir tablas/campos/estados “por si acaso”;
- no eliminar tests para resolver fallos;
- no añadir `skip`/`xfail` a una prueba obligatoria;
- no reducir restricciones de BD para facilitar tests;
- no duplicar lógica que ya es autoridad de un trigger;
- no copiar código de la rama experimental;
- no hacer refactors de idioma globales;
- crear migraciones solo después de fijar nombres/modelos del lote;
- documentar cualquier desviación deliberada.

## 7.3. Gate local antes de commit

Cuando corresponda a la fase:

```bash
uv sync --locked --extra dev
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest -ra
```

Las pruebas DB obligatorias deben ejecutarse contra PostgreSQL.

## 7.4. Gate CI

Una fase no se cierra mientras GitHub Actions no esté completamente verde.

CI debe estar dividido en jobs independientes para que un fallo de estilo no oculte resultados de:

- migraciones;
- tests PostgreSQL;
- concurrencia;
- OpenAPI.

No aceptar “pruebas locales verdes” como sustituto de CI verde.

## 7.5. Informe obligatorio de fase

Cada fase genera:

`docs/implementacion/<FASE>.md`

Debe incluir:

- commit/branch base;
- objetivo;
- archivos modificados;
- migraciones creadas;
- decisiones aplicadas;
- pruebas ejecutadas;
- resultado exacto de cada gate;
- pruebas PostgreSQL;
- pruebas de concurrencia si aplican;
- OpenAPI si aplica;
- riesgos conocidos;
- bloqueos externos;
- confirmación de que no hay skips obligatorios;
- commit final.

No escribir “fase completada” si existe un gate rojo.

---

# 8. Estrategia de ramas

El desarrollo se realiza por ramas pequeñas y verificables.

Patrón recomendado:

```text
main
 ├── feat/f07-0-baseline
 ├── feat/f07-1-db01
 ├── feat/f07-2-db02
 ├── feat/f07-3-db03
 ...
```

Reglas:

- una fase parte de `main` después de fusionar la anterior;
- una PR corresponde a una fase;
- no mezclar F07.2 y F07.3 en la misma PR;
- no comenzar F08 desde una rama no fusionada;
- el merge ocurre solo con CI verde;
- preferir squash/merge limpio según política del repositorio;
- una base local creada con una implementación descartada se recrea; no usar `--fake` para ocultar conflictos.

---

# 9. CI mínimo obligatorio

A partir de F07.0, CI debe tener jobs independientes:

## 9.1. `lint`

```bash
uv sync --locked --extra dev
uv run ruff check .
uv run ruff format --check .
```

## 9.2. `django-check`

```bash
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
```

## 9.3. `postgres-migrations`

Sobre PostgreSQL vacío:

```bash
uv run python manage.py migrate --noinput
uv run python manage.py migrate --noinput
```

La segunda ejecución debe ser no-op.

## 9.4. `tests-postgresql`

Toda la suite Django/ORM/API con PostgreSQL.

## 9.5. `concurrency-postgresql`

Tests marcados específicamente como concurrencia, con conexiones distintas.

## 9.6. `openapi-drift`

Generar a archivo temporal:

```bash
uv run python manage.py spectacular --file /tmp/openapi.yaml --validate
diff -u docs/openapi.yaml /tmp/openapi.yaml
```

Así CI falla si el código y el OpenAPI versionado divergen.

---

# 10. Reglas comerciales no negociables

## 10.1. G01/P29 — precio

Dos modos:

- `PRECIO_UNITARIO`;
- `TOTAL_NEGOCIADO`.

Ejemplo normativo:

```text
cantidad = 3
monto total negociado = 100.00
resultado total = 100.00
```

No convertirlo en 300.00. No falsear descuento ni cantidad.

## 10.2. G02/P30 — nota de entrega

- no se crea al aprobar;
- se emite cuando el pedido está `LISTO_ENTREGA`;
- una por pedido;
- fecha = fecha de emisión;
- entrega física sigue siendo una acción separada.

## 10.3. G03/P31 — recibos

- estados `EMITIDO` y `ANULADO`;
- solo EMITIDOS suman;
- recibo emitido no se borra ni reescribe;
- error se resuelve anulando;
- pedido con recibo EMITIDO no se cancela;
- no implementar devoluciones dentro del sistema.

## 10.4. T01–T09

Todas deben convertirse en tests de regresión. Ninguna se considera “cubierta” solo por código visualmente correcto.

---

# 11. F07.0 — Baseline seguro y nomenclatura congelada

**Objetivo:** crear una base Django reproducible antes de modelar negocio.

**Precondición:** `main` + este plan.

## Alcance permitido

- proyecto/configuración;
- estructura de apps;
- autenticación base;
- dependencias;
- CI;
- health;
- nomenclatura.

## Trabajo obligatorio

1. Adoptar `pyproject.toml` + `uv.lock`; `requirements.txt` no será una segunda fuente manual.
2. Mantener Python 3.11.15.
3. Crear settings `base/local/test/production`.
4. Configurar PostgreSQL por `DATABASE_URL` o contrato único equivalente.
5. Crear `.env.example`, README y Makefile.
6. Configurar DRF, JWT y CORS.
7. Crear `accounts.User` basado en `AbstractUser` y fijar `AUTH_USER_MODEL` antes de migraciones comerciales.
8. Crear/normalizar las apps definitivas:
   - conservar `catalogo`, `clientes`, `proformas`, `pedidos`;
   - `taller` → `ordenes_trabajo`;
   - `entregas` → `notas_entrega`;
   - `pagos` → `recibos`;
   - retirar `ventas`;
   - `nlp` → `capturas`;
   - crear `movimientos_stock`;
   - crear `documentos`;
   - crear `accounts`.
9. Corregir todos los `AppConfig.name`.
10. Crear `/api/v1/health/`.
11. Crear CI por jobs independientes.

## Prohibido

- modelos comerciales;
- migraciones de las 24 tablas;
- Celery/Redis;
- integrar NLP;
- lógica de aprobación;
- copiar implementación de `refactor`.

## Pruebas obligatorias

- instalación desde lock;
- `manage.py check`;
- auth/JWT smoke;
- health 200;
- ningún `INSTALLED_APPS` inexistente;
- lint/formato;
- CI verde.

## Cierre

Crear `docs/implementacion/F07_0_BASELINE.md`.

**No avanzar a F07.1 con CI rojo.**

---

# 12. F07.1 — DB-01: propiedad del esquema y paridad estructural

**Objetivo:** que Django pueda construir desde cero la estructura comercial sin doble bootstrap.

**Precondición:** F07.0 fusionada.

## Distribución de las 24 tablas

- `catalogo`: catálogo y productos;
- `clientes`: clientes;
- `proformas`: proformas, detalle, especificaciones;
- `pedidos`: pedidos y transiciones;
- `ordenes_trabajo`: órdenes de trabajo;
- `notas_entrega`: notas de entrega;
- `recibos`: recibos;
- `documentos`: archivos adjuntos;
- `capturas`: capturas, intentos, outbox, IA, humano, evaluaciones, mediciones;
- `movimientos_stock`: movimientos de stock.

En esta fase las tablas de F08 pueden existir estructuralmente si así lo exige la migración integral, pero **no se implementa todavía su flujo de aplicación**.

## Trabajo obligatorio

1. Modelar exactamente las 24 tablas.
2. Mantener `db_table` con los nombres del SQL.
3. Mapear actores a `settings.AUTH_USER_MODEL`.
4. Crear las cuatro secuencias mediante migraciones versionadas.
5. Trasladar funciones/triggers v3 por grupos mediante `RunSQL` o migraciones equivalentes claras.
6. Crear un manifiesto `docs/base_datos/mapa_sql_modelos.md`.
7. Documentar diferencias intencionales v3 → requisitos finales.
8. Crear schema dump normalizado de prueba o verificador equivalente.
9. No ejecutar el SQL v3 como bootstrap junto con las migraciones.

## Pruebas obligatorias

Sobre PostgreSQL vacío:

- `migrate` exitoso;
- segundo `migrate` sin cambios;
- 24 tablas presentes;
- cuatro secuencias presentes;
- FK y checks estructurales clave;
- actores apuntan al user configurado;
- `makemigrations --check --dry-run` sin cambios;
- schema diff documentado.

## Prueba destructiva controlada

Crear una BD descartable, migrar, destruirla, crear otra y repetir. El resultado debe ser reproducible.

## Cierre

`docs/implementacion/F07_1_DB_01.md`.

---

# 13. F07.2 — DB-02: clientes, catálogo y proforma manual

**Objetivo:** construir la cotización manual completa sin NLP.

**Precondición:** F07.1 cerrada.

## Trabajo obligatorio

- modelos/servicios/API de clientes;
- catálogo universal;
- productos silla/piso/OTRO;
- promociones simples;
- proformas y detalles;
- especificaciones de mueble;
- `PRECIO_UNITARIO/TOTAL_NEGOCIADO`;
- BOB/USD sin conversión;
- snapshots;
- envío de proforma;
- T01, T02, T03 y T04;
- demanda pendiente solo como referencia.

## Autoridad

Totales e invariantes deben resistir escritura directa concurrente. No confiar solamente en serializer/frontend.

## Tests obligatorios

### Precio

- 3 por 100 → 100.00 exactos;
- 2 × 50 − 5 → 95.00;
- no float monetario;
- modo inválido rechazado.

### T01

Intentar alterar directamente subtotal/total/descuento y comprobar protección/recalculo definido.

### T02

- BORRADOR permite cambio permitido;
- primera ENVIADA congela cliente/snapshot;
- cambios posteriores rechazados.

### T03

- detalle no cambia de proforma;
- especificaciones congeladas cuando corresponda.

### T04

Dos conexiones PostgreSQL: edición y envío/aprobación deben serializarse correctamente.

### API/permisos

- vendedor autorizado;
- usuario sin rol → 403;
- otro vendedor no accede a objeto ajeno;
- administración según matriz.

## OpenAPI

Regenerar y pasar `openapi-drift`.

## Cierre

`docs/implementacion/F07_2_DB_02.md`.

---

# 14. F07.3 — DB-03: aprobación, pedidos, movimientos de stock y OT

**Objetivo:** implementar el núcleo transaccional de la venta.

**Precondición:** F07.2 cerrada.

## Regla crítica de autoridad

El SQL v3 define la cadena de aprobación mediante triggers, incluyendo:

- aprobación de proforma;
- creación de pedido;
- VENTA(s);
- actualización de stock;
- creación de OT.

La implementación Django **no debe crear manualmente esos mismos efectos si PostgreSQL ya es su autoridad**.

El servicio Django debe:

1. autorizar;
2. abrir `transaction.atomic()`;
3. bloquear la proforma con `SELECT ... FOR UPDATE`;
4. validar precondiciones que correspondan al caso de uso;
5. ejecutar la transición autoritativa;
6. dejar que la cadena SQL cree sus efectos;
7. consultar el resultado;
8. devolverlo.

No duplicar pedido, movimiento u OT desde Python.

## Cancelación

La transición a `CANCELADO` debe activar una única `REVERSA_VENTA` por VENTA según T05. No crear reversas adicionales en Python si la BD es autoridad.

## Tests obligatorios PostgreSQL

- aprobación válida → exactamente 1 pedido;
- exactamente movimientos VENTA esperados;
- exactamente 1 OT;
- stock final correcto;
- stock insuficiente → rollback total;
- ningún pedido/VENTA/OT parcial;
- dos vendedores compiten por última unidad → solo uno gana;
- aprobación doble de la misma proforma no duplica efectos;
- transición no permitida rechazada;
- cancelación válida devuelve stock;
- segunda cancelación/reversa rechazada;
- T05 directo y concurrente;
- acceso taller según permisos.

## Prueba de paridad

Para la cadena de triggers trasladada, documentar qué funciones/triggers v3 se preservaron y qué cambios fueron necesarios por G/T.

## Cierre

`docs/implementacion/F07_3_DB_03.md`.

---

# 15. F07.4 — DB-05: recibos, notas de entrega y documentos

**Objetivo:** cerrar el flujo comercial manual posterior a aprobación.

**Precondición:** F07.3 cerrada.

## Recibos

Implementar G03/T06:

- `EMITIDO`;
- `ANULADO`;
- no DELETE;
- no UPDATE comercial;
- solo transición EMITIDO → ANULADO;
- acumulados/saldo solo con EMITIDOS;
- cobro solo sobre pedido válido;
- sobrepago imposible;
- cobro/anulación/cancelación bloquean el mismo pedido.

## Notas de entrega

Implementar G02:

- no crear al aprobar;
- solo desde `LISTO_ENTREGA`;
- exactamente una por pedido;
- fecha de emisión;
- emisión no equivale a entrega física.

## Documentos

Renderizar:

- proforma;
- orden de trabajo;
- recibo;
- nota de entrega.

No crear `documentos_emitidos`, `contadores` ni tablas rechazadas.

## Tests obligatorios PostgreSQL

- recibo correcto;
- sobrepago rechazado;
- dos cobros concurrentes que superarían saldo → solo combinación válida;
- recibo emitido bloquea cancelación;
- anulado deja de sumar;
- evidencia del recibo no se modifica;
- DELETE directo rechazado;
- nota desde estado incorrecto rechazada;
- nota única;
- dos emisiones concurrentes → una sola;
- secuencias comerciales sin duplicados bajo concurrencia;
- los cuatro documentos renderizan datos persistidos.

## Cierre

`docs/implementacion/F07_4_DB_05.md`.

---

# 16. F07.5 — DB-06: catálogo operativo real

**Objetivo:** importar catálogo comercial sin inventar información.

**Precondición:** F07.2 cerrada; puede ejecutarse después de F07.4 para simplificar secuencia.

## Regla de formato

El dataset NER de sillas **NO es catálogo comercial**.

El importador comercial debe tener un único esquema de entrada documentado. Preferencia inicial: JSON estructurado versionado.

Si se decide aceptar otro formato, debe agregarse como feature explícita con tests propios. No aceptar silenciosamente JSONL de entrenamiento como catálogo.

## Datos requeridos

No inventar:

- SKU;
- precio;
- stock;
- marca;
- presentación/color;
- unidad.

## Stock inicial

Producto nuevo comienza en stock 0 y la carga se representa con `CARGA_INICIAL` en `movimientos_stock`.

## Tests obligatorios

- dry-run no persiste;
- archivo válido crea exactamente lo esperado;
- segunda ejecución es idempotente;
- SKU duplicado rechazado;
- ficha incompleta rechazada;
- catálogo NER/JSONL no comercial se rechaza con error claro, nunca con crash;
- carga inicial no puede repetirse;
- promoción vigente seleccionada correctamente;
- demanda pendiente no modifica stock;
- stock 8, pendientes 3 → referencia 5;
- rollback completo ante un error en lote.

## Cierre

Si faltan datos reales de HOMEX, la fase puede cerrarse como **implementación lista / carga real bloqueada por insumo**, siempre que importador y tests estén completos.

`docs/implementacion/F07_5_DB_06.md`.

---

# 17. F07.6 — DB-07: endurecimiento y cierre real de F07

**Objetivo:** demostrar que el backend manual está preparado para ser base de producción antes de integrar NLP.

**Precondición:** F07.1–F07.5 cerradas.

## Trabajo obligatorio

- rol migrador/propietario separado de rol runtime;
- privilegios mínimos;
- matriz de permisos;
- índices/queries críticas;
- CI completa;
- OpenAPI estable;
- README actualizado;
- `docs/arquitectura.md`;
- `docs/migraciones.md`;
- `docs/permisos.md`;
- `docs/guia_operacion.md`;
- pruebas de regresión G01–G03 y T01–T06;
- recorrido manual extremo a extremo.

## Gate F07 completo

Deben estar verdes simultáneamente:

- lint;
- format;
- Django check;
- cero migraciones pendientes;
- PostgreSQL vacío → migrate;
- segunda migrate no-op;
- toda la suite PostgreSQL;
- concurrencia;
- OpenAPI sin drift;
- permisos;
- recorrido E2E manual.

Recorrido mínimo:

```text
login
→ cliente
→ catálogo/proforma
→ enviar
→ aprobar
→ pedido + VENTA + OT
→ recibo
→ LISTO_ENTREGA
→ nota de entrega
```

También probar cancelación válida sin recibo emitido.

## Condición de salida

**F07 solo se declara completa si CI remoto está verde.**

No iniciar F08 con F07 parcialmente verde.

---

# 18. F08.0 — Contrato backend ↔ homex-nlp

**Objetivo:** integrar el paquete sin persistencia todavía.

**Precondición:** F07 completa + F06 NLP completada.

## Trabajo

- fijar una versión/wheel exacta de `homex-nlp`;
- adapter explícito;
- validar `schema_version`;
- comenzar en `RULES_ONLY`;
- mapear contrato externo al dominio español;
- no renombrar campos públicos de `homex_nlp`.

## Tests

- importación sin side effects;
- versión soportada funciona;
- versión desconocida falla explícitamente;
- campos adicionales no aceptados si contrato los prohíbe;
- fixture v1 se transforma sin perder evidencia;
- backend no exige NER experimental.

## Cierre

`docs/implementacion/F08_0_CONTRATO_NLP.md`.

---

# 19. F08.1 — DB-04: capturas, intentos, outbox e idempotencia

**Objetivo:** persistir recepción y trabajo pendiente de forma recuperable.

## Reglas

- `clave_idempotencia` única;
- mismo contenido/actor/proforma recupera captura;
- misma clave incompatible → 409;
- intento numerado bajo bloqueo;
- trigger crea exactamente un outbox;
- Django no crea un segundo outbox;
- T07/T09.

## Tests PostgreSQL

- POST inicial → 202;
- repetición idéntica → misma captura;
- conflicto → 409;
- dos POST concurrentes con misma clave → una captura;
- intento → un outbox;
- intento cerrado inmutable;
- item IA cerrado inmutable.

---

# 20. F08.2 — Worker, Redis, ASR y audio efímero

**Objetivo:** procesar de forma asíncrona sin convertir Redis en fuente de verdad.

## Reglas

- audio temporal privado;
- fuera de backups;
- borrar inmediatamente después de ASR;
- reintento NLP usa texto, no audio;
- Redis caído no pierde trabajo;
- reentrega segura;
- worker tardío no reescribe intento cerrado;
- limpieza de huérfanos separada.

## Tests

- Redis indisponible;
- redelivery;
- worker crash;
- audio eliminado en éxito;
- audio eliminado/expirado en fallo según política;
- ausencia de endpoint histórico de audio;
- reconciliación de outbox.

---

# 21. F08.3 — HITL y confirmación

**Objetivo:** convertir propuesta IA en corrección humana trazable sin aprobar comercialmente la proforma.

## Reglas

- navegador no es autoridad del original IA;
- original se recupera del servidor;
- una corrección final por relación;
- una evaluación versionada;
- corrección + evaluación + detalle/especificación + vínculo en una misma transacción;
- confirmar captura NO aprueba proforma.

## Tests

- payload IA manipulado por navegador no sustituye original;
- propuesta parcial corregible;
- doble confirmación idempotente/rechazada según contrato;
- error transaccional no deja mitad de evidencia;
- aprobación comercial sigue siendo acción separada.

---

# 22. F08.4 — Resiliencia y cierre F08

Matriz obligatoria:

- DB;
- Redis;
- archivo temporal;
- ASR;
- NLP;
- worker;
- reintento;
- contrato incompatible.

Debe existir test de integración con:

- PostgreSQL real;
- Redis real;
- worker real;
- wheel fijado de NLP.

F08 no se cierra con mocks únicamente.

---

# 23. F09 — Integración con frontend

**Precondición:** F07/F08 cerradas.

- OpenAPI es contrato;
- no crear endpoints ad hoc para compensar lógica frontend;
- frontend no calcula autoridad de stock/totales/permisos;
- editor mixto;
- taller;
- pagos;
- entrega;
- captura/HITL;
- documentos HOMEX reales.

E2E compartido obligatorio.

---

# 24. F10 — Despliegue y recuperación

Antes de producción:

- imagen API;
- imagen worker;
- PostgreSQL versionado;
- Redis;
- health/readiness;
- migración controlada;
- rollback compatible;
- backups PostgreSQL;
- audio excluido de backup;
- restore ensayado;
- logs/metrics;
- secretos externos;
- HTTPS;
- manifiesto de versiones backend/NLP.

**No declarar listo para producción sin restauración probada.**

---

# 25. F11 — Piloto y cierre

- fijar versiones;
- medición MANUAL vs NLP_HITL;
- regresión de defectos del piloto;
- métricas sin audio histórico;
- documentación final;
- incidencias críticas = 0 antes de cierre productivo.

---

# 26. Matriz mínima de regresión

| Regla | Test obligatorio |
|---|---|
| G01 | 3 × total negociado 100 = 100.00 |
| G02 | nota solo desde LISTO_ENTREGA |
| G03 | EMITIDO bloquea cancelación; ANULADO no suma |
| T01 | totales no adulterables |
| T02 | cliente/snapshot congelado desde ENVIADA |
| T03 | detalle no migra; especificación congelada |
| T04 | lock real de proforma |
| T05 | una sola REVERSA_VENTA |
| T06 | recibo inmutable salvo anulación |
| T07 | IA/intento cerrado inmutable |
| T08 | promoción/JSON validado sin requisitos inventados |
| T09 | idempotencia HTTP única |
| P22 | pendientes informativos, no reserva |
| P32 | SKU por presentación con stock propio |

Cada test debe indicar si es unitario, API, integración o concurrencia. T04/T05/T06/T09 requieren PostgreSQL real donde aplique.

---

# 27. Reglas de migraciones para producción

1. Nunca editar una migración ya desplegada en producción.
2. Durante F07, antes de existir producción, se puede reconstruir una migración solo dentro de su fase y antes de fusionarla.
3. Una vez una fase con migraciones se fusiona a `main`, cambios posteriores se hacen con nuevas migraciones.
4. No usar `--fake` para resolver conflictos de desarrollo sin un procedimiento documentado.
5. No borrar tablas/columnas con datos sin migración de datos y plan de rollback.
6. Todo `RunSQL` debe tener reverse cuando sea seguro o documentar por qué no.
7. Probar migración desde vacío y upgrade desde la última versión aceptada.
8. Antes de producción, probar backup + migrate + smoke + rollback/restore.

---

# 28. Prohibiciones de diseño

No reintroducir:

- `proforma_grupos`;
- `proforma_versiones`;
- `movimientos_pago`;
- `documentos_emitidos`;
- `contadores`;
- `eventos_auditoria`;
- reservas de stock por proforma;
- conversiones automáticas BOB/USD;
- entregas parciales;
- múltiples notas por pedido;
- devoluciones dentro del flujo actual;
- NLP como autoridad comercial;
- audio histórico.

No inventar campos para resolver una incomodidad de implementación.

---

# 29. Insumos externos pendientes

No bloquear desarrollo técnico por datos que legítimamente aún no existen, pero tampoco inventarlos.

Pendientes conocidos:

- SKU/precio/color/stock comercial real de sillas;
- catálogo real de pisos/OTRO/promociones;
- formatos físicos definitivos de los cuatro documentos;
- audios reales para evaluación;
- RPO/RTO y política formal de retención antes de producción.

Una fase que dependa de un insumo puede cerrar como “implementación validada; carga/piloto bloqueado por insumo”, pero debe demostrar completamente la parte implementable.

---

# 30. Definición de terminado de una fase

Una fase está terminada únicamente cuando:

- [ ] el alcance implementado coincide con el plan;
- [ ] no incluye funcionalidades de fases futuras;
- [ ] nombres respetan la convención congelada;
- [ ] no existen migraciones pendientes;
- [ ] lint verde;
- [ ] format verde;
- [ ] `manage.py check` verde;
- [ ] tests obligatorios verdes;
- [ ] PostgreSQL obligatorio verde;
- [ ] concurrencia verde cuando aplica;
- [ ] OpenAPI sin drift cuando aplica;
- [ ] no hay skips de pruebas obligatorias;
- [ ] CI remoto completamente verde;
- [ ] documentación de fase actualizada;
- [ ] no existe un riesgo crítico conocido sin documentar;
- [ ] commit/PR de la fase contiene solo su alcance.

---

# 31. Definición de terminado del backend antes de producción

Además del cierre F07–F11:

- [ ] restore PostgreSQL probado;
- [ ] migraciones de release probadas sobre copia representativa;
- [ ] permisos runtime mínimos;
- [ ] secretos fuera de Git;
- [ ] health/readiness;
- [ ] logs sin datos sensibles indebidos;
- [ ] OpenAPI corresponde exactamente a release;
- [ ] backend y NLP fijados por versión;
- [ ] E2E crítico verde;
- [ ] pruebas de concurrencia críticas verdes;
- [ ] audio no persiste;
- [ ] no existen errores críticos/altos abiertos para producción;
- [ ] rollback o procedimiento de restauración ensayado.

---

# 32. Secuencia de ejecución

```text
MAIN + Plan 2.0
      ↓
F07.0 baseline + nombres definitivos
      ↓
F07.1 esquema/migraciones
      ↓
F07.2 cliente + catálogo + proforma
      ↓
F07.3 aprobación + pedido + stock + OT
      ↓
F07.4 recibos + nota + documentos
      ↓
F07.5 importador catálogo
      ↓
F07.6 endurecimiento + cierre manual
      ↓
F08.0 contrato NLP
      ↓
F08.1 capturas/outbox
      ↓
F08.2 worker/ASR
      ↓
F08.3 HITL
      ↓
F08.4 resiliencia
      ↓
F09 frontend
      ↓
F10 deploy/restore
      ↓
F11 piloto
```

**Principio final:** no “forzar” una fase hasta que parezca funcionar. Si una prueba revela una contradicción de diseño, se corrige la definición antes de consolidar migraciones o contratos. El objetivo no es avanzar rápido por la numeración; es que cada etapa aceptada se convierta en una base estable para la siguiente.
