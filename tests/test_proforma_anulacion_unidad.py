from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from apps.core.exceptions import ConflictoComercial
from apps.proformas.services import anular_proforma


class AnularProformaTests(TestCase):
    @patch("apps.proformas.services.valor_catalogo")
    @patch("apps.proformas.services._proforma_bloqueada")
    def test_borrador_puede_anularse(self, lock, catalogo):
        proforma = MagicMock(estado=SimpleNamespace(codigo="BORRADOR"))
        actor = object()
        lock.return_value = proforma
        resultado = anular_proforma.__wrapped__(proforma_id=7, actor=actor)
        lock.assert_called_once_with(7, actor)
        catalogo.assert_called_once_with("ESTADO_PROFORMA", "ANULADA")
        self.assertEqual(resultado.estado, catalogo.return_value)
        proforma.save.assert_called_once_with(update_fields=["estado", "updated_by"])

    @patch("apps.proformas.services._proforma_bloqueada")
    def test_aprobada_no_se_anula(self, lock):
        proforma = MagicMock(estado=SimpleNamespace(codigo="APROBADA"))
        lock.return_value = proforma
        with self.assertRaises(ConflictoComercial):
            anular_proforma.__wrapped__(proforma_id=7, actor=object())
        proforma.save.assert_not_called()
