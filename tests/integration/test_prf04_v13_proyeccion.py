"""Backend v13: proyección al configurador (PostgreSQL aislado en CI)."""

import pytest

from apps.capturas.nlp import AdaptadorNLP
from apps.capturas.proyeccion_prf03 import proyectar

pytestmark = pytest.mark.django_db


def preparar(texto):
    r = AdaptadorNLP().extraer(solicitud_id="backend-v13-proyeccion", texto=texto, moneda="BOB")
    return proyectar(r.resultado_original)


def test_cantidad_pospuesta_proyecta_un_item_y_precio_explicito():
    p = preparar("Mesa de reunión para 10 personas, una pieza, precio unitario 7300")
    assert p["version_proyeccion"] == "PRF04_2"
    assert p["comercial"]["cantidad"] == 1
    assert p["comercial"]["precio_unitario"] == "7300.00"
    assert not any(x["codigo"] == "NO_QUANTITY" for x in p["pendientes"])


def test_accesorio_delimitado_en_especificacion():
    p = preparar(
        "Mesa de reunión para 10 personas, una pieza con dos tomacorrientes "
        "al centro estructura en tablero melamínico, precio unitario 7300"
    )
    assert p["comercial"]["cantidad"] == 1
    assert "2 tomacorrientes al centro" in p["especificacion"]["datos_tecnicos"]["accesorios"]


def test_cantidad_no_inventada_en_piezas_de_vidrio():
    p = preparar("Mesa, una pieza de vidrio en la parte superior, precio unitario 750")
    assert p["comercial"]["cantidad"] is None
    assert any(x["codigo"] == "NO_QUANTITY" for x in p["pendientes"])
