import unittest

from research.asr_opt.evaluation import (
    align,
    field_errors,
    microaggregate,
    monetary_relation,
    normalize,
    score_reference,
    text_digest,
    validate_references,
)


def reference(text="una mesa"):
    return {
        "audio_id": "01",
        "audio_sha256": "a" * 64,
        "verificacion_por_escucha": True,
        "texto_literal_verificado": text,
        "listening_evidence": {
            "method": "human_listening",
            "reviewer": "test-only",
            "reviewed_at": "2026-10-30T00:00:00+00:00",
            "audio_id": "01",
            "audio_sha256": "a" * 64,
            "text_sha256": text_digest(text),
        },
        "provenance_audit": {
            "audited_by": "test-only",
            "audited_at": "2026-10-30",
            "status": "AUDITADA",
        },
        "notas_acusticas": {"confirmed_silence": not text.strip()},
    }


class EvaluationTests(unittest.TestCase):
    def test_alignment_counts_and_order(self):
        d = align("a b c".split(), "a x c z".split())
        self.assertEqual((d["substitutions"], d["deletions"], d["insertions"]), (1, 0, 1))
        self.assertEqual([x["op"] for x in d["alignment"]], ["H", "S", "H", "I"])
        self.assertEqual(align(["a", "b"], ["a"])["deletions"], 1)

    def test_micro_not_macro(self):
        a = score_reference(reference("a"), "x")
        b = score_reference(reference(" ".join(["a"] * 9)), " ".join(["a"] * 9))
        self.assertEqual(microaggregate([a, b])["rate"], 0.1)

    def test_literal_and_normalized(self):
        result = score_reference(reference("¡MESA blanca!"), "mesa blanca")
        self.assertEqual(result["normalized"]["wer"]["rate"], 0)
        self.assertEqual(result["literal"]["wer"]["errors"], 2)
        self.assertGreater(result["literal"]["cer"]["rate"], 0)

    def test_unicode_symmetric(self):
        self.assertEqual(normalize("Melo\u0301n"), normalize("melón"))

    def test_numeric_separators_not_erased(self):
        self.assertNotEqual(normalize("7.280"), normalize("7,280"))
        self.assertNotEqual(normalize("uno veinte"), normalize("1.20"))
        self.assertNotEqual(normalize("-2"), normalize("2"))
        self.assertNotEqual(normalize("cuatro"), normalize("4"))
        self.assertNotEqual(normalize(".20"), normalize("20"))
        self.assertNotEqual(normalize("1/2"), normalize("1 2"))
        self.assertNotEqual(normalize("50%"), normalize("50"))
        self.assertNotEqual(normalize("(.20)"), normalize("(20)"))
        self.assertNotEqual(normalize("- 2"), normalize("2"))

    def test_money_requires_context(self):
        self.assertEqual(monetary_relation("7.280", "7,280"), "AMBIGUEDAD_MONETARIA")
        self.assertEqual(monetary_relation("5.400", "5400", "es-BO"), "FORMATO_EQUIVALENTE")
        self.assertEqual(monetary_relation("7.280", "7,280", "es-BO"), "CAMBIO_VALOR")
        self.assertEqual(monetary_relation("1.2.3", "123", "es-BO"), "AMBIGUEDAD_MONETARIA")

    def test_pending_never_scores(self):
        r = reference()
        r["verificacion_por_escucha"] = False
        result = score_reference(r, "prediccion")
        self.assertIsNone(result["literal"])
        self.assertIsNone(microaggregate([result])["rate"])

    def test_boolean_is_not_gold(self):
        r = reference()
        del r["listening_evidence"]
        with self.assertRaises(ValueError):
            score_reference(r, "una mesa")

    def test_changed_reference_invalidates_evidence(self):
        r = reference()
        r["texto_literal_verificado"] = "otro texto"
        with self.assertRaises(ValueError):
            score_reference(r, "otro texto")

    def test_ids_hashes_and_duplicates(self):
        r = reference()
        for records, corpus in [
            ([r, r], [r]),
            ([r], [{**r, "audio_sha256": "b" * 64}]),
            ([r], [{**r, "audio_id": "02"}]),
        ]:
            with self.assertRaises(ValueError):
                validate_references(records, corpus)

    def test_inaudible_and_empty(self):
        r = reference()
        r["notas_acusticas"] = {"uncertain_spans": [{"start": 0, "end": 1}]}
        self.assertIsNone(score_reference(r, "palabras")["literal"])
        result = score_reference(reference(""), "palabras inventadas")
        self.assertIsNone(result["literal"]["wer"]["rate"])
        self.assertEqual(result["literal"]["wer"]["insertions"], 2)

    def test_commercial_error_types_and_severity(self):
        r = field_errors(
            {
                "price": {"value": "50", "original_text": "cincuenta"},
                "negation": "sin puertas",
                "unit": "cm",
                "material": None,
                "color": "INDETERMINADO",
            },
            {
                "price": {"value": "50", "original_text": "50"},
                "unit": "m",
                "material": "melamina",
                "color": "rojo",
            },
        )
        rows = {x["field"]: x for x in r["fields"]}
        self.assertEqual(rows["price"]["error"], "FORMATO")
        self.assertEqual(rows["negation"]["error"], "OMISION")
        self.assertEqual(rows["negation"]["severity"], "CRITICA")
        self.assertEqual(rows["unit"]["error"], "SUSTITUCION")
        self.assertEqual(rows["material"]["error"], "INVENCION")
        self.assertEqual(rows["color"]["error"], "NO_EVALUABLE")
        self.assertEqual(r["denominator"], 4)


