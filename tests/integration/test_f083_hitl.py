from decimal import Decimal
from threading import Barrier, Lock, Thread
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import DatabaseError, close_old_connections, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.capturas.hitl import confirmar_captura
from apps.capturas.models import (
    Captura,
    EvaluacionNLP,
    IntentoCaptura,
    ItemHumano,
    ItemIA,
)
from apps.pedidos.models import Pedido
from apps.pedidos.services import aprobar_proforma
from apps.proformas.models import DetalleProforma, EspecificacionMueble
from apps.proformas.services import (
    actualizar_detalle,
    agregar_detalle,
    crear_especificacion,
    crear_proforma,
    enviar_proforma,
)
from tests.factories import cliente_persona, valor, vendedor


def escenario_hitl(django_user_model, usuario, **item_ia_datos):
    actor = vendedor(django_user_model.objects.create_user(username=usuario))
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor, sufijo=usuario))
    captura = Captura.objects.create(
        proforma=proforma,
        vendedor=actor,
        clave_idempotencia=uuid4(),
        estado="COMPLETADA",
        capturado_at=timezone.now(),
        texto_transcrito="Dos mesas, total cien bolivianos",
        created_by=actor,
        updated_by=actor,
    )
    intento = IntentoCaptura.objects.create(
        captura=captura,
        numero_intento=1,
        estado="PENDIENTE",
        input_hash="a" * 64,
        inicio_at=timezone.now(),
    )
    IntentoCaptura.objects.filter(pk=intento.pk).update(
        estado="FINALIZADO",
        etapa_alcanzada="COMPLETO",
        fin_at=timezone.now(),
        resultado_raw={
            "schema_version": "1.0",
            "item_proposal": {
                clave: str(valor) if isinstance(valor, Decimal) else valor
                for clave, valor in item_ia_datos.items()
            },
        },
    )
    intento.refresh_from_db()
    base = {
        "nombre": "Mesa a medida",
        "cantidad": 2,
        "precio_total": Decimal("100.00"),
    }
    base.update(item_ia_datos)
    item_ia = ItemIA.objects.create(intento=intento, **base)
    return actor, proforma, captura, intento, item_ia


def payload_confirmacion(intento, item_ia):
    return {
        "intento_id": intento.id,
        "item_ia_id": item_ia.id,
        "item_corregido": {
            "nombre": "Mesa a medida",
            "cantidad": 2,
            "dimensiones": {"ancho": "1800 mm"},
            "accesorios": ["2 cajones"],
            "observaciones": "Validado por vendedor",
        },
        "linea_comercial": {
            "tipo_item_id": valor("TIPO_ITEM", "MUEBLE_MEDIDA").id,
            "unidad_id": valor("UNIDAD_MEDIDA", "PIEZA").id,
            "modo_calculo": "TOTAL_NEGOCIADO",
            "importe_negociado": Decimal("100.00"),
            "tipo_mueble_id": valor("TIPO_MUEBLE", "MESA_REUNION").id,
        },
    }


@pytest.mark.django_db(transaction=True)
def test_confirmacion_hitl_es_atomica_y_no_aprueba_proforma(django_user_model):
    actor, proforma, captura, intento, item_ia = escenario_hitl(django_user_model, "f083-exito")
    resultado = confirmar_captura(
        captura_id=captura.id,
        actor=actor,
        **payload_confirmacion(intento, item_ia),
    )

    captura.refresh_from_db()
    proforma.refresh_from_db()
    assert captura.proforma_detalle_id == resultado.detalle.id
    assert proforma.estado.codigo == "BORRADOR"
    assert not Pedido.objects.filter(proforma=proforma).exists()
    assert DetalleProforma.objects.filter(proforma=proforma).count() == 1
    assert EspecificacionMueble.objects.filter(proforma_detalle=resultado.detalle).count() == 1
    assert ItemHumano.objects.filter(item_ia=item_ia).count() == 1
    assert EvaluacionNLP.objects.filter(item_humano=resultado.item_humano).count() == 1
    assert resultado.detalle.total == Decimal("100.00")
    assert resultado.item_humano.precio_total == Decimal("100.00")
    assert resultado.evaluacion.version_metrica == "field-comparison-v1"
    assert resultado.evaluacion.inicio_revision_at is None
    assert resultado.evaluacion.tiempo_revision_ms is None
    assert resultado.evaluacion.fin_revision_at == resultado.item_humano.revisado_at


