import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.asr_opt.audio import PRESETS, derive


class AudioTests(unittest.TestCase):
    def test_presets_change_single_factor(self):
        a = PRESETS["webm-opus-64k"][1]
        b = PRESETS["webm-opus-128k"][1]
        self.assertEqual(sum(x != y for x, y in zip(a, b)), 1)
        self.assertEqual(a, PRESETS["ogg-opus-64k"][1])
        self.assertTrue(all("silenceremove" not in str(p) for p in PRESETS.values()))

    def test_unknown_preset_does_not_execute(self):
        with tempfile.TemporaryDirectory() as temp, patch("subprocess.run") as process:
            with self.assertRaises(ValueError):
                derive({}, "invented", Path(temp))
            process.assert_not_called()
