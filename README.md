# HOMEX Backend

Backend comercial del Sistema de Gestión de Pedidos HOMEX.

El proyecto utiliza:

- Python 3.11;
- Django 5.2 LTS;
- Django REST Framework;
- PostgreSQL 17;
- autenticación JWT;
- drf-spectacular para OpenAPI;
- pytest;
- Ruff.

PostgreSQL es obligatorio. No existe soporte operativo mediante SQLite.

## Responsabilidad

Este repositorio concentra:

- autenticación y autorización;
- catálogo comercial;
- clientes;
- proformas;
- pedidos;
- movimientos de stock;
- órdenes de trabajo;
- recibos;
- notas de entrega;
- documentos comerciales;
- persistencia necesaria para el futuro flujo NLP.

Las reglas críticas de integridad comercial y concurrencia se protegen también
en PostgreSQL mediante funciones, restricciones y triggers.

El frontend no debe reproducir reglas autoritativas de negocio.

## Estado actual

F07 implementa el flujo comercial manual:

1. autenticación JWT;
2. consulta de catálogo;
3. gestión de clientes;
4. creación de proforma;
5. detalles y condiciones comerciales;
6. envío de proforma;
7. aprobación;
8. creación automática de pedido;
9. movimiento `VENTA`;
10. creación automática de orden de trabajo;
11. cobros mediante recibos;
12. avance del pedido;
13. emisión de nota de entrega;
14. cancelación válida con reversa automática de stock.

Redis, Celery y la integración NLP pertenecen a F08 y no forman parte del flujo
manual actual.

## Requisitos

- Python `>=3.11,<3.12`;
- `uv`;
- PostgreSQL;
- una base de datos PostgreSQL accesible mediante `DATABASE_URL`.

## Configuración local

Copiar el archivo de ejemplo:

```bash
cp .env.example .env