@pytest.mark.django_db(transaction=True)
def test_propuesta_parcial_puede_completarse_y_no_inventa_precision(django_user_model):
    actor, _, captura, intento, item_ia = escenario_hitl(
        django_user_model,
        "f083-parcial",
        nombre="Mesa a medida",
        cantidad=None,
        precio_total=None,
    )
    resultado = confirmar_captura(
        captura_id=captura.id,
        actor=actor,
        **payload_confirmacion(intento, item_ia),
    )
    evaluacion = resultado.evaluacion
    assert evaluacion.campos_totales == 1
    assert evaluacion.campos_agregados >= 3
    assert evaluacion.precision_campo == Decimal("1")
    assert evaluacion.precision_item == Decimal("0")


@pytest.mark.django_db(transaction=True)
def test_sin_denominador_persiste_precision_null(django_user_model):
    actor, _, captura, intento, item_ia = escenario_hitl(
        django_user_model,
        "f083-sin-denominador",
        nombre=None,
        cantidad=None,
        precio_total=None,
    )
    resultado = confirmar_captura(
        captura_id=captura.id,
        actor=actor,
        **payload_confirmacion(intento, item_ia),
    )
    assert resultado.evaluacion.campos_totales == 0
    assert resultado.evaluacion.precision_campo is None
    assert resultado.evaluacion.precision_item is None


@pytest.mark.django_db(transaction=True)
def test_doble_confirmacion_se_rechaza_sin_duplicar(django_user_model):
    actor, proforma, captura, intento, item_ia = escenario_hitl(django_user_model, "f083-doble")
    payload = payload_confirmacion(intento, item_ia)
    confirmar_captura(captura_id=captura.id, actor=actor, **payload)
    with pytest.raises(APIException) as error:
        confirmar_captura(captura_id=captura.id, actor=actor, **payload)
    assert error.value.status_code == 409
    assert DetalleProforma.objects.filter(proforma=proforma).count() == 1
    assert ItemHumano.objects.filter(item_ia=item_ia).count() == 1
    assert EvaluacionNLP.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_edicion_comercial_posterior_no_reescribe_evidencia_hitl(django_user_model):
    actor, _, captura, intento, item_ia = escenario_hitl(
        django_user_model, "f083-edicion-posterior"
    )
    resultado = confirmar_captura(
        captura_id=captura.id,
        actor=actor,
        **payload_confirmacion(intento, item_ia),
    )
    evidencia_humana = {
        "nombre": resultado.item_humano.nombre,
        "precio_total": resultado.item_humano.precio_total,
    }
    metricas = {
        "campos_corregidos": resultado.evaluacion.campos_corregidos,
        "precision_campo": resultado.evaluacion.precision_campo,
    }
    actualizar_detalle(
        detalle_id=resultado.detalle.id,
        actor=actor,
        nombre="Mesa comercial editada",
        precio_unitario=Decimal("75.00"),
        modo_calculo="PRECIO_UNITARIO",
        importe_negociado=None,
    )
    resultado.item_humano.refresh_from_db()
    resultado.evaluacion.refresh_from_db()
    assert {
        "nombre": resultado.item_humano.nombre,
        "precio_total": resultado.item_humano.precio_total,
    } == evidencia_humana
    assert {
        "campos_corregidos": resultado.evaluacion.campos_corregidos,
        "precision_campo": resultado.evaluacion.precision_campo,
    } == metricas


@pytest.mark.django_db(transaction=True)
def test_fallo_intermedio_revierte_toda_la_confirmacion(django_user_model):
    actor, proforma, captura, intento, item_ia = escenario_hitl(django_user_model, "f083-rollback")
    with patch.object(EvaluacionNLP.objects, "create", side_effect=RuntimeError("fallo")):
        with pytest.raises(RuntimeError, match="fallo"):
            confirmar_captura(
                captura_id=captura.id,
                actor=actor,
                **payload_confirmacion(intento, item_ia),
            )
    captura.refresh_from_db()
    assert captura.proforma_detalle_id is None
    assert not DetalleProforma.objects.filter(proforma=proforma).exists()
    assert not ItemHumano.objects.filter(item_ia=item_ia).exists()
    assert not EvaluacionNLP.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_correccion_y_evaluacion_finales_son_inmutables_en_postgresql(django_user_model):
    actor, _, captura, intento, item_ia = escenario_hitl(django_user_model, "f083-inmutable")
    resultado = confirmar_captura(
        captura_id=captura.id,
        actor=actor,
        **payload_confirmacion(intento, item_ia),
    )
    with pytest.raises(DatabaseError), transaction.atomic():
        ItemHumano.objects.filter(pk=resultado.item_humano.id).update(nombre="Alterado")
    with pytest.raises(DatabaseError), transaction.atomic():
        EvaluacionNLP.objects.filter(pk=resultado.evaluacion.id).delete()


