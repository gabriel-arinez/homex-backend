# Plan maestro de implementación e integración — HOMEX Backend

**Fecha:** 16 de septiembre de 2026  
**Versión del plan:** 1.0  
**Repositorio:** `gabriel-arinez/homex-backend`  
**Rama revisada:** `main`  
**Punto de partida:** commit `39e64ff1617e357e093a70c54b59b5513ad63d5d` (`add: Cargar la base de datos`)  
**Repositorios coordinados:** `homex-backend/main` + `homex-nlp/refactor`  
**Baseline Python común:** 3.11.15  
**Objetivo:** llevar el backend desde el esqueleto Django actual hasta un backend comercial reproducible, probado y dueño de PostgreSQL, compatible con el contrato versionado de `homex-nlp`, listo para frontend, despliegue y piloto.

---

## 0. Cómo utilizar este documento

Este es el documento rector del backend. Debe leerse junto con los documentos vigentes de `homex-nlp/refactor`, en especial:

- `docs/PLAN_MAESTRO_REFACTORIZACION_HOMEX.md`;
- `docs/architecture.md`;
- `docs/integration-django.md`;
- `docs/contract-v1.md`;
- `docs/requirements.md`;
- `docs/configuration.md`;
- informes `F00` a `F06`.

El plan del NLP define la arquitectura global y asigna al backend principalmente las fases **F07 y F08**, además de responsabilidades en F09–F11. Este documento descompone esas fases en lotes ejecutables y verificables a partir del estado real de `homex-backend/main`.

No se considera completada una fase por crear archivos, apps o tablas. Cada fase tiene una condición de salida que debe demostrarse mediante pruebas, migraciones, contratos o recorridos ejecutables.

### 0.1. Jerarquía de autoridad

Mientras se implementa el backend, la precedencia es:

1. decisiones finales consolidadas en `homex-nlp/docs/requirements.md` (G01–G03, T01–T09 y P29–P32, además de P01–P28 no revocados);
2. contrato `homex-nlp` v1 para extracción/HITL;
3. plan maestro vigente de `homex-nlp/refactor`;
4. `homex_bd_final_v3.sql` como referencia estructural inicial;
5. una vez formalizado F07, **las migraciones Django del backend pasan a ser la fuente operativa única del esquema**.

El SQL v3 no se ejecutará además de migraciones que creen las mismas tablas. `inspectdb` puede utilizarse como herramienta de auditoría/comparación, pero no como arquitectura definitiva basada en modelos `managed=False`.

### 0.2. Alcances que no deben mezclarse

| Alcance | Responsable | Regla |
|---|---|---|
| Extracción ASR/NLP | `homex-nlp` | Paquete Python versionado; no importa Django/Celery/ORM ni persiste negocio. |
| Negocio, autenticación y persistencia | `homex-backend` | Django/DRF y PostgreSQL son autoridad comercial. |
| Trabajo asíncrono | worker del backend | Instala una versión fijada de `homex-nlp`; persiste mediante servicios del backend. |
| UI | futuro `homex-frontend` | Consume OpenAPI; no decide stock, permisos ni totales definitivos. |
| Operación | futuro `homex-deploy` | Versiona API, worker, frontend, DB, Redis, proxy, backups y recuperación. |

---

# 1. Diagnóstico del repositorio actual

## 1.1. Estado general

El repositorio existe y ya contiene una base técnica inicial, pero **todavía no constituye un backend ejecutable ni un backend comercial**. Está aproximadamente en la preparación previa a F07: dependencias instaladas, proyecto Django generado, intención modular creada, CORS iniciado y SQL v3 copiado.

El recorrido actual todavía no implementa autenticación HOMEX, modelos comerciales, migraciones propietarias, API REST, servicios de negocio, permisos, Celery, outbox, integración NLP, tests, OpenAPI ni CI.

## 1.2. Elementos aprovechables

- `.python-version` fija **3.11.15**, igual al baseline comprobado de `homex-nlp`.
- Django 5.2.17, DRF 3.18.1, psycopg 3, Celery 5.6.3, Redis, SimpleJWT y CORS están presentes en `requirements.txt`.
- Existe separación `config/` + `apps/`.
- El proyecto apunta a PostgreSQL, no SQLite.
- `homex_bd_final_v3.sql` está versionado.
- El blob SHA del SQL v3 en backend es el mismo que el del SQL conservado en `homex-nlp/refactor`: ambos repositorios parten hoy de la misma referencia.
- CORS ya contempla `http://localhost:5173` como origen local del futuro Vue.
- Las apps creadas muestran intención de separar catálogo, clientes, proformas, pedidos, taller, entregas y pagos.

## 1.3. Defectos bloqueantes actuales

### B01 — `settings.py` referencia una app inexistente

`INSTALLED_APPS` contiene `apps.usuarios`, pero el repositorio no tiene `apps/usuarios/`. Con el checkout actual Django no puede construir correctamente el registro de aplicaciones.

### B02 — Los `AppConfig` generados usan rutas incorrectas

Por ejemplo `apps/catalogo/apps.py` declara:

```python
name = "catalogo"
```

pero el paquete real es `apps.catalogo`. El patrón debe corregirse en todas las apps que se conserven, o las apps deben recrearse/renombrarse antes de desarrollar modelos.

### B03 — La configuración de PostgreSQL no lee las variables esperadas

Actualmente se usa, por ejemplo:

```python
"NAME": os.getenv("homex")
"USER": os.getenv("homex_user")
"HOST": os.getenv("127.0.0.1")
```

Eso interpreta los valores como **nombres de variables de entorno**, no como valores ni como `DB_NAME`, `DB_USER`, `DB_HOST`. Debe existir un contrato de configuración explícito y validado.

