import importlib
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock


class DesactivarEstadosProformaTests(TestCase):
    def test_only_obsolete_proforma_catalog_values_are_deactivated(self):
        migration = importlib.import_module(
            "apps.proformas.migrations.0013_desactivar_estados_sin_uso"
        )
        apps = MagicMock()
        model = apps.get_model.return_value
        migration.desactivar_estados(
            apps, SimpleNamespace(connection=SimpleNamespace(alias="test"))
        )
        apps.get_model.assert_called_once_with("catalogo", "ValorCatalogo")
        model.objects.using.assert_called_once_with("test")
        queryset = model.objects.using.return_value.filter
        queryset.assert_called_once_with(
            concepto__codigo="ESTADO_PROFORMA", codigo__in=["ENVIADA", "RECHAZADA"]
        )
        queryset.return_value.update.assert_called_once_with(activo=False)