@pytest.mark.django_db(transaction=True)
def test_total_negociado_conserva_monto_exacto_sin_recalcular_desde_unitario(
    django_user_model,
):
    actor, _, captura, intento, item_ia = escenario_hitl(
        django_user_model, "f083-total-exacto", cantidad=3, precio_total=Decimal("100.00")
    )
    payload = payload_confirmacion(intento, item_ia)
    payload["item_corregido"]["cantidad"] = 3
    resultado = confirmar_captura(captura_id=captura.id, actor=actor, **payload)
    assert resultado.detalle.precio_unitario == Decimal("33.33")
    assert resultado.detalle.importe_negociado == Decimal("100.00")
    assert resultado.detalle.total == Decimal("100.00")
    assert resultado.item_humano.precio_total == Decimal("100.00")


@pytest.mark.django_db(transaction=True)
def test_hitl_rechaza_unitario_en_total_negociado_y_unidad_no_comercial(
    django_user_model,
):
    actor, proforma, captura, intento, item_ia = escenario_hitl(
        django_user_model, "f083-semantica-comercial"
    )
    payload = payload_confirmacion(intento, item_ia)
    payload["linea_comercial"]["precio_unitario"] = Decimal("50.00")
    with pytest.raises(APIException):
        confirmar_captura(captura_id=captura.id, actor=actor, **payload)
    payload["linea_comercial"].pop("precio_unitario")
    payload["linea_comercial"]["unidad_id"] = valor("UNIDAD_MEDIDA", "CAJA").id
    with pytest.raises(APIException):
        confirmar_captura(captura_id=captura.id, actor=actor, **payload)
    assert not DetalleProforma.objects.filter(proforma=proforma).exists()
    assert not ItemHumano.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_resultado_atrasado_no_puede_incorporarse(django_user_model):
    actor, _, captura, intento, item_ia = escenario_hitl(django_user_model, "f083-atrasado")
    nuevo = IntentoCaptura.objects.create(
        captura=captura,
        numero_intento=2,
        estado="PENDIENTE",
        input_hash="b" * 64,
        inicio_at=timezone.now(),
    )
    IntentoCaptura.objects.filter(pk=nuevo.pk).update(
        estado="FINALIZADO",
        etapa_alcanzada="COMPLETO",
        fin_at=timezone.now(),
        resultado_raw={"schema_version": "1.0", "item_proposal": {"name": "Nueva"}},
    )
    nuevo.refresh_from_db()
    ItemIA.objects.create(intento=nuevo, nombre="Nueva", cantidad=1)
    with pytest.raises(APIException) as error:
        confirmar_captura(
            captura_id=captura.id,
            actor=actor,
            **payload_confirmacion(intento, item_ia),
        )
    assert error.value.status_code == 400
    assert captura.proforma_detalle_id is None
    assert not ItemHumano.objects.exists()


@pytest.mark.concurrency
@pytest.mark.django_db(transaction=True)
def test_confirmaciones_concurrentes_crean_una_sola_linea(django_user_model):
    actor, proforma, captura, intento, item_ia = escenario_hitl(
        django_user_model, "f083-concurrente"
    )
    payload = payload_confirmacion(intento, item_ia)
    barrera = Barrier(3)
    candado = Lock()
    resultados = []

    def ejecutar():
        close_old_connections()
        try:
            usuario = django_user_model.objects.get(pk=actor.pk)
            barrera.wait(timeout=5)
            confirmar_captura(captura_id=captura.id, actor=usuario, **payload)
            valor_resultado = "ok"
        except APIException as exc:
            valor_resultado = exc.status_code
        finally:
            close_old_connections()
        with candado:
            resultados.append(valor_resultado)

    hilos = [Thread(target=ejecutar, daemon=True) for _ in range(2)]
    for hilo in hilos:
        hilo.start()
    barrera.wait(timeout=5)
    for hilo in hilos:
        hilo.join(timeout=10)

    assert not any(hilo.is_alive() for hilo in hilos)
    assert sorted(resultados, key=str) == [409, "ok"]
    assert DetalleProforma.objects.filter(proforma=proforma).count() == 1
    assert ItemHumano.objects.filter(item_ia=item_ia).count() == 1