### B04 — No existe modelo de usuario ni estrategia de roles

El SQL v3 deja deliberadamente los actores como `*_by_id BIGINT` para relacionarlos después con `settings.AUTH_USER_MODEL`. Ese traslado todavía no existe. Debe resolverse **antes** de consolidar las primeras migraciones de autenticación del backend.

### B05 — Las apps son esencialmente stubs de `startapp`

Los `models.py`, `views.py`, `tests.py` y `admin.py` revisados conservan el contenido generado por Django. No hay serializadores, servicios, queries, permisos ni URLConfs de dominio.

### B06 — DRF y JWT están instalados pero no configurados

`config/urls.py` expone únicamente `/admin/`. No existen `/api/v1/`, login JWT, refresh, routers ni endpoints comerciales. Tampoco existe `REST_FRAMEWORK` con políticas por defecto.

### B07 — Celery/Redis están instalados pero no integrados

No existen `config/celery.py`, configuración del broker, tasks, publicador outbox, reconciliación ni worker del backend. `config/__init__.py` está vacío.

### B08 — El backend no es todavía dueño del esquema

El SQL v3 es un script DDL completo, con `BEGIN`, secuencias, tablas, funciones y triggers. No es una migración idempotente. Ejecutarlo sobre una base que ya contiene objetos produce conflictos. El objetivo de F07 es trasladar el diseño a migraciones Django/RunSQL ordenadas y comprobables desde una base vacía.

### B09 — Faltan las ampliaciones aprobadas posteriores a v3

El propio plan del NLP establece que el SQL v3 preservado **no contiene todavía** todas las decisiones finales. Deben entrar mediante migraciones, entre otras:

- `modo_calculo = PRECIO_UNITARIO | TOTAL_NEGOCIADO` e `importe_negociado`;
- estado de recibo `EMITIDO | ANULADO` e inmutabilidad correspondiente;
- `capturas.clave_idempotencia` única;
- protecciones T01–T09;
- relaciones de actores con `AUTH_USER_MODEL`.

### B10 — La estructura de apps actual no coincide con la arquitectura ya acordada

El plan rector del NLP propuso módulos `accounts`, `catalog`, `customers`, `quotations`, `captures`, `orders`, `inventory`, `workshop`, `deliveries`, `payments` y `documents`.

El backend actual usa nombres distintos y además incluye `apps/ventas` y `apps/nlp`. Como las apps están vacías, **este es el momento de alinear la estructura**, antes de crear migraciones difíciles de renombrar.

- `apps/nlp` no debe alojar el motor NLP: debe convertirse en `captures`/integración.
- no se necesita una app comercial separada `ventas` si la VENTA es el tipo de movimiento de stock generado por aprobación;
- falta un módulo explícito de inventario;
- falta el módulo de documentos/plantillas.

### B11 — No existe disciplina de proyecto equivalente al repositorio NLP

Faltan, como mínimo:

- `README.md`;
- `.env.example`;
- `pyproject.toml` y lock reproducible;
- `Makefile` o comandos equivalentes;
- `.github/workflows/ci.yml`;
- `docs/` hasta la creación de este plan;
- tests organizados por integración/API/concurrencia/contratos;
- OpenAPI;
- Dockerfile;
- runbook y documentación de migraciones/permisos.

## 1.4. Dictamen

El backend está **bien encaminado como esqueleto**, pero el siguiente paso no debe ser crear CRUDs al azar ni mapear el SQL con `managed=False`. Primero hay que convertirlo en un proyecto reproducible, arrancable y alineado con los contratos de NLP; después formalizar PostgreSQL por lotes y construir el recorrido comercial manual completo. La integración ASR/NLP comienza solo cuando ese flujo comercial ya funciona sin IA.

---

# 2. Decisiones arquitectónicas consolidadas

## 2.1. Arquitectura objetivo

```text
Vue
  │ HTTPS / JSON
  ▼
Django + DRF
  │
  ├──────────────► PostgreSQL
  │                  │
  │                  └── outbox
  │
  ├── audio temporal privado
  │
  └── publicador outbox ─► Redis ─► Worker Django
                                    │
                                    ├── homex-nlp fijado por versión
                                    ├── ASR
                                    ├── extracción
                                    └── servicios backend ─► PostgreSQL
```

### Propiedad

- Django autentica, autoriza, valida casos de uso y persiste.
- PostgreSQL protege invariantes relacionales/económicas y concurrencia.
- Redis transporta trabajo; **no es fuente de verdad**.
- Celery ejecuta trabajo asíncrono; **no crea un segundo dominio**.
- `homex-nlp` propone y conserva evidencia; no aprueba, no cobra y no reserva stock.
- Vue presenta y edita; no decide reglas de negocio.

## 2.2. Monolito modular

El backend será un único proyecto desplegable como API y worker, dividido por responsabilidades. No se introducirán microservicios por módulo.

## 2.3. PostgreSQL como autoridad de integridad

Django no debe competir con los triggers escribiendo dos veces las mismas consecuencias.

Ejemplo de aprobación:

1. servicio Django abre `transaction.atomic()`;
2. autoriza y bloquea la proforma (`SELECT ... FOR UPDATE`);
3. valida las condiciones comerciales;
4. cambia la proforma a APROBADA;
5. los triggers crean pedido CONFIRMADO, VENTA(s) y OT;
6. si stock falla, PostgreSQL revierte todo;
7. Django consulta y devuelve el resultado; no vuelve a crear pedido/VENTA/OT.

## 2.4. Manual primero, NLP después

Debe ser posible completar el recorrido:

```text
cliente → proforma → líneas manuales/catálogo → aprobación
       → pedido → stock → OT → recibo → entrega/cancelación permitida
```

