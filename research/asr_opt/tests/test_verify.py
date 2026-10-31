import csv
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from research.asr_opt.corpus import validate_manifest
from research.asr_opt.runner import sha256
from research.asr_opt.verify import verify


class VerifyTests(unittest.TestCase):
    def test_read_only_integrity_and_pending_are_distinct(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "audios").mkdir()
            rows = []
            for i in range(1, 21):
                audio = root / "audios" / f"{i:02}.wav"
                with wave.open(str(audio), "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(16000)
                    wav.writeframes(b"\0\0" * 160)
                rows.append(
                    {
                        "guion": f"{i:02}",
                        "archivo": f"audios/{i:02}.wav",
                        "sha256": sha256(audio),
                        "bytes": audio.stat().st_size,
                    }
                )
            with (root / "manifest.csv").open("w") as out:
                writer = csv.DictWriter(out, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            (root / "privado/revision").mkdir(parents=True)
            records = validate_manifest(root / "manifest.csv")
            (root / "privado/corpus.json").write_text(json.dumps({"records": records}))
            (root / "privado/revision/references-pending.json").write_text(
                json.dumps([{**r, "verificacion_por_escucha": False} for r in records])
            )
            info = {
                "bytes": (root / "manifest.csv").stat().st_size,
                "sha256": sha256(root / "manifest.csv"),
            }
            (root / "manifest_sha256.json").write_text(
                json.dumps({"files": {"manifest.csv": info}, "external_inputs": {}})
            )
            before = {str(p): sha256(p) for p in root.rglob("*") if p.is_file()}
            with patch("socket.create_connection", side_effect=AssertionError("red prohibida")):
                result = verify(root)
            self.assertTrue(any(r["status"] == "PENDIENTE" for r in result))
            self.assertFalse(any(r["status"] == "FALLÓ" for r in result))
            self.assertEqual(before, {str(p): sha256(p) for p in root.rglob("*") if p.is_file()})
            (root / "manifest.csv").write_text("alterado")
            self.assertEqual(verify(root)[0]["status"], "FALLÓ")
