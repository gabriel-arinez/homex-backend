# Arquitectura del backend HOMEX

## Visión general

HOMEX Backend es un monolito modular construido con Django y Django REST
Framework, respaldado exclusivamente por PostgreSQL.

Las responsabilidades se distribuyen de la siguiente manera:

- API REST: autenticación, autorización y contratos HTTP.
- Servicios Django: coordinación de casos de uso y transacciones.
- Modelos Django: representación del dominio persistente.
- PostgreSQL: integridad estructural, reglas comerciales críticas y concurrencia.
- Frontend Vue: captura y presentación de información.

El frontend no es autoridad sobre totales, stock, estados ni restricciones
comerciales.

## Módulos

El backend está compuesto por:

- `accounts`
- `catalogo`
- `clientes`
- `proformas`
- `pedidos`
- `movimientos_stock`
- `ordenes_trabajo`
- `recibos`
- `notas_entrega`
- `documentos`
- `capturas`

`capturas` contiene persistencia preparada para la futura integración NLP.
Redis, Celery, workers y procesamiento NLP pertenecen a F08.

## PostgreSQL como autoridad

PostgreSQL protege reglas que no deben depender únicamente de la API.

Entre ellas:

- cálculo de detalles y totales;
- congelamiento de información comercial;
- transiciones válidas de pedido;
- aprobación de proformas;
- creación de pedido;
- creación de `VENTA`;
- control de stock;
- creación de orden de trabajo;
- cancelación y `REVERSA_VENTA`;
- restricciones sobre recibos;
- emisión de nota de entrega;
- inmutabilidad de evidencia comercial;
- protección frente a concurrencia.

Django coordina las operaciones y traduce errores comerciales de PostgreSQL,
pero no duplica una regla cuando la base ya constituye su autoridad.

## Flujo comercial manual

El flujo implementado en F07 es:

```text
Cliente
  ↓
Proforma BORRADOR
  ↓
Detalle
  ↓
ENVIADA
  ↓
APROBADA
  ↓
Pedido CONFIRMADO
  ├── VENTA
  └── Orden de trabajo
  ↓
Recibo(s)
  ↓
EN_PRODUCCION
  ↓
LISTO_ENTREGA
  ↓
Nota de entrega
  ↓
ENTREGADO