sin que Redis, Celery, ASR o NLP estén disponibles.

---

# 3. Estructura objetivo del repositorio

Para coordinar con el plan de `homex-nlp`, se adopta su estructura conceptual. Los nombres físicos de tablas PostgreSQL permanecen en español mediante `db_table`; renombrar apps Python no cambia la base.

```text
homex-backend/
├── manage.py
├── pyproject.toml
├── uv.lock
├── .python-version
├── .env.example
├── Makefile
├── README.md
├── config/
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── local.py
│   │   ├── test.py
│   │   └── production.py
│   ├── urls.py
│   ├── celery.py
│   ├── asgi.py
│   └── wsgi.py
├── apps/
│   ├── accounts/
│   ├── catalog/
│   ├── customers/
│   ├── quotations/
│   ├── captures/
│   ├── orders/
│   ├── inventory/
│   ├── workshop/
│   ├── deliveries/
│   ├── payments/
│   └── documents/
├── sql/
│   ├── catalogs.sql
│   ├── quotations.sql
│   ├── stock.sql
│   ├── orders.sql
│   ├── receipts.sql
│   └── captures.sql
├── templates/documents/
│   ├── quotation.html
│   ├── work_order.html
│   ├── delivery.html
│   └── receipt.html
├── tests/
│   ├── api/
│   ├── contracts/
│   ├── integration/
│   ├── concurrency/
│   └── e2e/
├── docs/
│   ├── PLAN_MAESTRO_BACKEND_HOMEX.md
│   ├── architecture.md
│   ├── api-contract.md
│   ├── migrations.md
│   ├── permissions.md
│   └── runbook.md
├── Dockerfile
└── .github/workflows/ci.yml
```

### 3.1. Responsabilidad de los módulos

| Módulo | Responsabilidad |
|---|---|
| `accounts` | `AUTH_USER_MODEL`, grupos/roles, permisos y actor de sesión. |
| `catalog` | catálogos universales, productos, sillas, pisos, promociones e importador. |
| `customers` | clientes persona/empresa y reglas de actividad. |
| `quotations` | proformas, detalles, especificaciones, precios, snapshots, envío/aprobación. |
| `captures` | captura, intentos, outbox, IA, corrección humana, evaluación, audio temporal y adapter NLP. |
| `orders` | pedido y máquina de estados. |
| `inventory` | movimientos, stock proyectado, demanda pendiente y reversas. |
| `workshop` | OT y asignación/avance de taller. |
| `deliveries` | emisión de nota y transición de entrega. |
| `payments` | recibos, saldos, anulación por error y bloqueo de sobrepago. |
| `documents` | render de los cuatro documentos; sin tabla/numerador propio. |

### 3.2. Patrón interno

Una app de dominio podrá contener:

```text
models.py
services.py
queries.py
serializers.py
views.py
urls.py
permissions.py
admin.py
migrations/
tests/
```

- `views`: HTTP y traducción de errores;
- `serializers`: contrato API y validación de forma;
- `services`: casos de uso/transacciones;
- `queries`: lectura/proyecciones complejas;
- `permissions`: autorización;
- `models`: persistencia y relaciones;
- PostgreSQL: invariantes que deben resistir escrituras concurrentes/directas.

---

# 4. Configuración y reproducibilidad

## 4.1. Python y dependencias

Mantener Python `3.11.15`, igual a NLP. Adoptar `uv` y lock reproducible para coordinar ambos repositorios.

`pyproject.toml` debe declarar **dependencias directas**, no copiar ciegamente `pip freeze`.

Grupos sugeridos:

- runtime: Django, DRF, psycopg, cors, SimpleJWT, Celery, Redis, configuración;
- `dev`: pytest/pytest-django, ruff, cobertura, OpenAPI tooling;
- integración NLP: wheel/version fijada de `homex-nlp`;
- producción: servidor ASGI/WSGI según despliegue.

## 4.2. Variables de entorno

Contrato mínimo:

```text
DJANGO_SETTINGS_MODULE
DJANGO_SECRET_KEY
DJANGO_DEBUG
DJANGO_ALLOWED_HOSTS
DATABASE_URL   o DB_NAME/DB_USER/DB_PASSWORD/DB_HOST/DB_PORT
REDIS_URL
CORS_ALLOWED_ORIGINS
HOMEX_NLP_MODE
HOMEX_NER_MODEL_PATH
HOMEX_NER_MODEL_SHA256
HOMEX_DOMAIN_PROFILE_VERSION
HOMEX_ASR_MODEL_PATH
HOMEX_ASR_DEVICE
HOMEX_ASR_COMPUTE_TYPE
HOMEX_ASR_CPU_THREADS
AUDIO_TEMP_DIR
```

El backend compone `RuntimeSettings` del paquete NLP; el paquete no lee `.env` al importar.

## 4.3. Settings separados

- `base.py`: apps, DRF, auth, logging, reglas comunes;
- `local.py`: DEBUG, hosts/orígenes locales;
- `test.py`: DB de test, Celery eager solo en tests que lo justifiquen;
- `production.py`: secure cookies/headers, hosts explícitos, secretos externos.

---

# 5. Autenticación, autorización y actores

## 5.1. Usuario propio desde el inicio

Crear `accounts.User` antes de consolidar migraciones de auth y fijar:

```python
AUTH_USER_MODEL = "accounts.User"
```

La autorización funcional debe utilizar permisos/grupos explícitos; no confiar en que el frontend oculte botones.

Roles operativos iniciales a representar según el flujo vigente:

- administración;
- vendedor;
- taller/jefe de taller.

El detalle exacto de permisos se documenta en `docs/permissions.md` y se prueba endpoint por endpoint.

## 5.2. Actores SQL

