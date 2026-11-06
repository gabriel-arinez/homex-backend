from datetime import date
from unittest import TestCase

from apps.proformas.vigencia import esta_vencida, fecha_limite


class VigenciaProformaTests(TestCase):
    def test_ultimo_dia_es_inclusivo(self):
        creacion = date(2026, 11, 6)
        self.assertEqual(fecha_limite(creacion, 5), date(2026, 11, 11))
        self.assertFalse(esta_vencida(creacion, 5, date(2026, 11, 11)))
        self.assertTrue(esta_vencida(creacion, 5, date(2026, 11, 12)))

    def test_sin_plazo_no_vence(self):
        self.assertIsNone(fecha_limite(date(2026, 11, 6), None))
        self.assertFalse(esta_vencida(date(2026, 11, 6), None, date(2030, 1, 1)))

    def test_rechaza_plazos_no_positivos(self):
        with self.assertRaises(ValueError):
            fecha_limite(date(2026, 11, 6), 0)
