"""Gate PRF-04 del stack de pruebas: evidencia, vínculo único, métricas y audio efímero."""

import argparse
import json
import os
import re
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
if os.environ.get("DJANGO_SETTINGS_MODULE") != "config.settings.integration":
    raise RuntimeError("Este verificador sólo admite config.settings.integration.")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.db import connection  # noqa: E402

from apps.capturas.models import Captura, RevisionAsistida  # noqa: E402


def verify(output, synthetic_reference):
    capture = Captura.objects.filter(modo_captura="ASISTIDA_CREACION_MUEBLE").latest("id")
    attempt = capture.intentocaptura_set.latest("numero_intento")
    assert capture.estado == "COMPLETADA" and attempt.estado == "FINALIZADO"
    assert capture.proforma_id and capture.proforma_detalle_id
    assert capture.proforma_detalle.proforma_id == capture.proforma_id
    review = RevisionAsistida.objects.get(
        captura=capture, intento=attempt, detalle_id=capture.proforma_detalle_id
    )
    assert attempt.proyeccion_configurador and review.resultado_humano
    assert not list(settings.HOMEX_AUDIO_TEMP_ROOT.glob("*")), "Quedan temporales de audio."
    ref = re.findall(r"\w+", synthetic_reference.lower())
    hyp = re.findall(r"\w+", capture.texto_transcrito.lower())
    distance = list(range(len(hyp) + 1))
    for n, a in enumerate(ref, 1):
        row = [n]
        for m, b in enumerate(hyp, 1):
            row.append(min(row[-1] + 1, distance[m] + 1, distance[m - 1] + (a != b)))
        distance = row
    report = {
        "entorno": "INTEGRACION_AISLADA",
        "backend_revision_ejecutada": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True
        ).strip(),
        "postgresql": connection.pg_version,
        "wheel_sha256": sha256(
            (PROJECT / "vendor/homex_nlp-0.1.12-py3-none-any.whl").read_bytes()
        ).hexdigest(),
        "motor": attempt.resultado_raw["engine"],
        "modelo_asr": attempt.modelo_asr_version,
        "audio": "TTS_SINTETICO_NO_VOZ_DE_VENDEDORES",
        "audio_temporal_restante": 0,
        "latencia_asr_ms": attempt.latencia_asr_ms,
        "latencia_nlp_ms": attempt.latencia_nlp_ms,
        "latencia_total_ms": attempt.latencia_total_ms,
        "wer_sintetico": {
            "distancia": distance[-1],
            "palabras_referencia": len(ref),
            "wer": distance[-1] / len(ref),
            "normalizacion": "minusculas y tokens Unicode; sin normalizar números",
        },
        "wer_vendedores": None,
        "comparacion_semantica": review.comparacion,
        "vinculo_y_snapshot_verificados": True,
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--synthetic-reference", required=True)
    args = parser.parse_args()
    verify(args.output, args.synthetic_reference)
