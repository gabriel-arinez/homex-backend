from uuid import uuid4

import pytest

from apps.capturas.models import ItemIA
from apps.capturas.nlp import ContratoNLPNoSoportado
from apps.capturas.pipeline import procesar_intento
from apps.capturas.services import recibir_captura_texto
from apps.proformas.services import crear_proforma
from tests.factories import cliente_persona, vendedor


class AdaptadorContratoIncompatible:
    def extraer(self, **kwargs):
        raise ContratoNLPNoSoportado("schema_version 2.0 no soportada")


@pytest.mark.django_db(transaction=True)
def test_contrato_nlp_incompatible_cierra_intento_con_error_seguro(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="f084-contrato"))
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor, sufijo="f084"))
    recepcion = recibir_captura_texto(
        actor=actor,
        clave_idempotencia=uuid4(),
        proforma_id=proforma.id,
        texto="Tres escritorios por cien bolivianos",
    )

    assert (
        procesar_intento(
            intento_id=recepcion.intento.id,
            adaptador_nlp=AdaptadorContratoIncompatible(),
        )
        == "ERROR"
    )

    recepcion.intento.refresh_from_db()
    recepcion.captura.refresh_from_db()
    assert recepcion.intento.estado == "ERROR"
    assert recepcion.intento.error_codigo == "NLP_CONTRACT_INCOMPATIBLE"
    assert recepcion.intento.error_detalle == (
        "El contrato del motor NLP no es compatible con el backend."
    )
    assert "2.0" not in recepcion.intento.error_detalle
    assert recepcion.captura.estado == "ERROR"
    assert not ItemIA.objects.filter(intento=recepcion.intento).exists()
