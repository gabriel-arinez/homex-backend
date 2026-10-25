"""Contrato backend real ante negaciones y rectificaciones del motor v7."""

import pytest

from apps.capturas.nlp import AdaptadorNLP


# Las fixtures autouse globales crean registros comerciales en PostgreSQL.
# Este contrato comprueba solo RulesEngine y AdaptadorNLP, sin acceso a BD;
# mantener las pruebas de persistencia en la suite de integración con PostgreSQL.
@pytest.fixture(autouse=True)
def catalogo_estructural():
    yield


@pytest.fixture(autouse=True)
def transiciones_pedido():
    yield


def extraer(texto):
    return AdaptadorNLP().extraer(
        solicitud_id="backend-nlp-v7-regresion", texto=texto, moneda="BOB"
    )


def test_rectificacion_de_producto_reconocida():
    resultado = extraer("Una mesa, no, mejor un escritorio")
    assert resultado.estado == "REQUIRES_REVIEW"
    assert resultado.propuesta.nombre.lower() == "escritorio"
    assert resultado.motor["rules_version"] == "prf04-rules-v11"
    assert any(c["decision"] == "REJECTED" for c in resultado.candidatos)


def test_productos_negados_no_crean_propuesta():
    resultado = extraer("No quiero dos mesas y un escritorio")
    assert resultado.estado == "NO_PROPOSAL"
    assert resultado.propuesta is None


def test_componentes_negados_no_se_proponen():
    resultado = extraer("Un escritorio sin cajones ni puertas")
    assert resultado.propuesta is not None
    assert not resultado.propuesta.componentes


def test_multiples_productos_requieren_abstencion():
    resultado = extraer("Dos mesas y tres escritorios")
    assert resultado.estado == "NO_PROPOSAL"
    assert resultado.propuesta is None


def test_total_negociado_conserva_importe_literal():
    resultado = extraer("Tres escritorios, total 100")
    assert resultado.propuesta is not None
    assert resultado.propuesta.precio["mode"] == "TOTAL_NEGOCIADO"
    assert resultado.propuesta.precio["line_total"] == "100.00"
