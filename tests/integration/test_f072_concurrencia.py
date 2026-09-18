from decimal import Decimal
from threading import Event, Thread

import pytest
from django.db import close_old_connections, transaction

from apps.proformas.services import (
    actualizar_detalle,
    agregar_detalle,
    crear_especificacion,
    crear_proforma,
    enviar_proforma,
)
from tests.factories import cliente_persona, valor


@pytest.mark.concurrency
@pytest.mark.django_db(transaction=True)
def test_edicion_y_envio_de_proforma_se_serializan_con_for_update(django_user_model):
    actor = django_user_model.objects.create_user(username="vendedor-concurrencia")
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre="Mueble",
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("50.00"),
    )
    crear_especificacion(detalle_id=detalle.id, actor=actor, dimensiones={"ancho": "1 m"})
    inicio, terminado = Event(), Event()
    resultado = {}

    def enviar_en_otra_conexion():
        close_old_connections()
        inicio.set()
        try:
            resultado["proforma"] = enviar_proforma(proforma_id=proforma.id, actor=actor)
        except Exception as exc:  # la aserción se realiza en el hilo principal
            resultado["error"] = exc
        finally:
            close_old_connections()
            terminado.set()

    with transaction.atomic():
        type(proforma).objects.select_for_update().get(pk=proforma.id)
        hilo = Thread(target=enviar_en_otra_conexion)
        hilo.start()
        assert inicio.wait(timeout=2)
        assert not terminado.wait(timeout=0.15)
        actualizar_detalle(detalle_id=detalle.id, actor=actor, precio_unitario=Decimal("60.00"))
    assert terminado.wait(timeout=5)
    hilo.join(timeout=1)
    assert "error" not in resultado
    resultado["proforma"].refresh_from_db()
    assert resultado["proforma"].estado.codigo == "ENVIADA"
    assert resultado["proforma"].total == Decimal("60.00")
