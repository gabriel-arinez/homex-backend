import unittest

from research.asr_opt.scope_gate import scope_changes


class ScopeGateTests(unittest.TestCase):
    def row(self, ref, decision="ACCEPTED", component="a"):
        return {
            "nlp": {
                "item_proposal": {"components": [{"component_id": component, "name": "panel"}]},
                "candidates": [
                    {
                        "label": "COLOR",
                        "text": "azul",
                        "normalized_value": None,
                        "component_ref": ref,
                        "decision": decision,
                    }
                ],
            }
        }

    def test_scope_identity_uses_names_not_ephemeral_ids(self):
        self.assertEqual(scope_changes(self.row("a"), self.row("other", component="other")), [])
        self.assertEqual(len(scope_changes(self.row(None), self.row("a"))), 1)

    def test_exclusion_transition_requires_review(self):
        events = scope_changes(self.row(None, "REJECTED"), self.row(None))
        self.assertEqual(events[0]["gate"], "BLOCK_SCOPE_REVIEW")
        self.assertEqual(events[0]["attribution"], "NO_ATRIBUIBLE_SIN_VALIDACION_DE_AMBITO")


class UnitDiagnosticTests(unittest.TestCase):
    def test_orthography_is_not_a_lost_unit_or_scale_conversion(self):
        from research.asr_opt.scope_gate import canonical_unit_sequence

        self.assertEqual(
            canonical_unit_sequence("32 milimetros"), canonical_unit_sequence("32 Milímetros")
        )
        self.assertEqual(canonical_unit_sequence("1 metro y 2 centímetros"), ["m", "cm"])
        self.assertNotEqual(canonical_unit_sequence("3 m"), canonical_unit_sequence("3 cm"))
        self.assertNotEqual(canonical_unit_sequence("3 M"), canonical_unit_sequence("3 m"))
