# Guía de operación — HOMEX Backend

## Preparación

Instalar dependencias y validar Django:

```bash
uv sync --locked --extra dev
uv run python manage.py check
```

## Base de datos

El backend utiliza exclusivamente PostgreSQL.

Aplicar migraciones:

```bash
uv run python manage.py migrate --noinput
```

Una segunda ejecución debe finalizar con `No migrations to apply.`.

Para desarrollo y pruebas debe utilizarse una base construida mediante las
migraciones actuales. La base histórica local `homex` no constituye evidencia
del bootstrap vigente porque contiene un esquema comercial preexistente fuera
del historial actual de migraciones Django.

## Roles PostgreSQL

Se separan dos responsabilidades:

- `homex_migrator`: ejecuta migraciones y DDL;
- `homex_runtime`: ejecuta las operaciones normales de la aplicación.

El runtime no debe disponer de privilegios DDL.

Ver:

- `docs/migraciones.md`;
- `docs/sql/privilegios_runtime.sql`;
- `scripts/verificar_privilegios_runtime.py`.

## Inicio

```bash
uv run python manage.py runserver
```

Health check:

```text
GET /api/v1/health/
```

## Autenticación

Obtener JWT:

```text
POST /api/v1/auth/token/
```

Renovar JWT:

```text
POST /api/v1/auth/token/refresh/
```

Consultar identidad y capacidades del usuario autenticado:

```text
GET /api/v1/auth/me/
```

La respuesta incluye:

- `id`;
- `username`;
- `display_name`;
- `capabilities`.

Las capacidades comerciales actuales son `comercial.operar` y
`comercial.administrar`. Un usuario autenticado sin rol comercial recibe una
lista vacía.

## Flujo comercial

### Cliente y catálogo

```text
/api/v1/clientes/
/api/v1/catalogo/productos/
```

El vendedor consulta el catálogo. Su administración corresponde al perfil
administrativo.

### Proforma

```text
POST /api/v1/proformas/
POST /api/v1/proformas/{id}/detalles/
POST /api/v1/proformas/{id}/enviar/
POST /api/v1/proformas/{id}/aprobar/
```

La aprobación genera el pedido `CONFIRMADO`, el movimiento `VENTA`, el
descuento de stock y la orden de trabajo. PostgreSQL protege los efectos
comerciales críticos.

### Recibos

Sólo pueden emitirse mientras el pedido está `CONFIRMADO`:

```text
POST /api/v1/pedidos/{id}/emitir_recibo/
```

Un recibo incorrecto se anula:

```text
POST /api/v1/recibos/{id}/anular/
```

### Estados de pedido

El avance normal se realiza mediante:

```text
POST /api/v1/pedidos/{id}/cambiar-estado/
```

Estados expuestos:

- `EN_PRODUCCION`;
- `LISTO_ENTREGA`;
- `ENTREGADO`.

PostgreSQL valida que la transición concreta esté permitida. No se debe usar
esta acción para cancelar.

### Nota de entrega

Sólo puede emitirse desde `LISTO_ENTREGA`:

```text
POST /api/v1/pedidos/{id}/emitir_nota_entrega/
```

### Cancelación

La cancelación utiliza exclusivamente:

```text
POST /api/v1/pedidos/{id}/cancelar/
```

Una cancelación válida produce `CANCELADO`, `REVERSA_VENTA`, restitución de
stock y OT `CANCELADA`. Un pedido con recibos `EMITIDO` no puede cancelarse
mediante el flujo comercial normal.

## Permisos

La autorización se aplica en backend mediante permission classes, querysets y
servicios. Un vendedor no puede operar directamente objetos comerciales de
otro vendedor.

La matriz completa está en `docs/permisos.md`.

## OpenAPI

Validar:

```bash
uv run python manage.py spectacular --file /tmp/openapi.yaml --validate
diff -u docs/openapi.yaml /tmp/openapi.yaml
```

El diff debe quedar vacío.

## Gates de cierre

```bash
uv run ruff check .
uv run ruff format --check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest -ra
uv run pytest -ra -m concurrency
```

Además deben pasar:

- migración desde PostgreSQL vacía;
- segunda migración no-op;
- E2E JWT/API;
- permisos y aislamiento;
- privilegios migrador/runtime;
- OpenAPI sin drift;
- CI remoto.
