"""Valida originales y prepara un paquete de revisión privado, sin inferir gold."""

from __future__ import annotations

import csv
import json
import shutil
import wave
from pathlib import Path

from research.asr_opt.runner import sha256


def validate_manifest(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if [r["guion"] for r in rows] != [f"{i:02}" for i in range(1, 21)]:
        raise ValueError("Se requieren 20 IDs únicos y ordenados")
    records = []
    for row in rows:
        audio = path.parent / row["archivo"]
        if (
            audio.is_symlink()
            or not audio.resolve().is_relative_to(path.parent.resolve())
            or row["archivo"] != f"audios/{row['guion']}.wav"
            or sha256(audio) != row["sha256"]
            or audio.stat().st_size != int(row["bytes"])
        ):
            raise ValueError("Audio fuera de corpus, alterado o no corresponde al ID")
        with wave.open(str(audio)) as wav:
            if (wav.getnchannels(), wav.getframerate(), wav.getsampwidth(), wav.getcomptype()) != (
                1,
                16000,
                2,
                "NONE",
            ):
                raise ValueError("Se requiere PCM16 mono 16 kHz")
            duration = wav.getnframes() / wav.getframerate()
        records.append(
            {
                "audio_id": row["guion"],
                "audio_sha256": row["sha256"],
                "path": str(audio.resolve()),
                "duration_s": duration,
            }
        )
    return records


def prepare_review(records: list[dict], destination: Path) -> None:
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    (destination / "audios").mkdir(mode=0o700)
    refs = []
    for r in records:
        source = Path(r["path"])
        if sha256(source) != r["audio_sha256"]:
            raise ValueError("Original alterado")
        target = destination / "audios" / f"{r['audio_id']}.wav"
        shutil.copyfile(source, target)
        target.chmod(0o600)
        refs.append(
            {
                "audio_id": r["audio_id"],
                "audio_sha256": r["audio_sha256"],
                "verificacion_por_escucha": False,
                "texto_literal_verificado": None,
                "campos_comerciales_gold": {},
                "notas_acusticas": {"uncertain_spans": []},
            }
        )
    html = Path(__file__).with_name("review.html").read_text()
    html = html.replace(
        "const records = []; // REFERENCE_DATA",
        "const records = " + json.dumps(refs).replace("</", "<\\/") + ";",
    )
    (destination / "revisar.html").write_text(html)
    (destination / "references-pending.json").write_text(json.dumps(refs, indent=2))
