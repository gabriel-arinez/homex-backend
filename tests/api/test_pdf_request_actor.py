"""The requesting authenticated seller signs; no client-supplied identity is trusted."""

from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.proformas.services import crear_proforma
from tests.factories import cliente_persona, vendedor


@pytest.mark.django_db(transaction=True)
def test_pdf_uses_request_user_without_reassigning_the_original_seller(django_user_model):
    creator = vendedor(django_user_model.objects.create_user(username="pdf-creator"))
    proforma = crear_proforma(actor=creator, cliente=cliente_persona(creator))
    api = APIClient()
    for username in ("pdf-seller-b", "pdf-seller-c"):
        # Staff already has cross-seller access; do not broaden permissions.
        requester = vendedor(
            django_user_model.objects.create_user(username=username, is_staff=True)
        )
        api.force_authenticate(requester)
        with patch(
            "apps.proformas.api.views.renderizar_proforma_pdf", return_value=b"%PDF-1.4"
        ) as render:
            response = api.get(
                f"/api/v1/proformas/{proforma.pk}/documento-pdf/?usuario_id={creator.pk}"
            )
        assert response.status_code == 200
        render.assert_called_once_with(proforma.pk, usuario=requester)
        assert "no-store" in response["Cache-Control"]
        assert "private" in response["Cache-Control"]
        assert "Authorization" in response["Vary"]
        proforma.refresh_from_db()
        assert proforma.vendedor_id == creator.pk
    api.force_authenticate(None)
    assert api.get(f"/api/v1/proformas/{proforma.pk}/documento-pdf/").status_code == 401
