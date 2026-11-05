"""El catálogo de ejemplo nunca escribe sin autorización explícita."""
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.catalogo.models import Producto, ValorCatalogo
from tests.factories import valor


@pytest.mark.django_db(transaction=True)
def test_catalogo_demo_valida_sin_modificar_y_carga_quince_de_forma_idempotente(django_user_model):
    for category in ("SILLA", "PISO_FLOTANTE", "OTRO"):
        valor("CATEGORIA_PRODUCTO", category)
    for unit in ("PIEZA", "M2"):
        valor("UNIDAD_MEDIDA", unit)

    from apps.catalogo.models import ConceptoCatalogo
    marca, _ = ConceptoCatalogo.objects.get_or_create(codigo="MARCA", defaults={"activo": True})
    color, _ = ConceptoCatalogo.objects.get_or_create(codigo="COLOR", defaults={"activo": True})
    ValorCatalogo.objects.get_or_create(
        concepto=color, codigo="NEGRO", defaults={"nombre": "Negro", "activo": True}
    )
    actor = django_user_model.objects.create_user(username="demo-loader-test")
    output = StringIO()
    call_command("cargar_catalogo_demo", actor_id=actor.id, stdout=output)
    assert "SIMULACIÓN" in output.getvalue()
    assert not Producto.objects.filter(sku__startswith="DEMO-").exists()
    assert not ValorCatalogo.objects.filter(concepto=marca, codigo="DEMO_MARCA").exists()

    with pytest.raises(CommandError):
        call_command("cargar_catalogo_demo", actor_id=actor.id, apply=True)

    with override_settings(DEBUG=True), patch.dict("os.environ", {"HOMEX_ALLOW_DEMO_DATA": "1"}):
        call_command("cargar_catalogo_demo", actor_id=actor.id, apply=True, stdout=StringIO())
        assert Producto.objects.filter(sku__startswith="DEMO-").count() == 15
        assert Producto.objects.filter(sku__startswith="DEMO-", stock=0).count() == 15
        for code in ("SILLA", "PISO_FLOTANTE", "OTRO"):
            assert Producto.objects.filter(
                sku__startswith="DEMO-", categoria__codigo=code
            ).count() == 5
        call_command("cargar_catalogo_demo", actor_id=actor.id, apply=True, stdout=StringIO())
        assert Producto.objects.filter(sku__startswith="DEMO-").count() == 15
