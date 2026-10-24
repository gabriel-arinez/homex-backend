from decimal import Decimal

import pytest
from homex_nlp.contracts import ExtractionRequest
from homex_nlp.engine import RulesEngine

from apps.capturas.api.asistidas import PendienteAsistidaSerializer
from apps.capturas.proyeccion_prf03 import proyectar

pytestmark = pytest.mark.django_db


def proyectar_texto(texto):
    raw = RulesEngine().extract(
        ExtractionRequest(request_id="comercial-v5", text=texto, currency_context="BOB")
    )
    return proyectar(raw.model_dump(mode="json"))


def test_total_negociado_estructurado_sin_unitario_inventado():
    propuesta = proyectar_texto("Dos mesas, precio total de las dos mesas es de 7300")
    assert propuesta["comercial"]["cantidad"] == 2
    assert propuesta["comercial"]["precio_unitario"] is None
    pendiente = next(x for x in propuesta["pendientes"] if x["codigo"] == "TOTAL_NEGOCIADO")
    assert pendiente["total_negociado"] == "7300.00"
    assert pendiente["moneda_codigo"] == "BOB"
    serializado = PendienteAsistidaSerializer(pendiente).data
    assert Decimal(serializado["total_negociado"]) == Decimal("7300.00")


def test_total_sin_cantidad_requiere_revision():
    propuesta = proyectar_texto("Mesa de reunión para diez personas, total 7300")
    assert propuesta["comercial"]["cantidad"] is None
    assert propuesta["comercial"]["precio_unitario"] is None
    assert {p["codigo"] for p in propuesta["pendientes"]} >= {"NO_QUANTITY", "TOTAL_NEGOCIADO"}


def test_precio_unitario_explicito_si_se_proyecta():
    propuesta = proyectar_texto("Dos mesas, precio unitario de 3650 bolivianos")
    assert propuesta["comercial"]["cantidad"] == 2
    assert propuesta["comercial"]["precio_unitario"] == "3650.00"
