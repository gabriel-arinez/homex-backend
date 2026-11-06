from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.conf import settings
from django.db import close_old_connections
from rest_framework.test import APIClient

from apps.proformas.models import Proforma
from apps.proformas.services import vencer_proformas
from apps.proformas.tasks import vencer_proformas_task
from tests.api.test_ap3_proformas_integrales import payload_integral
from tests.factories import vendedor


@pytest.mark.django_db(transaction=True)
def test_vigencia_inclusiva_y_estado_en_base(django_user_model):
    assert settings.CELERY_BEAT_SCHEDULE["vencer-proformas"]["task"] == "proformas.vencer"
    actor = vendedor(django_user_model.objects.create_user(username="vigencia"))
    api = APIClient()
    api.force_authenticate(actor)
    payload = payload_integral(clave=uuid4(), emitir=True)
    payload["validez_oferta"] = 5
    response = api.post("/api/v1/proformas/integral/", payload, format="json")
    assert response.status_code == 201, response.data
    proforma = Proforma.objects.get(pk=response.data["id"])
    assert str(response.data["fecha_vencimiento"]) == str(proforma.fecha + timedelta(days=5))
    with patch(
        "apps.proformas.services.timezone.localdate",
        return_value=proforma.fecha + timedelta(days=5),
    ):
        assert vencer_proformas() == 0
    with patch(
        "apps.proformas.services.timezone.localdate",
        return_value=proforma.fecha + timedelta(days=6),
    ):
        assert vencer_proformas_task.apply().get() == 1
    proforma.refresh_from_db()
    assert proforma.estado.codigo == "VENCIDA"
    assert api.post(f"/api/v1/proformas/{proforma.id}/aprobar/").status_code == 409


@pytest.mark.django_db(transaction=True)
def test_anulacion_respetando_propiedad(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="dueno"))
    otro = vendedor(django_user_model.objects.create_user(username="otro"))
    api = APIClient()
    api.force_authenticate(actor)
    response = api.post(
        "/api/v1/proformas/integral/", payload_integral(clave=uuid4()), format="json"
    )
    assert response.status_code == 201, response.data
    proforma_id = response.data["id"]
    api.force_authenticate(otro)
    assert api.post(f"/api/v1/proformas/{proforma_id}/anular/").status_code == 404
    api.force_authenticate(actor)
    assert api.post(f"/api/v1/proformas/{proforma_id}/anular/").status_code == 200
    assert Proforma.objects.get(pk=proforma_id).estado.codigo == "ANULADA"
    assert api.post(f"/api/v1/proformas/{proforma_id}/anular/").status_code == 409


@pytest.mark.django_db(transaction=True)
def test_aprobacion_rechaza_vencida_y_acepta_ultimo_dia(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="aprobacion-vigencia"))
    api = APIClient()
    api.force_authenticate(actor)
    payload = payload_integral(clave=uuid4(), emitir=True)
    payload["validez_oferta"] = 5
    response = api.post("/api/v1/proformas/integral/", payload, format="json")
    assert response.status_code == 201, response.data
    proforma = Proforma.objects.get(pk=response.data["id"])
    with patch(
        "apps.pedidos.services.timezone.localdate", return_value=proforma.fecha + timedelta(days=6)
    ):
        assert api.post(f"/api/v1/proformas/{proforma.id}/aprobar/").status_code == 409
        assert api.post(f"/api/v1/proformas/{proforma.id}/anular/").status_code == 409
        assert api.post(f"/api/v1/proformas/{proforma.id}/no-concretar/").status_code == 409
    proforma.refresh_from_db()
    assert proforma.estado.codigo == "EN_REVISION"
    with patch(
        "apps.pedidos.services.timezone.localdate", return_value=proforma.fecha + timedelta(days=5)
    ):
        respuesta = api.post(f"/api/v1/proformas/{proforma.id}/aprobar/")
    assert respuesta.status_code == 200, respuesta.data


@pytest.mark.django_db(transaction=True)
def test_aprobar_y_anular_concurrentemente_no_generan_doble_transicion(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="concurrencia"))
    api = APIClient()
    api.force_authenticate(actor)
    response = api.post(
        "/api/v1/proformas/integral/", payload_integral(clave=uuid4(), emitir=True), format="json"
    )
    assert response.status_code == 201, response.data
    pk = response.data["id"]
    barrier = Barrier(2, timeout=10)

    def ejecutar(action):
        close_old_connections()
        client = APIClient()
        client.force_authenticate(actor)
        barrier.wait()
        try:
            return client.post(f"/api/v1/proformas/{pk}/{action}/").status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(ejecutar, "aprobar")
        b = pool.submit(ejecutar, "anular")
        resultados = sorted([a.result(timeout=20), b.result(timeout=20)])
    assert resultados == [200, 409]
    assert Proforma.objects.get(pk=pk).estado.codigo in {"APROBADA", "ANULADA"}


@pytest.mark.django_db(transaction=True)
def test_vencimiento_y_aprobacion_concurrentes_no_crean_pedido(django_user_model):
    from apps.pedidos.models import Pedido

    actor = vendedor(django_user_model.objects.create_user(username="vencimiento-concurrente"))
    api = APIClient()
    api.force_authenticate(actor)
    payload = payload_integral(clave=uuid4(), emitir=True)
    payload["validez_oferta"] = 5
    response = api.post("/api/v1/proformas/integral/", payload, format="json")
    assert response.status_code == 201, response.data
    proforma = Proforma.objects.get(pk=response.data["id"])
    barrier = Barrier(2, timeout=10)

    def ejecutar(action):
        close_old_connections()
        client = APIClient()
        client.force_authenticate(actor)
        barrier.wait()
        try:
            return (
                vencer_proformas()
                if action == "expire"
                else client.post(f"/api/v1/proformas/{proforma.id}/aprobar/").status_code
            )
        finally:
            close_old_connections()

    with patch(
        "apps.proformas.services.timezone.localdate",
        return_value=proforma.fecha + timedelta(days=6),
    ):
        with ThreadPoolExecutor(max_workers=2) as pool:
            expiration = pool.submit(ejecutar, "expire")
            approval = pool.submit(ejecutar, "approve")
            expiration.result(timeout=20)
            assert approval.result(timeout=20) == 409
        vencer_proformas()
    proforma.refresh_from_db()
    assert proforma.estado.codigo == "VENCIDA"
    assert not Pedido.objects.filter(proforma_id=proforma.id).exists()


@pytest.mark.django_db(transaction=True)
def test_sin_validez_expone_fecha_vencimiento_nula(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="sin-vigencia"))
    api = APIClient()
    api.force_authenticate(actor)
    payload = payload_integral(clave=uuid4())
    payload["validez_oferta"] = None
    response = api.post("/api/v1/proformas/integral/", payload, format="json")
    assert response.status_code == 201, response.data
    assert response.data["fecha_vencimiento"] is None
