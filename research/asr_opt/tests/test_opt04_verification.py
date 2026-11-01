import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from research.asr_opt.verify_opt04 import verify


class Opt04VerificationTests(unittest.TestCase):
    def test_manifest_reads_only_detects_corruption_and_forbidden_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pair = {
                "same_catalog": True,
                "same_60_transcriptions": True,
                "official_denominator": 0,
                "independent_acoustic_audited": 0,
                "rows": [{"classification": "CORRECCION_DE_BUG"}] * 2
                + [{"classification": "SIN_CAMBIO"}] * 58,
            }
            (root / "04_COMPARACION_COMERCIAL_ANTES_DESPUES.json").write_text(json.dumps(pair))
            experiments = {
                "in_sample": True,
                "official_denominator": 0,
                "experiments": [
                    {"model": model, "status": "REJECT_RISK_WER_NO_CRITICAL_BENEFIT"}
                    for model in ["small", "medium", "large-v3-turbo"]
                    for _ in range(4)
                ],
            }
            (root / "06_RESULTADOS_ASR_OPT_04.json").write_text(json.dumps(experiments))
            (root / "external_inputs_sha256.json").write_text('{"files":{}}')
            manifest = {
                "files": {
                    p.name: {
                        "bytes": p.stat().st_size,
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    }
                    for p in root.iterdir()
                },
                "model_identities": {},
                "profiles": {},
                "inference_reports": [],
            }
            (root / "manifest_sha256.json").write_text(json.dumps(manifest))
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(verify(root), [])
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})
            (root / "external_inputs_sha256.json").write_text('{"files":{},"tampered":true}')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertIn("external_inputs_sha256.json", verify(root))
            manifest["files"]["../outside"] = {"bytes": 0, "sha256": "0" * 64}
            (root / "manifest_sha256.json").write_text(json.dumps(manifest))
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
                verify(root)
