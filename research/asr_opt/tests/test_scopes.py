import unittest

from research.asr_opt.scopes import scoped_diagnostics


class ScopeTests(unittest.TestCase):
    def test_scope_and_rejection_evidence_not_lexical_count(self):
        draft = {
            "components": [{"name": "cajones", "quantity": 4, "scope": "cada mueble"}],
            "materials": [{"name": "melamina", "thickness_mm": "22", "scope": "tablero"}],
            "negations": [
                {"scope": "puertas", "restriction": "sin puertas"},
                {"scope": "descuento", "restriction": "sin descuento"},
            ],
        }
        row = {
            "nlp": {
                "item_proposal": {
                    "components": [
                        {"component_id": "a", "name": "Tablero"},
                        {"component_id": "b", "name": "cajones"},
                    ],
                    "thicknesses": [{"component_ref": "a", "unit": "mm", "value": "22"}],
                },
                "candidates": [
                    {
                        "label": "CANTIDAD_INTERNA",
                        "component_ref": "b",
                        "normalized_value": 4,
                        "decision": "ACCEPTED",
                    },
                    {
                        "label": "COMPONENTE",
                        "text": "puertas",
                        "decision": "REJECTED",
                        "reason": "Componente explícitamente excluido",
                    },
                ],
            }
        }
        r = scoped_diagnostics(draft, row)
        self.assertTrue(r["components"][0]["quantity_equal"])
        self.assertEqual(
            r["components"][0]["parent_scope_status"], "NO_EVALUABLE_RELACION_NO_REPRESENTADA"
        )
        self.assertEqual(r["thicknesses"][0]["status"], "IGUAL_VALOR_AMBITO")
        self.assertEqual(r["negations"][0]["status"], "EXCLUSION_NLP_OBSERVADA")
        self.assertEqual(r["negations"][1]["status"], "NO_EVALUABLE_EXCLUSION_NO_REPRESENTADA")
        row["nlp"]["item_proposal"]["thicknesses"][0]["component_ref"] = None
        self.assertEqual(
            scoped_diagnostics(draft, row)["thicknesses"][0]["status"],
            "NO_EVALUABLE_AMBITO_NO_RESUELTO",
        )