Los `created_by_id`, `updated_by_id`, vendedor, jefe_taller, revisor, operador y `evaluated_by` del diseño v3 se trasladan a FK hacia `settings.AUTH_USER_MODEL`, respetando nulabilidad y `on_delete` coherente con preservación histórica.

---

# 6. Estrategia de base de datos y migraciones

## 6.1. Regla principal

`homex_bd_final_v3.sql` es **baseline de comparación**, no una segunda fuente operativa después de F07.

El backend debe poder ejecutar desde una PostgreSQL vacía:

```bash
uv run python manage.py migrate
```

y producir el esquema esperado, sin cargar además el DDL completo.

## 6.2. Lotes DB-01 a DB-07

Se conservan los lotes definidos en el plan rector del NLP.

### DB-01 — identidad y estructura base

- `accounts.User` y roles/permisos;
- 24 tablas comerciales por dependencia;
- FK de actores;
- cuatro secuencias comerciales;
- seeds estructurales por código.

**Verificación:** migración desde vacío y comparación de nombres/tipos/restricciones principales.

### DB-02 — catálogo, clientes y proformas

- catálogo universal;
- productos y especializaciones;
- promoción simple;
- clientes;
- proformas, detalles y especificaciones;
- G01 `PRECIO_UNITARIO/TOTAL_NEGOCIADO`;
- T01–T04 donde correspondan;
- snapshots y freeze desde ENVIADA/APROBADA.

**Verificación:** 3 por 100 = 100.00 exacto; edición concurrente serializada; totales no adulterables.

### DB-03 — pedidos, stock y taller

- aprobación basada en triggers;
- pedido CONFIRMADO;
- VENTA(s) de stock;
- OT automática;
- máquina de estados;
- cancelación y REVERSA_VENTA única;
- T05.

**Verificación:** éxito atómico, rollback por stock insuficiente y carrera real con dos conexiones.

### DB-04 — capturas e HITL

- `capturas`;
- `intentos_captura`;
- `trabajos_outbox`;
- `items_ia`;
- `items_humano`;
- `evaluaciones_nlp`;
- `mediciones_proceso`;
- T07/T09.

**Verificación:** outbox exactamente una vez por intento; reentrega no duplica IA; evidencia cerrada inmutable.

### DB-05 — recibos, notas y documentos

- G02: nota solo al emitir para entregar desde `LISTO_ENTREGA`;
- G03: recibo `EMITIDO/ANULADO`;
- T06;
- sobrepago solo con EMITIDOS;
- cuatro secuencias comerciales y snapshots.

**Verificación:** no cancelar con recibos EMITIDOS; ANULADO no cuenta; no se reescribe el recibo original.

### DB-06 — catálogo operativo

- selección de promoción;
- demanda pendiente referencial;
- importador de sillas;
- alta con stock cero y `CARGA_INICIAL` real.

**Verificación:** dry-run, idempotencia de importación, no inventar SKU/precio/stock/color.

### DB-07 — endurecimiento

- rol migrador/propietario separado del runtime;
- permisos mínimos;
- índices;
- integridad T01–T09;
- recuperación y comparación de esquema.

**Verificación:** API funciona con rol runtime; SQL directo no puede saltarse las barreras previstas; concurrencia se ejecuta en PostgreSQL multiusuario real.

## 6.3. Pruebas de esquema

Mantener un schema dump normalizado para comparar el resultado de migraciones con la referencia v3 y documentar diferencias intencionales. Las ampliaciones posteriores a v3 deben estar explicadas en `docs/migrations.md`.

---

# 7. Dominio comercial manual — condición previa a NLP

## 7.1. Clientes y catálogo

- crear/editar clientes según PERSONA/EMPRESA;
- solo activos disponibles para nuevas operaciones;
- catálogo por SKU/producto;
- silla/piso/OTRO con especialización correcta;
- promociones simples ANTES/AHORA;
- stock en PIEZA/CAJA según categoría.

## 7.2. Proformas

Estados y reglas del SQL/matriz vigente.

- BORRADOR admite prospecto sin cliente registrado;
- antes de enviar/aprobar se requiere cliente;
- sin historial de versiones de proforma;
- líneas mixtas: mueble a medida + catálogo;
- BOB/USD explícito, sin conversión;
- precio negociado exacto o unitario explícito;
- snapshots mínimos congelados según T02/T03.

## 7.3. Aprobación

Debe conservar el encadenamiento del v3. Django no duplica consecuencias ya producidas por triggers.

## 7.4. Stock

- no reservar por proformas pendientes;
- mostrar stock real, demanda pendiente y disponible referencial;
- proteger aprobación con bloqueo real;
- movimiento inmutable;
- cancelación antes de ENTREGADO genera una sola reversa completa.

## 7.5. Taller, entrega y pagos

- todo pedido genera OT;
- catálogo puede requerir preparación pero no una máquina de estados paralela;
- nota única emitida para realizar la entrega, no al aprobar;
- recibos solo sobre pedido confirmado;
- sin devoluciones dentro del sistema;
- recibo erróneo se ANULA, no se borra ni edita comercialmente.

---

# 8. API REST y OpenAPI

Base:

```text
/api/v1/
```

Familias previstas:

```text
/api/v1/auth/
/api/v1/customers/
/api/v1/catalog/
/api/v1/quotations/
/api/v1/captures/
/api/v1/orders/
/api/v1/inventory/
/api/v1/workshop/
/api/v1/deliveries/
/api/v1/payments/
/api/v1/documents/
```

Acciones de dominio no se expresan como UPDATE genérico:

```text
POST /quotations/{id}/send/
POST /quotations/{id}/approve/
POST /orders/{id}/cancel/
POST /deliveries/{order_id}/issue-note/
POST /payments/receipts/
POST /payments/receipts/{id}/void/
POST /captures/
GET  /captures/{id}/
POST /captures/{id}/confirm/
```