class EndToEndEvaluatorTests(unittest.TestCase):
    def test_missing_gold_cli_core_never_emits_rates(self):
        from research.asr_opt.evaluate import evaluate

        r = reference()
        r["verificacion_por_escucha"] = False
        h = {
            "audio_id": r["audio_id"],
            "audio_sha256": r["audio_sha256"],
            "transcription": "hipótesis automática",
        }
        result = evaluate([r], [r], [h])
        self.assertEqual(result["status"], "PENDIENTE_GOLD")
        self.assertIsNone(result["micro"]["normalized"]["cer"]["rate"])
        self.assertEqual(result["micro"]["literal"]["wer"]["scored_audios"], 0)
        with self.assertRaises(ValueError):
            evaluate([r], [r], [{**h, "audio_sha256": "b" * 64}])

    def test_known_character_alignment_and_reconstruction(self):
        result = align(list("kitten"), list("sitting"))
        self.assertEqual(result["errors"], 3)
        self.assertEqual(
            "".join(x["reference"] for x in result["alignment"] if x["reference"] is not None),
            "kitten",
        )
        self.assertEqual(
            "".join(x["hypothesis"] for x in result["alignment"] if x["hypothesis"] is not None),
            "sitting",
        )


class CommercialAnnotationTests(unittest.TestCase):
    def test_missing_annotation_is_not_hallucination(self):
        result = field_errors({}, {"price": "500"})
        self.assertEqual(result["denominator"], 0)
        self.assertEqual(result["fields"][0]["error"], "NO_EVALUABLE")
        self.assertEqual(
            field_errors({"price": None}, {"price": "500"})["fields"][0]["error"], "INVENCION"
        )

    def test_commercial_cli_requires_audited_text_and_typed_fields(self):
        from research.asr_opt.evaluate import evaluate

        r = reference()
        r["campos_comerciales_gold"] = {
            "price": {"value": "50", "currency": "BOB", "price_mode": "unit"}
        }
        h = {
            "audio_id": r["audio_id"],
            "audio_sha256": r["audio_sha256"],
            "transcription": "una mesa",
            "commercial_fields": {
                "price": {"value": "500", "currency": "BOB", "price_mode": "unit"}
            },
        }
        result = evaluate([r], [r], [h])
        self.assertEqual(result["commercial"][0]["errors"], 1)
        self.assertEqual(result["commercial"][0]["denominator"], 1)
        r["verificacion_por_escucha"] = False
        self.assertIsNone(evaluate([r], [r], [h])["commercial"][0]["errors"])
