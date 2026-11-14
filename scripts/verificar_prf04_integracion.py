"""Gate PRF-04 del stack de pruebas: evidencia, vínculo único, métricas y audio efímero."""

import argparse
import json
import os
import re
import subprocess
import sys
from hashlib import sha256
from importlib.metadata import distribution
from pathlib import Path
from zipfile import ZipFile

import homex_nlp

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
if os.environ.get("DJANGO_SETTINGS_MODULE") != "config.settings.integration":
    raise RuntimeError("Este verificador sólo admite config.settings.integration.")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.db import connection  # noqa: E402

from apps.capturas.models import Captura, RevisionAsistida  # noqa: E402

WHEEL = PROJECT / "vendor/homex_nlp-0.1.24-py3-none-any.whl"
WHEEL_SHA256 = "12d1dab78a5e1ea04780e0e3345e1885cc5dc9edf5c7b2aa1b989f8349379ec6"


def verify_nlp_artifact():
    """Bind reported identity to ordinary installed files, not just a wheel filename."""
    installed = distribution("homex-nlp")
    assert installed.version == homex_nlp.__version__ == "0.1.24", "NLP version mismatch."
    assert sha256(WHEEL.read_bytes()).hexdigest() == WHEEL_SHA256, "NLP wheel hash mismatch."
    files = {str(file) for file in installed.files or ()}
    assert files, "Installed NLP distribution has no file manifest."
    direct_url = installed.read_text("direct_url.json")
    assert not direct_url or not json.loads(direct_url).get("dir_info", {}).get("editable"), (
        "Editable NLP installs are not valid integration artifacts."
    )
    expected_origin = Path(installed.locate_file("homex_nlp/__init__.py")).resolve()
    assert Path(homex_nlp.__file__).resolve() == expected_origin, "NLP source override."
    with ZipFile(WHEEL) as wheel:
        packaged = {
            name
            for name in wheel.namelist()
            if not name.endswith("/") and not name.endswith(".dist-info/RECORD")
        }
        assert packaged <= files, "Installed NLP manifest omits packaged files."
        for name in sorted(packaged):
            path = Path(installed.locate_file(name))
            assert path.is_file() and path.read_bytes() == wheel.read(name), (
                f"Installed NLP file differs from reviewed wheel: {name}"
            )
    package_root = expected_origin.parent
    expected_package = {name for name in packaged if name.startswith("homex_nlp/")}
    actual_package = {
        "homex_nlp/" + path.relative_to(package_root).as_posix()
        for path in package_root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    assert actual_package == expected_package, "Unexpected installed NLP package files."
    for name, module in tuple(sys.modules.items()):
        if name.startswith("homex_nlp.") and getattr(module, "__file__", None):
            relative = "homex_nlp/" + name.removeprefix("homex_nlp.").replace(".", "/")
            origin = Path(module.__file__).resolve()
            allowed = {
                Path(installed.locate_file(relative + ".py")).resolve(),
                Path(installed.locate_file(relative + "/__init__.py")).resolve(),
            }
            assert origin in allowed, f"NLP submodule source override: {name}"
    return {
        "distribution_version": installed.version,
        "module_version": homex_nlp.__version__,
        "module_origin": str(expected_origin),
        "wheel_filename": WHEEL.name,
        "verified_files": len(packaged),
    }


def verify(output, synthetic_reference):
    artifact = verify_nlp_artifact()
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
        "wheel_sha256": WHEEL_SHA256,
        "nlp_artifact": artifact,
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
