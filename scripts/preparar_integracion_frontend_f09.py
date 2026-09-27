"""Datos deterministas del backend para el recorrido compartido frontend/backend F09."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.integration")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.catalogo.models import Producto, ValorCatalogo  # noqa: E402
from apps.clientes.models import Cliente  # noqa: E402
from apps.movimientos_stock.models import MovimientoStock  # noqa: E402


def valor(concepto: str, codigo: str) -> ValorCatalogo:
    return ValorCatalogo.objects.get(concepto__codigo=concepto, codigo=codigo)


def ejecutar() -> None:
    usuario, _ = get_user_model().objects.get_or_create(username="fe08-admin")
    usuario.first_name = "Integración"
    usuario.last_name = "FE08"
    usuario.is_staff = True
    usuario.is_superuser = True
    usuario.set_password("fe08-integration-only")
    usuario.save()

    Cliente.objects.get_or_create(
        celular="70000008",
        defaults={
            "tipo_cliente": valor("TIPO_CLIENTE", "PERSONA"),
            "nombres": "Cliente",
            "apellidos": "Integración FE08",
            "direccion": "Tienda HOMEX",
            "activo": True,
            "created_by": usuario,
            "updated_by": usuario,
        },
    )
    producto, creado = Producto.objects.get_or_create(
        sku="FE08-SILLA-001",
        defaults={
            "categoria": valor("CATEGORIA_PRODUCTO", "OTRO"),
            "nombre": "Silla integración FE08",
            "precio_lista": "250.00",
            "stock": 0,
            "unidad_stock": valor("UNIDAD_MEDIDA", "PIEZA"),
            "activo": True,
            "created_by": usuario,
            "updated_by": usuario,
        },
    )
    if creado:
        MovimientoStock.objects.create(
            producto=producto,
            tipo_movimiento=valor("TIPO_MOVIMIENTO", "CARGA_INICIAL"),
            cantidad=20,
            fecha=timezone.now(),
            observaciones="Stock reproducible para F09",
            created_by=usuario,
        )

    print(f"f09-seed-ok user={usuario.id} product={producto.id}")


if __name__ == "__main__":
    ejecutar()
