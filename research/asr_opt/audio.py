"""Derivados offline pareados: una variable por preset; nunca modifica el WAV fuente."""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

from research.asr_opt.runner import check_input, sha256

PRESETS = {
    "webm-opus-64k": (".webm", ["-c:a", "libopus", "-b:a", "64k", "-ar", "48000"]),
    "webm-opus-128k": (".webm", ["-c:a", "libopus", "-b:a", "128k", "-ar", "48000"]),
    "ogg-opus-64k": (".ogg", ["-c:a", "libopus", "-b:a", "64k", "-ar", "48000"]),
    "gain-minus6db": (".wav", ["-af", "volume=-6dB", "-c:a", "pcm_s16le"]),
    "highpass-80hz": (".wav", ["-af", "highpass=f=80", "-c:a", "pcm_s16le"]),
    "denoise-fixed": (".wav", ["-af", "afftdn=nf=-25", "-c:a", "pcm_s16le"]),
    "resample-48khz": (".wav", ["-ar", "48000", "-c:a", "pcm_s16le"]),
}


def signal_properties(path: Path) -> dict:
    from faster_whisper.audio import decode_audio

    samples = decode_audio(str(path), sampling_rate=16000)
    if not len(samples):
        raise ValueError("Audio sin muestras decodificables")
    import numpy as np

    rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
    peak = float(np.max(np.abs(samples)))
    return {
        "decoded_frames_16khz": len(samples),
        "duration_s": len(samples) / 16000,
        "rms_dbfs": 20 * math.log10(rms) if rms else None,
        "peak_dbfs": 20 * math.log10(peak) if peak else None,
        "clipping_fraction": float(np.mean(np.abs(samples) >= 32767 / 32768)),
        "near_silence_fraction_below_minus60db": float(np.mean(np.abs(samples) < 0.001)),
        "dc_offset": float(np.mean(samples)),
        "bytes": path.stat().st_size,
    }


def derive(entry: dict, preset: str, directory: Path, ffmpeg="ffmpeg") -> dict:
    if preset not in PRESETS:
        raise ValueError("Preset no autorizado")
    source = check_input(entry)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    suffix, options = PRESETS[preset]
    output = directory / (entry["audio_id"] + suffix)
    if output.exists() or output.resolve() == source.resolve():
        raise FileExistsError("No sobrescribir originales ni derivados")
    command = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-n",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-ac",
        "1",
        "-threads",
        "1",
        *options,
        str(output),
    ]
    subprocess.run(command, check=True, capture_output=True, timeout=90)
    output.chmod(0o600)
    props = signal_properties(output)
    if abs(props["duration_s"] - entry["duration_s"]) > 0.1:
        raise ValueError("Cambio inesperado de duración; preservar incidente")
    return {
        "audio_id": entry["audio_id"],
        "audio_sha256": sha256(output),
        "source_audio_sha256": entry["audio_sha256"],
        "path": str(output.resolve()),
        "duration_s": props["duration_s"],
        "preset": preset,
        "ffmpeg_command": command,
        "source_class": "FFMPEG_DERIVED_NOT_MICROPHONE",
        "signal": props,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    corpus = json.loads(args.corpus.read_text())["records"]
    args.destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    result = {
        "original": [{**r, "signal": signal_properties(Path(r["path"]))} for r in corpus],
        "ffmpeg_version": subprocess.check_output(["ffmpeg", "-version"], text=True),
        "derivatives": {},
    }
    for preset in PRESETS:
        selected = (
            corpus
            if preset == "webm-opus-64k"
            else [r for r in corpus if r["audio_id"] in {"01", "03", "20"}]
        )
        result["derivatives"][preset] = [
            derive(r, preset, args.destination / preset) for r in selected
        ]
    (args.destination / "derivatives.json").write_text(json.dumps(result, indent=2))