@pytest.mark.django_db(transaction=True)
def test_pipeline_proyecta_estructuras_nlp_al_json_comercial_v1(django_user_model):
    from apps.capturas.pipeline import procesar_intento
    from apps.capturas.services import recibir_captura_texto

    actor = vendedor(django_user_model.objects.create_user(username="f083-proyeccion-v1"))
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor, sufijo="v1"))
    recepcion = recibir_captura_texto(
        actor=actor,
        clave_idempotencia=uuid4(),
        proforma_id=proforma.id,
        texto="Un escritorio de 18 milímetros con dos cajones",
    )
    assert procesar_intento(intento_id=recepcion.intento.id) == "FINALIZADO"
    item = ItemIA.objects.get(intento=recepcion.intento)
    assert item.espesor == {"espesor": "18 milímetros"}
    assert item.accesorios == ["cajones"]


def _detalle_valido_para_emision(actor, proforma, *, nombre):
    detalle = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre=nombre,
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("50.00"),
    )
    crear_especificacion(
        detalle_id=detalle.id,
        actor=actor,
        schema_version=1,
    )
    return detalle


@pytest.mark.django_db(transaction=True)
def test_confirmacion_hitl_admite_enviada_y_no_cambia_estado(django_user_model):
    actor, proforma, captura, intento, item_ia = escenario_hitl(django_user_model, "f083-enviada")
    _detalle_valido_para_emision(actor, proforma, nombre="Línea previa")
    enviar_proforma(proforma_id=proforma.id, actor=actor)

    resultado = confirmar_captura(
        captura_id=captura.id,
        actor=actor,
        **payload_confirmacion(intento, item_ia),
    )

    proforma.refresh_from_db()
    assert proforma.estado.codigo == "ENVIADA"
    assert resultado.detalle.proforma_id == proforma.id
    assert DetalleProforma.objects.filter(proforma=proforma).count() == 2


@pytest.mark.django_db(transaction=True)
def test_confirmacion_hitl_rechaza_proforma_aprobada_sin_evidencia_parcial(
    django_user_model,
):
    actor, proforma, captura, intento, item_ia = escenario_hitl(django_user_model, "f083-aprobada")
    _detalle_valido_para_emision(actor, proforma, nombre="Línea aprobable")
    enviar_proforma(proforma_id=proforma.id, actor=actor)
    aprobar_proforma(proforma_id=proforma.id, actor=actor)

    with pytest.raises(APIException) as error:
        confirmar_captura(
            captura_id=captura.id,
            actor=actor,
            **payload_confirmacion(intento, item_ia),
        )

    proforma.refresh_from_db()
    assert error.value.status_code == 400
    assert proforma.estado.codigo == "APROBADA"
    assert DetalleProforma.objects.filter(proforma=proforma).count() == 1
    assert not ItemHumano.objects.exists()
    assert not EvaluacionNLP.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_vinculo_comercial_de_captura_confirmada_es_inmutable(django_user_model):
    actor, proforma, captura, intento, item_ia = escenario_hitl(
        django_user_model, "f083-vinculo-inmutable"
    )
    resultado = confirmar_captura(
        captura_id=captura.id,
        actor=actor,
        **payload_confirmacion(intento, item_ia),
    )
    otro = agregar_detalle(
        proforma_id=proforma.id,
        actor=actor,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre="Otro mueble",
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        precio_unitario=Decimal("20.00"),
    )

    with pytest.raises(DatabaseError), transaction.atomic():
        Captura.objects.filter(pk=captura.pk).update(proforma_detalle=otro)

    captura.refresh_from_db()
    assert captura.proforma_detalle_id == resultado.detalle.id