OpenAPI debe ser generado en CI y ser la fuente para el cliente tipado del frontend.

---

# 9. Contrato con `homex-nlp`

## 9.1. Versión

El worker instala una **versión fijada** del paquete. La versión inicial observable en `homex-nlp/refactor` es `0.1.0`, pero la integración de release debe consumir el artefacto aprobado, no una rama flotante.

## 9.2. Estado real del motor

El NER entrenado en F04 no fue promovido por métricas insuficientes. Por tanto, el backend **no debe asumir HYBRID** ni declarar un modelo NER productivo. Debe funcionar con `RULES_ONLY` y registrar modo/versiones reales. HYBRID solo se habilita con artefacto/hash válidos.

## 9.3. Entrada/salida

El adapter Django construye `ExtractionRequest` con:

- texto exacto;
- `request_id`;
- moneda de contexto;
- tipo esperado `MUEBLE_MEDIDA`;
- metadatos ASR cuando existan.

No envía modelos ORM ni credenciales al paquete.

El paquete devuelve cero o una propuesta. `REQUIRES_REVIEW` no equivale a proforma lista para aprobar.

## 9.4. Persistencia

- `intentos_captura.resultado_raw` conserva el resultado original del servidor;
- `items_ia` es proyección consultable;
- el navegador no puede reemplazar la IA original;
- confirmación recupera evidencia del servidor y recibe solo corrección humana;
- una corrección final y una evaluación por corrección;
- `schema_version` NLP no se confunde con `schema_version` JSONB comercial.

## 9.5. Adapter JSONB V1

`captures/nlp_adapter.py` traduce el contrato rico a la representación comercial sin perder información legible. El JSONB no obliga perfiles de muebles todavía no proporcionados.

## 9.6. Offsets

Persistir offsets Unicode Python `[start,end)` sobre `text_original`. El futuro frontend convierte a UTF-16 únicamente al resaltar; no reescribe offsets almacenados.

---

# 10. Celery, Redis, outbox e idempotencia

## 10.1. Flujo

```text
POST captura
  ├── transacción DB
  │    ├── captura/idempotencia
  │    ├── intento
  │    └── trigger → trabajo outbox
  └── 202

publicador outbox
  └── Redis
       └── worker
            ├── reclamar intento
            ├── ASR si corresponde
            ├── borrar audio
            ├── NLP
            └── cerrar intento + item IA
```

## 10.2. Idempotencia HTTP

`capturas.clave_idempotencia` viene del frontend y es única. Mismo actor/proforma/contenido con misma clave recupera la captura existente; misma clave con contenido incompatible produce conflicto. La clave no sustituye autorización.

## 10.3. Outbox

El trigger crea el trabajo junto al intento. Django no inserta un segundo outbox. Publicar a Redis no equivale a completar el trabajo; reentrega es esperable y debe ser segura.

## 10.4. Audio

- temporal privado;
- fuera de `archivos_adjuntos`;
- fuera de backups;
- sin endpoint de reproducción/histórico;
- se elimina inmediatamente tras ASR en éxito o fallo conforme al contrato;
- los reintentos NLP usan texto, no audio;
- limpieza de huérfanos independiente del worker de inferencia.

---

# 11. Seguridad y permisos

- autenticación JWT para API;
- administración Django restringida;
- permisos de objeto/caso de uso, no solo roles visuales;
- PostgreSQL runtime sin privilegios de propietario ni TRUNCATE;
- secretos fuera de Git;
- CORS por lista explícita;
- límites de upload y validación de contenido de audio/adjuntos;
- errores externos con código estable y `correlation_id`, sin traceback/rutas/credenciales/texto completo sensible;
- logs sin bytes de audio ni payloads completos de cliente;
- HTTPS en despliegue.

---

# 12. Estrategia de pruebas

## 12.1. Capas

| Capa | Objetivo |
|---|---|
| Unitarias | pricing, validadores, serializers, adapters puros. |
| Integración DB | funciones/triggers/migraciones con PostgreSQL real. |
| API | auth, permisos, contratos, estados HTTP, idempotencia. |
| Concurrencia | dos conexiones reales y sincronización de intercalados. |
| Contrato NLP | fixtures/schema/versiones del paquete fijado. |
| Worker | reentrega, Redis caído, worker tardío, retry, audio. |
| E2E backend | recorrido manual y recorrido NLP+HITL. |

## 12.2. Casos mínimos obligatorios

- migrar desde DB vacía;
- G01: 3 por 100 mantiene `100.00`;
- totales adulterados rechazados/recalculados;
- cliente/snapshot congelado desde ENVIADA;
- detalle no cambia de proforma;
- edición/aprobación concurrente serializada;
- stock insuficiente revierte aprobación completa;
- dos vendedores compiten por última unidad: solo uno aprueba;
- cancelación crea una única REVERSA_VENTA;
- recibo EMITIDO bloquea cancelación;
- ANULADO deja de sumar sin reescribir snapshots históricos previos;
- nota no existe al aprobar y se emite en LISTO_ENTREGA;
- intento cerrado/IA inmutables;
- outbox sobrevive a Redis caído;
- reentrega no duplica IA;
- idempotencia HTTP recupera o produce 409 correctamente;
- confirmación HITL usa IA del servidor;
- archivo de audio desaparece tras ASR/fallo y no es consultable;
- usuario sin permiso recibe 403 aunque conozca la URL.

---

# 13. CI y calidad

Workflow mínimo:

1. instalar Python 3.11.15/versión compatible definida;
2. `uv sync --locked --extra dev`;
3. lint/formato;
4. levantar PostgreSQL real;
5. migrar desde vacío;
6. unit/API/integration;
7. pruebas de concurrencia seleccionadas;
8. contrato con versión NLP fijada;
9. generar/verificar OpenAPI;
10. build de imagen/artefacto cuando corresponda.

No descargar pesos ASR/NER desde Internet durante tests normales. Las pruebas del adapter usan dobles; smoke de modelo real pertenece a pipeline/release controlado.

---

# 14. Fases de ejecución y entregables verificables

Las fases se mantienen coordinadas con F07–F11 del plan rector. Las subfases de este documento permiten trabajar desde el estado actual sin llamar “F07 terminada” a un esqueleto.

## F07.0 — Saneamiento y baseline ejecutable

**Dependencias:** estado actual.  
**Objetivo:** convertir el repositorio en una base reproducible que arranca.

### Trabajo

- crear manifiesto/baseline del estado actual;
- corregir o recrear apps con nombres canónicos;
- crear `accounts` y `AUTH_USER_MODEL` antes de consolidar auth;
- corregir configuración DB;
- separar settings;
- crear `.env.example`, README, `pyproject.toml`, `uv.lock`, Makefile;
- configurar DRF/JWT básico;
- crear health endpoint;
- CI inicial con `check` y tests mínimos;
- retirar stubs que contradigan la estructura objetivo (`ventas`, `nlp` como motor) antes de que tengan migraciones.

### Entregables verificables

- `uv sync --locked --extra dev` funciona;
- `uv run python manage.py check` pasa;
- `/admin/`, `/api/v1/health/` y login básico arrancan;
- ninguna app en `INSTALLED_APPS` es inexistente;
- configuración local no contiene secretos versionados;
- CI verde.

**Salida:** proyecto Django sano; aún no se declara negocio implementado.

## F07.1 — DB-01: Django toma propiedad del esquema

**Dependencias:** F07.0.

### Trabajo

- modelar las 24 tablas comerciales por dependencia;
- actores hacia AUTH_USER_MODEL;
- secuencias y catálogos estructurales;
- migraciones iniciales + RunSQL versionado;
- documentar mapa SQL v3 → modelos/migraciones;
- impedir doble bootstrap SQL+migrations.

### Entregables verificables

- PostgreSQL vacía → `migrate` exitoso;
- 24 tablas comerciales + auth Django + cuatro secuencias;
- schema diff explicado;
- tests de catálogo/FK/checks base.

**Salida:** DB-01 cerrado.

## F07.2 — DB-02: clientes, catálogo y proforma manual

**Dependencias:** F07.1.

### Trabajo

- customers/catalog/quotations;
- serializers, services, queries, permissions y endpoints;
- proforma mixta;
- BOB/USD sin conversión;
- promoción simple;
- G01 y T01–T04;
- demanda pendiente solo informativa.

### Entregables verificables

- CRUD autorizado donde corresponde;
- proforma manual completa sin NLP;
- 3×100 negociado conserva 100.00;
- freeze y FOR UPDATE probados;
- OpenAPI de estos módulos.

**Salida:** cotización manual fiable.

## F07.3 — DB-03: aprobación, pedidos, inventario y taller

**Dependencias:** F07.2.

### Trabajo

- triggers de aprobación trasladados/probados;
- pedido/OT;
- movimientos/stock;
- estados;
- cancelación/reversa;
- permisos de vendedor/taller;
- concurrencia real.

### Entregables verificables

- aprobación válida crea exactamente pedido + VENTA(s) + OT;
- falta de stock deja cero efectos parciales;
- competencia por stock consistente;
- cancelación crea una sola reversa;
- OT accesible según permisos.

**Salida:** DB-03 y núcleo de venta cerrados.

## F07.4 — DB-05: recibos, entregas y documentos

**Dependencias:** F07.3.

### Trabajo

- EMITIDO/ANULADO;
- sobrepago;
- bloqueo común de pedido;
- emisión de nota desde LISTO_ENTREGA;
- cuatro plantillas/documentos, inicialmente funcionales y luego ajustadas a originales HOMEX.

### Entregables verificables

- G02/G03/T06 pasan;
- numeración concurrente comprobada;
- no cancelar con recibos EMITIDOS;
- documento recuperable desde datos persistidos, sin depender de valores vivos del maestro.

**Salida:** flujo comercial manual extremo a extremo.

## F07.5 — DB-06: carga de catálogo real

**Dependencias:** F07.2; puede avanzar en paralelo con F07.3/F07.4 sin inventar datos.

### Trabajo

- `import_sillas` con `--dry-run`;
- identidad estable SKU/mapa confirmado;
- revisión de colores/presentaciones;
- stock inicial solo mediante movimientos;
- catálogo pisos/OTRO/promociones cuando existan datos reales.

### Entregables verificables

- ejecutar dos veces no duplica;
- faltantes se reportan;
- no se inventan precio/stock/SKU;
- carga real solo después de confirmación de datos.

**Salida:** DB-06 cerrado o formalmente bloqueado por insumos identificados.

## F07.6 — DB-07, permisos, OpenAPI y cierre de F07

**Dependencias:** F07.1–F07.5.

### Trabajo

- rol DB runtime mínimo;
- matriz de permisos;
- índices y queries críticas;
- pruebas SQL históricas convertidas a regresión;
- CI completa backend;
- OpenAPI estable;
- documentación `architecture`, `migrations`, `permissions`, `runbook`.

### Entregables verificables

- checklist F07 del plan NLP cumplido;
- recorrido comercial manual sin Redis/NLP;
- todas las pruebas DB/API/concurrency acordadas verdes;
- migración desde vacío reproducible.

**Salida:** **F07 completa**.

## F08.0 — Contrato e instalación del paquete NLP

