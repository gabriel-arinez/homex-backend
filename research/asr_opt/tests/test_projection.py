import unittest

from research.asr_opt.projection import clean, differences


class ProjectionTests(unittest.TestCase):
    def test_semantic_values_scopes_kept(self):
        left = {
            "value": "2",
            "unit": "cm",
            "axis": "ancho",
            "component_ref": "pieza-1",
            "evidence_ids": ["a"],
            "original_text": "dos cm",
            "start": 1,
        }
        right = {**left, "evidence_ids": ["b"], "original_text": "2 cm", "start": 12}
        self.assertEqual(clean(left), clean(right))
        for field, value in [
            ("value", "3"),
            ("unit", "m"),
            ("axis", "alto"),
            ("component_ref", "pieza-2"),
        ]:
            self.assertEqual(
                differences(clean(left), clean({**right, field: value}))[0]["field"], "/" + field
            )

    def test_difference_never_claims_acoustic_correctness(self):
        result = differences({"price": "50"}, {"price": None})
        self.assertEqual(result[0]["acoustic_correctness"], "PENDIENTE_GOLD")
        self.assertEqual(differences(None, None), [])


class NumericProjectionTests(unittest.TestCase):
    def test_words_and_digits_do_not_create_quantity_error(self):
        left = {
            "label": "CANTIDAD_INTERNA",
            "text": "dos",
            "normalized_value": 2,
            "component_ref": "pieza-1",
        }
        right = {**left, "text": "2"}
        self.assertEqual(clean(left), clean(right))
        self.assertNotEqual(clean(left), clean({**right, "component_ref": "pieza-2"}))
        self.assertNotEqual(clean(left), clean({**right, "normalized_value": 3}))
