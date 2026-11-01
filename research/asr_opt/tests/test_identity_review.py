import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.asr_opt.commercial import bind_projection, dimension_comparisons
from research.asr_opt.identity import verify_model
from research.asr_opt.review_audit import validate_drafts


class IdentityReviewTests(unittest.TestCase):
    def test_auxiliary_tampering_missing_and_extra_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            files = {}
            for name in ["config.json", "model.bin", "tokenizer.json"]:
                (p / name).write_bytes(name.encode())
                files[name] = {
                    "bytes": len(name),
                    "sha256": hashlib.sha256(name.encode()).hexdigest(),
                }
            with patch("research.asr_opt.identity.IDENTITIES", {"synthetic": {"files": files}}):
                verify_model("synthetic", p)
                (p / "config.json").write_bytes(b"x" * len("config.json"))
                with self.assertRaises(ValueError):
                    verify_model("synthetic", p)
                (p / "config.json").write_bytes(b"config.json")
                (p / "tokenizer.json").unlink()
                with self.assertRaises(ValueError):
                    verify_model("synthetic", p)
                (p / "tokenizer.json").write_bytes(b"tokenizer.json")
                (p / "preprocessor_config.json").write_text("{}")
                with self.assertRaises(ValueError):
                    verify_model("synthetic", p)

    def test_projection_join_checks_text_hash_and_duplicates(self):
        text = "mesa sintética"
        prediction = {
            "audio_id": "x",
            "audio_sha256": "a" * 64,
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "transcription": text,
        }
        projected = {
            "audio_id": "x",
            "source_audio_sha256": "a" * 64,
            "nlp": {
                "text_original": text,
                "item_proposal": None,
                "candidates": [],
                "proposed_item_count": 0,
            },
        }
        self.assertEqual(len(bind_projection({"records": [prediction]}, {"rows": [projected]})), 1)
        for bad in [
            {**prediction, "text_sha256": "0" * 64},
            {**prediction, "audio_sha256": "b" * 64},
            {**prediction, "transcription": "otra mesa"},
        ]:
            with self.assertRaises(ValueError):
                bind_projection({"records": [bad]}, {"rows": [projected]})
        with self.assertRaises(ValueError):
            bind_projection({"records": [prediction, prediction]}, {"rows": [projected]})

    def test_controlled_dimensions_do_not_erase_axis_or_scope(self):
        e = {"value": "0.9", "unit": "m", "axis": "ancho", "scope": "mueble"}
        a = {**e, "value": "90", "unit": "cm"}
        self.assertTrue(dimension_comparisons([e], [a])[0]["equivalent_value_same_axis_scope"])
        for key, value in [("axis", "alto"), ("scope", "cajonera"), ("value", "9")]:
            self.assertFalse(
                dimension_comparisons([e], [{**a, key: value}])[0][
                    "equivalent_value_same_axis_scope"
                ]
            )
        self.assertEqual(
            dimension_comparisons([e], [{**a, "unit": None}])[0]["status"],
            "NO_EVALUABLE_UNIDAD_NO_RESUELTA",
        )
        self.assertEqual(
            dimension_comparisons([e], [a, a])[0]["status"], "NO_EVALUABLE_EJE_DUPLICADO"
        )

    def test_draft_source_binding(self):
        r = {"audio_id": "x", "audio_sha256": "a" * 64, "texto_literal_verificado": "sintético"}
        d = {
            "reference_json_sha256": "r",
            "records": [
                {
                    "audio_id": "x",
                    "source_audio_sha256": "a" * 64,
                    "source_text_sha256": hashlib.sha256("sintético".encode()).hexdigest(),
                    "public_release_authorized": False,
                }
            ],
        }
        original = copy.deepcopy(d)
        validate_drafts(d, [r], "r")
        self.assertEqual(original, d)
        with self.assertRaises(ValueError):
            validate_drafts(d, [r], "otro")
        d["records"][0]["source_text_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            validate_drafts(d, [r], "r")


class AcquisitionFixtureTests(unittest.TestCase):
    def test_wrong_valid_hex_revision_rejected_before_network(self):
        from research.asr_opt.acquire import acquire

        with patch("urllib.request.urlopen") as network:
            with self.assertRaises(ValueError):
                acquire(
                    {"id": "Systran/faster-whisper-medium", "sha": "f" * 40},
                    "medium",
                    Path("/unused"),
                )
        network.assert_not_called()

    def test_f09_historical_and_small_fixture_routes_without_downloads(self):
        import sys
        from types import ModuleType, SimpleNamespace

        fake = ModuleType("huggingface_hub")
        fake.snapshot_download = lambda **kwargs: None
        with patch.dict(sys.modules, {"huggingface_hub": fake}):
            from scripts import preparar_modelo_asr_f09 as helper
        for small in (False, True):
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp)

                def synthetic_download(**kwargs):
                    (p / "model.bin").write_bytes(b"synthetic fixture")

                argv = ["fixture", str(p)] + (["--small-research"] if small else [])
                with (
                    patch("sys.argv", argv),
                    patch.object(
                        helper, "snapshot_download", side_effect=synthetic_download
                    ) as download,
                    patch.object(
                        helper,
                        "sha256",
                        return_value=SimpleNamespace(
                            hexdigest=lambda: (
                                "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671"
                            )
                        ),
                    ),
                ):
                    helper.ejecutar()
                args = download.call_args.kwargs
                self.assertEqual(
                    args["repo_id"], "Systran/faster-whisper-" + ("small" if small else "base")
                )
                if small:
                    self.assertEqual(args["revision"], "536b0662742c02347bc0e980a01041f333bce120")
                else:
                    self.assertNotIn("revision", args)

    def test_small_fixture_wrong_hash_rejected_without_downloads(self):
        import sys
        from types import ModuleType

        fake = ModuleType("huggingface_hub")
        fake.snapshot_download = lambda **kwargs: None
        with patch.dict(sys.modules, {"huggingface_hub": fake}):
            from scripts import preparar_modelo_asr_f09 as helper
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "model.bin").write_bytes(b"wrong")
            with (
                patch("sys.argv", ["fixture", str(p), "--small-research"]),
                patch.object(helper, "snapshot_download"),
            ):
                with self.assertRaises(SystemExit):
                    helper.ejecutar()
