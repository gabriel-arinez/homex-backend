from datetime import date
from unittest import TestCase
from unittest.mock import MagicMock, patch

from apps.proformas.services import vencer_proformas


class VencerProformasTests(TestCase):
    @patch("apps.proformas.services.valor_catalogo")
    @patch("apps.proformas.services.Proforma.objects")
    @patch("apps.proformas.services.timezone.localdate", return_value=date(2026, 11, 12))
    def test_vence_solo_luego_del_ultimo_dia(self, today, objects, catalogo):
        overdue = MagicMock(fecha=date(2026, 11, 6), validez_oferta=5)
        valid = MagicMock(fecha=date(2026, 11, 7), validez_oferta=5)
        qs = objects.select_for_update.return_value.select_related.return_value.filter
        qs.return_value.iterator.return_value = iter([overdue, valid])
        self.assertEqual(vencer_proformas.__wrapped__(), 1)
        objects.select_for_update.assert_called_once_with(skip_locked=True, of=("self",))
        qs.assert_called_once_with(
            estado__codigo="EN_REVISION", validez_oferta__gt=0, fecha__lt=date(2026, 11, 12)
        )
        overdue.save.assert_called_once_with(update_fields=["estado"])
        valid.save.assert_not_called()
        self.assertIs(overdue.estado, catalogo.return_value)
