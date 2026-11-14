"""PRF-04 must identify the installed artifact before emitting metrics."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture(autouse=True)
def catalogo_estructural():
    yield


@pytest.fixture(autouse=True)
def transiciones_pedido():
    yield


@pytest.fixture
def verifier(monkeypatch, tmp_path):
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.integration")
    script = Path(__file__).parents[2] / "scripts/verificar_prf04_integracion.py"
    spec = importlib.util.spec_from_file_location("prf04_identity_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "settings", SimpleNamespace(HOMEX_AUDIO_TEMP_ROOT=tmp_path))
    attempt = SimpleNamespace(
        estado="FINALIZADO",
        proyeccion_configurador={"ok": True},
        resultado_raw={"engine": {"mode": "RULES_ONLY"}},
        modelo_asr_version="test",
        latencia_asr_ms=1,
        latencia_nlp_ms=2,
        latencia_total_ms=3,
    )
    capture = SimpleNamespace(
        estado="COMPLETADA",
        proforma_id=1,
        proforma_detalle_id=2,
        proforma_detalle=SimpleNamespace(proforma_id=1),
        texto_transcrito="test",
        intentocaptura_set=Mock(),
    )
    capture.intentocaptura_set.latest.return_value = attempt
    captures = Mock()
    captures.objects.filter.return_value.latest.return_value = capture
    reviews = Mock()
    reviews.objects.get.return_value = SimpleNamespace(
        resultado_humano={"ok": True}, comparacion={}
    )
    monkeypatch.setattr(module, "Captura", captures)
    monkeypatch.setattr(module, "RevisionAsistida", reviews)
    monkeypatch.setattr(module, "connection", SimpleNamespace(pg_version=160000))
    monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **kw: "test-revision")
    return module


def test_report_identifies_the_actual_installed_wheel(verifier, tmp_path):
    output = tmp_path / "report.json"
    verifier.verify(output, "test")
    report = json.loads(output.read_text())
    assert (
        report["wheel_sha256"] == "12d1dab78a5e1ea04780e0e3345e1885cc5dc9edf5c7b2aa1b989f8349379ec6"
    )
    assert report["nlp_artifact"]["distribution_version"] == "0.1.24"
    assert report["nlp_artifact"]["module_version"] == "0.1.24"
    assert report["nlp_artifact"]["verified_files"] > 10
    assert report["nlp_artifact"]["module_origin"].endswith("homex_nlp/__init__.py")


@pytest.mark.parametrize(
    "failure",
    [
        "metadata",
        "module_version",
        "source_override",
        "wheel",
        "installed_file",
        "extra_file",
        "editable",
    ],
)
def test_invalid_identity_never_writes_metrics(verifier, monkeypatch, tmp_path, failure):
    if failure == "metadata":
        installed = verifier.distribution("homex-nlp")
        monkeypatch.setattr(
            verifier,
            "distribution",
            lambda name: SimpleNamespace(
                version="0.1.21",
                files=installed.files,
                read_text=installed.read_text,
                locate_file=installed.locate_file,
            ),
        )
    elif failure == "editable":
        installed = verifier.distribution("homex-nlp")
        monkeypatch.setattr(
            verifier,
            "distribution",
            lambda name: SimpleNamespace(
                version=installed.version,
                files=installed.files,
                locate_file=installed.locate_file,
                read_text=lambda name: '{"dir_info": {"editable": true}}',
            ),
        )
    elif failure == "module_version":
        monkeypatch.setattr(verifier.homex_nlp, "__version__", "0.1.21")
    elif failure == "source_override":
        monkeypatch.setattr(verifier.homex_nlp, "__file__", str(tmp_path / "homex_nlp/__init__.py"))
    elif failure == "wheel":
        wheel = tmp_path / verifier.WHEEL.name
        wheel.write_bytes(b"not the reviewed artifact")
        monkeypatch.setattr(verifier, "WHEEL", wheel)
    else:
        installed = verifier.distribution("homex-nlp")
        altered = tmp_path / "installed"
        from shutil import copytree

        copytree(installed.locate_file("homex_nlp"), altered / "homex_nlp")
        if failure == "installed_file":
            (altered / "homex_nlp/__init__.py").write_text("# tampered\n")
        else:
            (altered / "homex_nlp/override.py").write_text("# unexpected source\n")
        monkeypatch.setattr(verifier.homex_nlp, "__file__", str(altered / "homex_nlp/__init__.py"))
        monkeypatch.setattr(
            verifier,
            "distribution",
            lambda name: SimpleNamespace(
                version=installed.version,
                files=installed.files,
                read_text=installed.read_text,
                locate_file=lambda path: (
                    altered / str(path)
                    if str(path).startswith("homex_nlp/")
                    else installed.locate_file(path)
                ),
            ),
        )
    output = tmp_path / "report.json"
    with pytest.raises(AssertionError):
        verifier.verify(output, "test")
    assert not output.exists()
    verifier.Captura.objects.filter.assert_not_called()
