import copy
import unittest

from research.asr_opt.commercial import bind_projection, compare_draft, typed_normalize
from research.asr_opt.evaluation import (
    microaggregate,
    score_reference,
    text_digest,
    validate_references,
)
from research.asr_opt.identity import IDENTITIES, validate_origin
from research.asr_opt.numeric import numeric_normalize


class NumericV2Tests(unittest.TestCase):
    def norm(self, text, convention=None):
        return numeric_normalize(text, convention)["text"]

    def test_contextual_equivalences(self):
        for words, digits in [
            ("cero punto veinte metros", "0.20 metros"),
            ("uno punto veinte metros", "1.20 metros"),
            ("mil ochocientos cincuenta bolivianos", "1850 bolivianos"),
            ("siete mil doscientos ochenta bolivianos", "7280 bolivianos"),
            ("dieciocho milímetros", "18 milímetros"),
            ("noventa centímetros", "90 centímetros"),
            ("cuatro cajones", "4 cajones"),
            ("setenta y cinco centímetros", "75 centímetros"),
            ("dos unidades", "2 unidades"),
            ("diez mil bolivianos", "10 mil bolivianos"),
            ("cero punto cero cinco metros", "0.05 metros"),
            ("cincuenta %", "50%"),
        ]:
            with self.subTest(words=words):
                self.assertEqual(self.norm(words), self.norm(digits))
        self.assertEqual(
            self.norm("diez mil bolivianos", "es-BO"), self.norm("10.000 bolivianos", "es-BO")
        )

    def test_preserves_commercial_risks(self):
        for left, right in [
            ("0.20 metros", "1.20 metros"),
            ("10 bolivianos", "10000 bolivianos"),
            ("sin puertas", "puertas"),
            ("no cajones ni chapa", "cajones y chapa"),
            ("2 por cada escritorio", "2 escritorios"),
            ("total negociado 50 bolivianos", "unitario 50 bolivianos"),
            ("90 cm", "90 m"),
            ("- 2 unidades", "2 unidades"),
            ("−2 unidades", "2 unidades"),
            ("50%", "50"),
            ("+2 unidades", "2 unidades"),
            ("cero punto veinte metros de ancho", "cero punto veinte metros de alto"),
        ]:
            self.assertNotEqual(self.norm(left), self.norm(right))

    def test_ambiguities_and_idempotence(self):
        for t in ["7.280 bolivianos", "7,280 bolivianos", "uno veinte metros", "dos tres unidades"]:
            self.assertTrue(any(e["status"] == "AMBIGUO" for e in numeric_normalize(t)["events"]))
        self.assertNotEqual(self.norm("7.280 metros", "es-BO"), self.norm("7280 metros", "es-BO"))
        for t in [
            "Dieciocho MILÍMETROS",
            "cero punto sesenta metros y dos cajones",
            "7,280 bolivianos",
            "dos mil cien bolivianos",
            "-2 unidades",
            "50%",
        ]:
            self.assertEqual(self.norm(self.norm(t)), self.norm(t))
        self.assertEqual(self.norm("dieciocho mili\u0301metros"), self.norm("18 milímetros"))

    def test_explicit_negative_context(self):
        self.assertEqual(self.norm("menos dos unidades"), self.norm("-2 unidades"))
        self.assertNotEqual(self.norm("menos dos unidades"), self.norm("2 unidades"))

    def test_zero_denominators(self):
        s = {
            "numeric": {
                "wer": {
                    "reference_units": 0,
                    "substitutions": 0,
                    "deletions": 0,
                    "insertions": 3,
                    "errors": 3,
                }
            }
        }
        self.assertIsNone(microaggregate([s], mode="numeric")["rate"])
        self.assertEqual(microaggregate([s], mode="numeric")["insertions"], 3)

    def test_official_gate_not_relaxed(self):
        r = {
            "audio_id": "01",
            "audio_sha256": "a" * 64,
            "verificacion_por_escucha": True,
            "texto_literal_verificado": "dos unidades",
            "notas_acusticas": {},
            "listening_evidence": {
                "method": "human_listening",
                "reviewer": "declarado",
                "reviewed_at": "2026-10-31T00:00:00Z",
                "audio_id": "01",
                "audio_sha256": "a" * 64,
                "text_sha256": text_digest("dos unidades"),
                "playback_ended_events": 1,
            },
            "provenance_audit": {"status": "PENDIENTE_AUDITORIA"},
        }
        original = copy.deepcopy(r)
        with self.assertRaises(ValueError):
            score_reference(r, "2 unidades")
        s = score_reference(r, "2 unidades", provisional=True)
        self.assertEqual(s["numeric"]["wer"]["errors"], 0)
        self.assertEqual(r, original)
        with self.assertRaises(ValueError):
            validate_references([r, r], [r, r], provisional=True)
        r["listening_evidence"]["text_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            score_reference(r, "2 unidades", provisional=True)

    def test_model_revisions_exact(self):
        for model, i in IDENTITIES.items():
            validate_origin(model, i["repo"], i["revision"])
            with self.assertRaises(ValueError):
                validate_origin(model, i["repo"], "f" * 40)

    def test_typed_normalization_preserves_scope_and_unit(self):
        self.assertEqual(typed_normalize({"name": "Tablero"}), typed_normalize({"name": "tablero"}))
        for k, a, b in [
            ("unit", "M", "m"),
            ("axis", "alto", "ancho"),
            ("scope", "cajones", "puertas"),
            ("value", "0.2", "1.2"),
            ("currency", "BOB", "USD"),
        ]:
            self.assertNotEqual(typed_normalize({k: a}), typed_normalize({k: b}))

    def test_critical_pipeline_synthetic_regression(self):
        draft = {
            "item": "mesa",
            "quantity": 2,
            "price": {"value": "12000", "currency": "BOB", "price_mode": "negotiated_total"},
            "measures": [],
            "materials": [],
            "components": [],
            "colors": [],
            "negations": [],
        }
        fields = {
            "product": "mesa",
            "quantity": 2,
            "price.amount": "12.00",
            "price.currency": "BOB",
            "price.mode": "negotiated_total",
            "measures": [],
            "materials": [],
            "components": [],
            "colors": [],
            "thicknesses": [],
            "accessories": [],
            "negations": "INDETERMINADO",
            "proposal": 1,
            "projected_type": None,
        }
        bound = {
            "audio_id": "synthetic",
            "transcription": "Precio total negociado 12 mil bolivianos",
            "commercial_fields": fields,
        }
        result = compare_draft(draft, bound)
        self.assertEqual(result["promotion_gate"], "BLOCK_CRITICAL_PIPELINE")
        self.assertEqual(result["critical_pipeline_amounts"], 1)
        self.assertEqual(result["official_denominator"], 0)

    def test_projection_binding_rejects_corruption(self):
        with self.assertRaises(ValueError):
            bind_projection({"records": []}, {"rows": [{"audio_id": "x"}]})
