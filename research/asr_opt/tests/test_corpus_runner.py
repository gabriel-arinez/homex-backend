import csv
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from research.asr_opt.corpus import prepare_review, validate_manifest
from research.asr_opt.runner import check_input, sha256, supervise


class CorpusRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "audios").mkdir()
        rows = []
        for i in range(1, 21):
            audio = self.root / "audios" / f"{i:02}.wav"
            with wave.open(str(audio), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(16000)
                stream.writeframes(b"\x00\x00" * 160)
            rows.append(
                {
                    "guion": f"{i:02}",
                    "archivo": f"audios/{i:02}.wav",
                    "sha256": sha256(audio),
                    "bytes": audio.stat().st_size,
                }
            )
        self.manifest = self.root / "manifest.csv"
        with self.manifest.open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def test_manifest_and_private_review_never_gold(self):
        records = validate_manifest(self.manifest)
        prepare_review(records, self.root / "review")
        refs = json.loads((self.root / "review/references-pending.json").read_text())
        self.assertEqual(len(refs), 20)
        self.assertTrue(all(r["verificacion_por_escucha"] is False for r in refs))
        self.assertNotIn("REFERENCE_DATA", (self.root / "review/revisar.html").read_text())
        self.assertEqual(sha256(self.root / "review/audios/01.wav"), records[0]["audio_sha256"])
        with self.assertRaises(FileExistsError):
            prepare_review(records, self.root / "review")

    def test_corruption_symlink_and_wrong_ids_rejected(self):
        audio = self.root / "audios/01.wav"
        audio.write_bytes(b"corrupto")
        with self.assertRaises(ValueError):
            validate_manifest(self.manifest)
        audio.unlink()
        audio.symlink_to(self.root / "audios/02.wav")
        with self.assertRaises(ValueError):
            validate_manifest(self.manifest)
        text = self.manifest.read_text().replace("02,audios", "01,audios")
        self.manifest.write_text(text)
        with self.assertRaises(ValueError):
            validate_manifest(self.manifest)

    def test_preflight_never_launches_under_pressure(self):
        output = self.root / "result.json"
        with (
            patch("research.asr_opt.runner.memory", return_value={"MemAvailable": 800000}),
            patch("research.asr_opt.runner.subprocess.Popen") as popen,
        ):
            result = supervise(self.root / "request.json", output)
        popen.assert_not_called()
        self.assertEqual(result["status"], "NO_VIABLE_RECURSOS_PREFLIGHT")
        self.assertTrue(output.with_suffix(".monitor.json").exists())

    def test_input_hash_required(self):
        entry = validate_manifest(self.manifest)[0]
        self.assertEqual(check_input(entry), Path(entry["path"]))
        entry["audio_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            check_input(entry)
