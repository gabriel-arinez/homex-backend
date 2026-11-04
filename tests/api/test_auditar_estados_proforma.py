from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalogo.models import ConceptoCatalogo, ValorCatalogo


@pytest.mark.django_db
def test_auditoria_no_modifica_estado_inactivo_y_reparacion_es_explicita():
    concepto, _ = ConceptoCatalogo.objects.get_or_create(
        codigo="ESTADO_PROFORMA", defaults={"activo": True}
    )
    concepto.activo = True
    concepto.save(update_fields=["activo"])
    estado, _ = ValorCatalogo.objects.get_or_create(
        concepto=concepto,
        codigo="EN_REVISION",
        defaults={"nombre": "En revisión"},
    )
    estado.activo = False
    estado.save(update_fields=["activo"])
    with pytest.raises(CommandError, match="EN_REVISION"):
        call_command("auditar_estados_proforma", stdout=StringIO())
    estado.refresh_from_db()
    assert estado.activo is False

    salida = StringIO()
    call_command("auditar_estados_proforma", "--reparar", stdout=salida)
    estado.refresh_from_db()
    assert estado.activo is True
    assert "REPARADO ESTADO_PROFORMA.EN_REVISION" in salida.getvalue()
    call_command("auditar_estados_proforma", stdout=StringIO())


@pytest.mark.django_db
def test_reparacion_restaura_estado_operativo_ausente_sin_duplicarlo():
    concepto, _ = ConceptoCatalogo.objects.get_or_create(
        codigo="ESTADO_PROFORMA", defaults={"activo": True}
    )
    concepto.activo = True
    concepto.save(update_fields=["activo"])
    ValorCatalogo.objects.filter(
        concepto=concepto, codigo="NO_CONCRETADA"
    ).delete()
    with pytest.raises(CommandError, match="NO_CONCRETADA"):
        call_command("auditar_estados_proforma", stdout=StringIO())
    call_command("auditar_estados_proforma", "--reparar", stdout=StringIO())
    call_command("auditar_estados_proforma", "--reparar", stdout=StringIO())
    assert ValorCatalogo.objects.filter(
        concepto=concepto, codigo="NO_CONCRETADA", activo=True
    ).count() == 1


@pytest.mark.django_db
def test_concepto_inactivo_nunca_se_reactiva_automaticamente():
    concepto, _ = ConceptoCatalogo.objects.get_or_create(
        codigo="ESTADO_PROFORMA", defaults={"activo": True}
    )
    concepto.activo = False
    concepto.save(update_fields=["activo"])
    with pytest.raises(CommandError, match="inactivo"):
        call_command("auditar_estados_proforma", "--reparar", stdout=StringIO())
    concepto.refresh_from_db()
    assert not concepto.activo