**Dependencias:** F06 NLP + F07 backend.

### Trabajo

- fijar wheel/version de `homex-nlp`;
- consumer tests de `schema_version` soportada;
- `nlp_adapter.py`;
- configuración RULES_ONLY inicial;
- manejo seguro de errores/versiones.

### Entregables verificables

- importar paquete sin Django dentro de NLP;
- adapter convierte fixture v1 sin pérdida relevante;
- versión desconocida falla explícitamente;
- backend no requiere NER promovido.

## F08.1 — DB-04: capturas, intentos, outbox e idempotencia

**Dependencias:** F08.0.

### Trabajo

- tablas/migraciones DB-04;
- POST idempotente;
- creación automática de outbox;
- consulta de estado;
- protección T07/T09.

### Entregables verificables

- 202 + polling;
- reenvío idéntico recupera captura;
- conflicto produce 409;
- intento crea un solo outbox;
- evidencia cerrada no se modifica.

## F08.2 — Worker, ASR y audio efímero

**Dependencias:** F08.1.

### Trabajo

- Celery config;
- publicador/reconciliador;
- worker;
- audio store privado;
- ASR adapter;
- limpieza inmediata y limpieza de huérfanos;
- reintentos sin audio después de transcripción.

### Entregables verificables

- Redis caído no pierde trabajo;
- reentrega segura;
- audio eliminado en éxito/fallo;
- worker tardío no reescribe intento cerrado;
- no hay endpoint/backup de audio histórico.

## F08.3 — HITL, confirmación y evaluación

**Dependencias:** F08.2.

### Trabajo

- presentar resultado IA;
- recuperar original desde servidor;
- corrección final;
- `items_humano`;
- `evaluaciones_nlp` con `version_metrica`;
- crear/vincular detalle de proforma en misma transacción;
- confirmar captura **sin aprobar proforma**.

### Entregables verificables

- IA del navegador no puede sustituir original;
- una corrección/evaluación por relación;
- propuesta parcial puede corregirse;
- confirmación manual y aprobación comercial siguen separadas.

## F08.4 — Resiliencia y cierre F08

**Dependencias:** F08.0–F08.3.

### Trabajo

- matriz de fallos archivo/DB/Redis/ASR/NLP;
- observabilidad/correlation IDs;
- test de contrato con wheel real;
- documentación de operación/reintento.

### Entregables verificables

- AUDIO/HITL/CONTRACT pasan;
- worker real + PostgreSQL real + Redis real en integración;
- ningún fallo probado deja evidencia contradictoria o audio histórico.

**Salida:** **F08 completa**.

## F09 — Soporte backend a Vue y documentos finales

**Dependencias:** F07/F08 + frontend.

### Backend

- estabilizar OpenAPI;
- CORS/CSRF según estrategia final;
- endpoints necesarios para editor mixto, taller, entrega y pagos;
- render de documentos basado en documentos físicos reales;
- pruebas E2E compartidas.

**Salida backend:** el frontend no necesita lógica comercial duplicada ni endpoints ad hoc fuera del contrato.

## F10 — Despliegue y recuperación

**Dependencias:** F09 + deploy.

### Backend

- imagen API y worker;
- health/readiness;
- migración controlada;
- logs/metrics;
- backup PostgreSQL sin audio;
- restore probado;
- limpieza temporal independiente;
- manifiesto con versión backend + NLP.

**Salida:** smoke, rollback compatible y recuperación ensayada.

## F11 — Piloto y cierre integrado

**Dependencias:** F10 + datos/sesiones reales.

### Backend

- fijar versiones de componentes;
- registrar mediciones MANUAL/NLP_HITL;
- soportar recolección de métricas sin guardar audio;
- ejecutar regresión después de defectos de piloto;
- documentación final de operación y mantenimiento.

**Salida:** checklist B del plan global cumplido o faltantes externos documentados sin declarar falsamente el sistema terminado.

---

# 15. Dependencia resumida

```text
homex-nlp F00 ─ F01 ─ F02 ─ F03 ─ F04 ─ F05 ─ F06
                   │                         │
                   └──────────────┐          │
                                  ▼          ▼
backend actual → F07.0 → F07.1 → F07.2 → F07.3 → F07.4 → F07.6
                          │          │          │        │
                          └→ F07.5 ──┘          │        │
                                                ▼        │
                                              F08.0 ←────┘
                                                ↓
                                              F08.1
                                                ↓
                                              F08.2
                                                ↓
                                              F08.3
                                                ↓
                                              F08.4
                                                ↓
                                              F09 → F10 → F11
```

---

# 16. Comandos que deberán existir

Después de F07.0:

```bash
uv sync --locked --extra dev
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py migrate
uv run pytest
make check
```

Base limpia en CI:

```bash
uv run python manage.py migrate --noinput
uv run pytest tests/integration tests/api
```

Catálogo:

```bash
uv run python manage.py import_sillas --input <archivo-revisado>.json --dry-run
uv run python manage.py import_sillas --input <archivo-revisado>.json
```

Worker después de F08:

```bash
uv run celery -A config worker -l INFO
```

El publicador/reconciliador debe tener comando o proceso explícito documentado; no depender de que una petición HTTP recorra outbox antiguos.

---

# 17. Insumos pendientes que no deben inventarse

| Insumo | Impacto |
|---|---|
| SKU/identidad, precio, color/presentación y stock real de sillas | carga comercial real F07.5. |
| catálogo real de pisos/OTRO/promociones | carga de esas categorías. |
| cuatro documentos físicos HOMEX | validación final de plantillas F09. |
| perfiles reales de muebles | mejoran validación, pero no bloquean JSON V1 flexible. |
| sesiones de audio con referencia humana | evaluación ASR/piloto F11; no bloquea worker con dobles. |
| RPO/RTO y política formal de retención | necesarios antes de producción/piloto formal. |

