from datetime import timedelta

import pytest
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.test import APIClient

from apps.proformas.models import Proforma
from apps.proformas.services import crear_proforma
from tests.factories import vendedor


@pytest.mark.django_db(transaction=True)
def test_bandeja_expone_hora_real_y_preserva_fechas_historicas(django_user_model):
    actor = vendedor(django_user_model.objects.create_user(username="fe04-created-at"))
    reciente = crear_proforma(actor=actor, titulo="Reciente")
    anterior = crear_proforma(actor=actor, titulo="Histórica")
    Proforma.objects.filter(pk=anterior.pk).update(creado_en=None)

    assert reciente.creado_en is not None
    assert timezone.is_aware(reciente.creado_en)
    assert abs(timezone.now() - reciente.creado_en) < timedelta(minutes=2)

    api = APIClient()
    api.force_authenticate(actor)
    response = api.get("/api/v1/proformas/", {"page_size": 10})
    assert response.status_code == 200
    data = {item["id"]: item for item in response.data["results"]}
    parsed = parse_datetime(data[reciente.pk]["creado_en"])
    assert parsed is not None and timezone.is_aware(parsed)
    assert abs(parsed - reciente.creado_en) < timedelta(seconds=1)
    assert data[anterior.pk]["creado_en"] is None
    assert data[anterior.pk]["fecha"] == anterior.fecha.isoformat()

    original_timestamp = reciente.creado_en
    updated = api.patch(
        f"/api/v1/proformas/{reciente.pk}/",
        {"titulo": "Editada"},
        format="json",
    )
    assert updated.status_code == 200
    reciente.refresh_from_db()
    assert reciente.creado_en == original_timestamp
