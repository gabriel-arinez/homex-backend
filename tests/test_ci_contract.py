import pytest
from django.db import connection


@pytest.mark.concurrency
@pytest.mark.django_db
def test_concurrency_job_uses_postgresql():
    """Mantiene el job activo hasta que F07.2 agregue concurrencia de dominio."""
    assert connection.vendor == "postgresql"
