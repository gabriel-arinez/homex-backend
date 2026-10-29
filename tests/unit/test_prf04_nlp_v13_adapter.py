"""Backend v13: cantidades comerciales pospuestas y límites de accesorios."""

import pytest

from apps.capturas.nlp import AdaptadorNLP


@pytest.fixture(autouse=True)
def catalogo_estructural():
    yield


@pytest.fixture(autouse=True)
def transiciones_pedido():
    yield


def extraer(texto):
    return AdaptadorNLP().extraer(solicitud_id="backend-v13-cantidad", texto=texto, moneda="BOB")


@pytest.mark.parametrize(
    ("texto", "cantidad"),
    [
        ("Mesa de reunión para 10 personas, una pieza tamaño 2 metros", 1),
        ("Escritorio, dos piezas. Color a elección", 2),
        ("Ropero 3 unidades, alto dos metros", 3),
        ("Vitrina una pieza precio unitario 750", 1),
        ("Mesa, dos pzas., color blanco", 2),
    ],
)
def test_cantidad_pospuesta_sin_confundir_capacidad(texto, cantidad):
    r = extraer(texto)
    assert r.estado == "REQUIRES_REVIEW"
    assert r.motor["rules_version"] == "prf04-rules-v16"
    assert r.motor["mode"] == "RULES_ONLY"
    assert r.propuesta is not None
    assert r.propuesta.cantidad == cantidad
    assert all(r.texto_original[x["start"] : x["end"]] == x["text"] for x in r.candidatos)


@pytest.mark.parametrize(
    "texto",
    [
        "Mesa de reunión para 10 personas, color blanco",
        "Mesa, dos puertas y tres cajones",
        "Mesa, una pieza de vidrio en la parte superior",
        "Mesa con dos piezas de vidrio",
        "Mesa, dos piezas, no mejor tres piezas",
    ],
)
def test_cantidad_no_inventada_en_capacidad_componentes_o_ambiguos(texto):
    r = extraer(texto)
    assert r.propuesta is not None
    assert r.propuesta.cantidad is None
    assert any(w["code"] == "NO_QUANTITY" for w in r.advertencias)


def test_precio_unitario_explicito_con_cantidad_uno():
    r = extraer("Mesa de reunión para 10 personas, una pieza tamaño 2 metros, precio unitario 7300")
    assert r.propuesta.cantidad == 1
    assert r.propuesta.precio["mode"] == "PRECIO_UNITARIO"
    assert r.propuesta.precio["line_total"] == "7300.00"
    assert r.propuesta.precio["unit_price_input"] == "7300.00"


def test_total_negociado_se_conserva_sin_venta_unitaria_inventada():
    r = extraer("Mesa, dos unidades, alto 75 centímetros, total 7600 bolivianos")
    assert r.propuesta.cantidad == 2
    assert r.propuesta.precio["mode"] == "TOTAL_NEGOCIADO"
    assert r.propuesta.precio["line_total"] == "7600.00"


def test_accesorio_no_absorbe_inicio_de_estructura():
    texto = (
        "Mesa de reunión para 10 personas, una pieza con dos tomacorrientes "
        "al centro estructura en tablero melamínico, precio unitario 7300"
    )
    r = extraer(texto)
    assert r.propuesta.cantidad == 1
    assert [a["name"] for a in r.propuesta.accesorios] == ["tomacorrientes al centro"]
    assert r.propuesta.accesorios[0]["quantity"] == 2
    assert all(texto[x["start"] : x["end"]] == x["text"] for x in r.candidatos)
