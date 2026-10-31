"""Inferencias locales supervisadas. Ninguna importación carga modelos automáticamente."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path

MODEL_WEIGHTS = {
    "small": "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671",
    "medium": "9b45e1009dcc4ab601eff815b61d80e60ce3fd8c74c1a14f4a282258286b51ae",
    "large-v3-turbo": "e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da",
}
ALLOWED = set(MODEL_WEIGHTS)
RESERVE_KIB = 786432  # Reserva pre-registrada: 768 MiB para el equipo y servicios ajenos.
MAX_SWAP_GROWTH_KIB = 131072


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def memory() -> dict:
    return {
        line.split(":")[0]: int(line.split()[1])
        for line in Path("/proc/meminfo").read_text().splitlines()
        if ":" in line
    }


def process_memory(pid: int) -> dict:
    try:
        return {
            line.split(":")[0]: int(line.split()[1])
            for line in Path(f"/proc/{pid}/status").read_text().splitlines()
            if line.startswith(("VmRSS:", "VmSwap:", "VmHWM:"))
        }
    except FileNotFoundError:
        return {}


def check_input(entry: dict) -> Path:
    path = Path(entry["path"])
    if not path.is_file() or path.is_symlink() or sha256(path) != entry["audio_sha256"]:
        raise ValueError("Audio ausente, symlink o hash distinto")
    return path


def run(request_path: Path, output: Path) -> None:
    request = json.loads(request_path.read_text())
    if request["model_id"] not in ALLOWED:
        raise ValueError("Modelo no autorizado")
    if request["model_sha256"] != MODEL_WEIGHTS[request["model_id"]]:
        raise ValueError("Pesos no pertenecen a los tres candidatos auditados")
    model_path = Path(request["model_path"])
    if not model_path.is_dir() or sha256(model_path / "model.bin") != request["model_sha256"]:
        raise ValueError("Modelo local no corresponde al hash fijado")
    if output.exists():
        raise FileExistsError("No sobrescribir resultados anteriores")
    os.umask(0o077)
    os.nice(10)
    from importlib.metadata import version

    from faster_whisper import WhisperModel

    for package, expected in {
        "faster-whisper": "1.2.1",
        "ctranslate2": "4.8.2",
        "homex-nlp": "0.1.18",
    }.items():
        if version(package) != expected:
            raise ValueError("Runtime no corresponde a las versiones auditadas")
    started = time.perf_counter()
    report = {
        "status": "RUNNING",
        "request": request,
        "python": platform.python_version(),
        "versions": {p: version(p) for p in ("faster-whisper", "ctranslate2", "homex-nlp")},
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "git_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True)),
        "mem_before": memory(),
        "load_average": os.getloadavg(),
        "transcribe_defaults": {
            k: p.default
            for k, p in inspect.signature(WhisperModel.transcribe).parameters.items()
            if p.default is not inspect.Parameter.empty
        },
        "call": "model.transcribe(path, language='es')",
        "cpu_threads": 0,
        "cpu_count": os.cpu_count(),
        "env_threads": {
            k: os.getenv(k) for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
        },
        "records": [],
    }

    def save():
        report["maxrss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        report["current_memory"] = process_memory(os.getpid())
        report["wall_s"] = time.perf_counter() - started
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    save()
    t = time.perf_counter()
    # Local path plus explicit offline mode: never resolve a model alias during inference.
    model = WhisperModel(str(model_path), device="cpu", compute_type="int8", local_files_only=True)
    report["model_load_s"] = time.perf_counter() - t
    report["effective_compute_type"] = model.model.compute_type
    report["effective_device"] = model.model.device
    save()
    for index, entry in enumerate(request["records"]):
        path = check_input(entry)
        t, cpu = time.perf_counter(), time.process_time()
        segments, info = model.transcribe(str(path), language="es")
        rows = [
            {
                "start": s.start,
                "end": s.end,
                "text": s.text,
                "avg_logprob": s.avg_logprob,
                "no_speech_prob": s.no_speech_prob,
            }
            for s in segments
        ]
        elapsed = time.perf_counter() - t
        text = " ".join(s["text"].strip() for s in rows if s["text"].strip())
        report["records"].append(
            {
                "audio_id": entry["audio_id"],
                "source_audio_sha256": entry.get("source_audio_sha256", entry["audio_sha256"]),
                "audio_sha256": entry["audio_sha256"],
                "duration_s": entry["duration_s"],
                "inference_s": elapsed,
                "cpu_s": time.process_time() - cpu,
                "rtf": elapsed / entry["duration_s"],
                "transcription": text,
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "segments": rows,
                "segment_overruns": [s for s in rows if s["end"] > entry["duration_s"]],
                "first_inference_after_load": index == 0,
                "memory": process_memory(os.getpid()),
                "mem_available_kib": memory()["MemAvailable"],
                "detected_language": info.language,
            }
        )
        save()
    report["status"] = "PASS"
    save()


def supervise(request: Path, output: Path, timeout: float = 900) -> dict:
    """Solo termina el PID hijo propio; conserva muestras/resultado parcial al abortar."""
    if output.exists() or output.with_suffix(".monitor.json").exists():
        raise FileExistsError("Resultado previo: use otra ruta")
    before = memory()
    rss_limit = min(3 * 1024 * 1024, before["MemAvailable"] - RESERVE_KIB)
    log = {
        "preflight": before,
        "rss_limit_kib": rss_limit,
        "reserve_kib": RESERVE_KIB,
        "swap_growth_limit_kib": MAX_SWAP_GROWTH_KIB,
        "timeout_s": timeout,
        "samples": [],
        "status": "STARTING",
    }
    if rss_limit < 900 * 1024:
        log["status"] = "NO_VIABLE_RECURSOS_PREFLIGHT"
    else:
        started = time.monotonic()
        with output.with_suffix(".log").open("x") as stream:
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "research.asr_opt.runner",
                    "--child",
                    str(request),
                    str(output),
                ],
                stdout=stream,
                stderr=stream,
                env={**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"},
            )
            while child.poll() is None:
                current, proc = memory(), process_memory(child.pid)
                log["samples"].append(
                    {
                        "elapsed_s": time.monotonic() - started,
                        "mem_available_kib": current["MemAvailable"],
                        **proc,
                    }
                )
                reason = None
                if current["MemAvailable"] < RESERVE_KIB or proc.get("VmRSS", 0) > rss_limit:
                    reason = "NO_VIABLE_RECURSOS_MEMORIA"
                if proc.get("VmSwap", 0) > MAX_SWAP_GROWTH_KIB:
                    reason = "NO_VIABLE_RECURSOS_SWAP"
                if time.monotonic() - started > timeout:
                    reason = "NO_VIABLE_TIEMPO"
                if reason:
                    child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
                    log["status"] = reason
                    break
                time.sleep(0.25)
            log["exit_code"] = child.wait()
            if log["status"] == "STARTING":
                log["status"] = "PASS" if child.returncode == 0 else "FAILED"
    log["postflight"] = memory()
    output.with_suffix(".monitor.json").write_text(json.dumps(log, indent=2))
    return log


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("request", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--timeout", type=float, default=900)
    args = parser.parse_args()
    if args.child:
        run(args.request, args.output)
    else:
        print(
            json.dumps(
                {
                    k: v
                    for k, v in supervise(args.request, args.output, args.timeout).items()
                    if k != "samples"
                }
            )
        )
