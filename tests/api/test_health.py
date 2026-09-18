from django.test import Client


def test_health_is_public():
    response = Client().get("/api/v1/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
