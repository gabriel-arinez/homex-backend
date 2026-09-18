# Permisos

Los grupos estructurales son `ADMINISTRACION`, `VENTAS` y `TALLER`. Se crean después de migrar y pueden asegurarse con `uv run python manage.py seed_roles`.

Los endpoints comerciales de proformas, recibos y notas requieren `VENTAS` o `ADMINISTRACION`. Las consultas se limitan al vendedor propietario salvo ampliaciones explícitas de administración. Un usuario autenticado sin rol recibe 403. Taller se reserva para las futuras acciones de OT.