---

# 18. Incoherencias entre repositorios que deben mantenerse visibles

## C01 — El SQL está duplicado hoy

Mismo SQL v3 aparece en `homex-nlp` y `homex-backend`. Esto es útil como baseline, pero después de F07 no deben evolucionar manualmente dos copias.

**Resolución:** backend migrations = fuente operativa; NLP conserva referencia/evidencia y contrato, sin administrar esquema.

## C02 — El plan NLP habla de “backend futuro”, pero el repositorio ya existe

No es una contradicción funcional: el documento fue escrito antes de crear el repo. Este plan sustituye esa parte prospectiva por el estado real y conserva F07/F08 como numeración global.

## C03 — `apps/nlp` del backend invade la frontera del paquete

El backend no debe copiar motor, entrenamiento ni modelos. La app se sustituye por `captures`; el adapter importa el paquete versionado.

## C04 — `requirements.txt` backend vs `pyproject/uv.lock` NLP

Dos mecanismos dificultan releases coordinadas.

**Resolución:** migrar backend a dependencias directas + lock reproducible con uv durante F07.0; conservar `requirements.txt` solo si se genera automáticamente para una necesidad de despliegue, no como segunda fuente manual.

## C05 — SQL v3 no es todavía el esquema final aprobado

G01/G02/G03 y T01–T09 incluyen cambios que no deben editarse silenciosamente en una copia del SQL.

**Resolución:** migraciones explícitas y tests; actualizar documentación/schema dump después.

## C06 — Estado NER

F04 produjo un modelo con métricas insuficientes y no fue promovido.

**Resolución:** backend inicia con RULES_ONLY; HYBRID requiere release y hash aprobados. Nunca presentar el modelo experimental como modelo productivo.

## C07 — Audio

El NLP borra temporales que recibe en su servicio local; en producto el backend es propietario del ciclo del archivo y debe garantizar además limpieza de huérfanos/errores y exclusión de backups.

## C08 — `inspectdb/managed=False` no es el destino final

Puede ayudar a auditar el SQL ya existente, pero contradice la decisión global de que Django sea dueño del esquema y de que las 24 tablas se creen mediante migraciones.

**Resolución:** utilizarlo únicamente como comparación temporal, nunca como contrato permanente.

---

# 19. Riesgos de implementación

| Riesgo | Mitigación |
|---|---|
| Duplicar lógica Django/triggers | definir autoridad por caso de uso y probar paridad. |
| Ejecutar DDL v3 y migraciones sobre las mismas tablas | una sola estrategia por entorno; bootstrap nuevo exclusivamente con migrations tras F07.1. |
| Crear auth y luego cambiar AUTH_USER_MODEL | crear custom user en F07.0 antes de estabilizar migraciones. |
| Nombrar apps/modelos y luego renombrarlos con datos | alinear estructura ahora, mientras los stubs están vacíos. |
| Concurrencia simulada con mocks | PostgreSQL real, conexiones distintas. |
| Worker duplica efectos | idempotencia + estados + restricciones únicas + outbox. |
| Navegador falsifica evidencia IA | original recuperado desde servidor. |
| Redis tratado como persistencia | estado definitivo en PostgreSQL. |
| NER experimental promovido por comodidad | RULES_ONLY por defecto hasta release medido. |
| Audio retenido accidentalmente | store privado, finally, janitor, backup exclusions y tests. |

---

# 20. Definición de terminado del backend

El backend se considera terminado para integración únicamente cuando:

- [ ] Python/dependencias/configuración son reproducibles y CI está verde.
- [ ] Django arranca sin apps faltantes ni configuración local hardcodeada.
- [ ] `AUTH_USER_MODEL`, roles y permisos están establecidos y probados.
- [ ] PostgreSQL se construye desde vacío exclusivamente mediante migraciones del backend.
- [ ] Las 24 tablas comerciales, cuatro secuencias y ampliaciones G01–G03/T01–T09 están implementadas.
- [ ] Proforma manual mixta funciona sin NLP.
- [ ] Aprobación es atómica y conserva pedido + VENTA + OT de los triggers.
- [ ] Stock, demanda referencial, cancelación y reversa soportan concurrencia real.
- [ ] Recibos EMITIDO/ANULADO y nota de entrega cumplen semántica aprobada.
- [ ] Catálogo real se carga solo mediante datos confirmados e importador auditable.
- [ ] OpenAPI, permisos y documentación están versionados.
- [ ] Capturas son idempotentes y crean intento/outbox consistente.
- [ ] Worker instala una versión fijada de `homex-nlp` y funciona inicialmente en RULES_ONLY.
- [ ] ASR/NLP no escriben negocio directamente.
- [ ] HITL usa evidencia del servidor, crea una corrección final y una evaluación versionada.
- [ ] Audio es temporal, privado, no respaldado ni consultable después de ASR.
- [ ] Redis caído/reentrega/worker tardío no producen pérdida ni duplicación lógica.
- [ ] API + worker + PostgreSQL + Redis superan tests de integración.
- [ ] Frontend puede consumir OpenAPI sin duplicar reglas comerciales.
- [ ] Deploy fija versiones backend/NLP y existe restauración ensayada.
- [ ] El piloto puede medir MANUAL vs NLP_HITL sin conservar audio histórico.

**Cierre:** F07 demuestra que HOMEX funciona comercialmente sin IA. F08 demuestra que la captura ASR/NLP se integra de forma recuperable y trazable sin convertirse en autoridad comercial. F09–F11 demuestran que ese backend funciona como producto completo junto al frontend, despliegue y evaluación real.
