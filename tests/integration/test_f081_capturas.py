from hashlib import sha256
from uuid import uuid4

import pytest
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from apps.capturas.models import Captura, IntentoCaptura, ItemIA, TrabajoOutbox
from apps.capturas.services import crear_intento, recibir_captura_texto
from apps.proformas.services import crear_proforma
from tests.factories import cliente_persona


def nueva_captura(actor, proforma, *, sufijo=""):
    return Captura.objects.create(
        proforma=proforma,
        vendedor=actor,
        clave_idempotencia=uuid4(),
        capturado_at=timezone.now(),
        texto_transcrito=f"captura {sufijo}",
        created_by=actor,
        updated_by=actor,
    )


@pytest.mark.django_db(transaction=True)
def test_cada_intento_crea_exactamente_un_outbox_y_numero_correlativo(django_user_model):
    actor = django_user_model.objects.create_user(username="f081-outbox")
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    captura = nueva_captura(actor, proforma)

    primero = crear_intento(captura_id=captura.id, input_hash="a" * 64)
    segundo = crear_intento(captura_id=captura.id, input_hash="b" * 64)

    assert [primero.numero_intento, segundo.numero_intento] == [1, 2]
    assert TrabajoOutbox.objects.filter(intento__captura=captura).count() == 2
    assert TrabajoOutbox.objects.get(intento=primero).clave_unica == (
        f"captura:{captura.id}:intento:1"
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("estado", ["FINALIZADO", "ERROR"])
def test_intento_cerrado_no_admite_update_ni_delete(django_user_model, estado):
    actor = django_user_model.objects.create_user(username=f"f081-cerrado-{estado.lower()}")
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    captura = nueva_captura(actor, proforma, sufijo=estado)
    intento = IntentoCaptura.objects.create(
        captura=captura,
        numero_intento=1,
        estado=estado,
        input_hash=sha256(estado.encode()).hexdigest(),
        inicio_at=timezone.now(),
        fin_at=timezone.now(),
        resultado_raw={"estado": estado},
    )

    with pytest.raises(DatabaseError), transaction.atomic():
        IntentoCaptura.objects.filter(pk=intento.pk).update(modelo_nlp_version="otro")
    with pytest.raises(DatabaseError), transaction.atomic():
        IntentoCaptura.objects.filter(pk=intento.pk).delete()

    assert IntentoCaptura.objects.filter(pk=intento.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_item_ia_no_admite_update_ni_delete(django_user_model):
    actor = django_user_model.objects.create_user(username="f081-item-ia")
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    captura = nueva_captura(actor, proforma)
    intento = IntentoCaptura.objects.create(
        captura=captura,
        numero_intento=1,
        estado="FINALIZADO",
        input_hash="c" * 64,
        inicio_at=timezone.now(),
        fin_at=timezone.now(),
        resultado_raw={"items": [{"nombre": "Silla"}]},
    )
    item = ItemIA.objects.create(intento=intento, nombre="Silla", cantidad=1)

    with pytest.raises(DatabaseError), transaction.atomic():
        ItemIA.objects.filter(pk=item.pk).update(nombre="Alterada")
    with pytest.raises(DatabaseError), transaction.atomic():
        ItemIA.objects.filter(pk=item.pk).delete()

    assert ItemIA.objects.get(pk=item.pk).nombre == "Silla"


@pytest.mark.django_db(transaction=True)
def test_fallo_intermedio_no_se_interpreta_como_replay_y_hace_rollback(
    django_user_model,
    monkeypatch,
):
    actor = django_user_model.objects.create_user(username="f081-fallo-intermedio")
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    clave = uuid4()

    def fallar_creacion_intento(**_kwargs):
        raise IntegrityError("fallo intermedio simulado")

    monkeypatch.setattr(
        "apps.capturas.services.crear_intento",
        fallar_creacion_intento,
    )

    with pytest.raises(IntegrityError, match="fallo intermedio simulado"):
        recibir_captura_texto(
            actor=actor,
            clave_idempotencia=clave,
            proforma_id=proforma.id,
            texto="Captura que debe revertirse",
        )

    assert not Captura.objects.filter(clave_idempotencia=clave).exists()
    assert IntentoCaptura.objects.count() == 0
    assert TrabajoOutbox.objects.count() == 0
