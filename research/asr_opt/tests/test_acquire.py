import unittest
from pathlib import Path

from research.asr_opt.acquire import REPOS
from research.asr_opt.runner import MODEL_WEIGHTS, run


class AcquisitionTests(unittest.TestCase):
    def test_only_authorized_models_and_exact_weights(self):
        self.assertEqual(set(REPOS), {"medium", "large-v3-turbo"})
        self.assertEqual(set(MODEL_WEIGHTS), {"small", "medium", "large-v3-turbo"})
        self.assertTrue(all(len(v) == 64 for v in MODEL_WEIGHTS.values()))

    def test_runner_rejects_other_models_before_import(self):
        import tempfile
        import json
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as temp:
            req = Path(temp) / "request.json"
            req.write_text(json.dumps({"model_id": "base"}))
            with self.assertRaises(ValueError), patch("builtins.__import__") as importing:
                run(req, Path(temp) / "output.json")
            importing.assert_not_called()
