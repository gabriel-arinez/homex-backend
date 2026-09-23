import ast
import inspect
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import homex_nlp
import pytest
from pydantic import ValidationError

from apps.capturas.nlp import (
    AdaptadorNLP,
    ContratoNLPNoSoportado,
    ModoNLPNoSoportado,
    PaqueteNLPNoSoportado,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "nlp" / "medidas-componentes-v1.json"


@pytest.fixture(autouse=True)
def catalogo_estructural():
    yield


@pytest.fixture(autouse=True)
def transiciones_pedido():
    yield


def test_importacion_no_inicializa_django_ni_escribe_archivos(tmp_path):
    script = "import sys; import apps.capturas.nlp; print('django' in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[2])},
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "False"
    assert list(tmp_path.iterdir()) == []


def test_version_fijada_y_rules_only_funcionan():
    assert homex_nlp.__version__ == "0.1.0"
    resultado = AdaptadorNLP().extraer(
        solicitud_id="backend-f080-001",
        texto="tres escritorios, total 100",
        moneda="BOB",
    )
    assert resultado.version_contrato == "1.0"
    assert resultado.motor["mode"] == "RULES_ONLY"
    assert resultado.propuesta is not None
    assert resultado.propuesta.cantidad == 3
    assert resultado.propuesta.precio["mode"] == "TOTAL_NEGOCIADO"
    assert resultado.propuesta.precio["line_total"] == "100.00"


def test_version_de_paquete_desconocida_falla(monkeypatch):
    monkeypatch.setattr(homex_nlp, "__version__", "9.0.0")
    with pytest.raises(PaqueteNLPNoSoportado, match="9.0.0"):
        AdaptadorNLP()


def test_version_de_schema_desconocida_falla_antes_de_deserializar():
    payload = json.loads(FIXTURE.read_text())
    payload["schema_version"] = "2.0"
    with pytest.raises(ContratoNLPNoSoportado, match="2.0"):
        AdaptadorNLP().transformar(payload)


def test_campos_adicionales_son_rechazados():
    payload = json.loads(FIXTURE.read_text())
    payload["campo_futuro"] = True
    with pytest.raises(ValidationError, match="campo_futuro"):
        AdaptadorNLP().transformar(payload)


def test_fixture_v1_se_mapea_sin_perder_evidencia():
    payload = json.loads(FIXTURE.read_text())
    resultado = AdaptadorNLP().transformar(payload)
    assert resultado.propuesta is not None
    assert resultado.propuesta.nombre == "escritorio"
    assert resultado.propuesta.tipo_mueble_candidato == "ESCRITORIO"
    assert len(resultado.propuesta.espesores) == 2
    assert resultado.resultado_original == payload
    assert list(resultado.candidatos) == payload["candidates"]
    assert resultado.resultado_original["text_original"] == resultado.texto_original


def test_roundtrip_estricto_y_payload_original_aislado():
    payload = json.loads(FIXTURE.read_text())
    resultado = AdaptadorNLP().transformar(payload)
    copia = deepcopy(resultado.resultado_original)
    payload["candidates"][0]["text"] = "manipulado"
    assert resultado.resultado_original == copia


def test_backend_no_exige_ner_experimental():
    payload = json.loads(FIXTURE.read_text())
    payload_hibrido = deepcopy(payload)
    payload_hibrido["engine"] = {
        "mode": "HYBRID",
        "model_version": "experimental",
        "rules_version": "1.0",
        "normalization_version": "1.0",
    }
    with pytest.raises(ModoNLPNoSoportado, match="HYBRID"):
        AdaptadorNLP().transformar(payload_hibrido)
    assert AdaptadorNLP().transformar(payload).motor["model_version"] is None


def test_transformar_no_permite_desactivar_rules_only():
    parametros = inspect.signature(AdaptadorNLP.transformar).parameters
    assert "exigir_rules_only" not in parametros


def test_adapter_no_depende_de_internals_de_homex_nlp():
    adapter = Path(__file__).parents[2] / "apps" / "capturas" / "nlp" / "adapter.py"

    arbol = ast.parse(adapter.read_text())
    imports_homex_nlp = set()

    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                if alias.name.startswith("homex_nlp"):
                    imports_homex_nlp.add(alias.name)

        if isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.module.startswith("homex_nlp"):
            imports_homex_nlp.add(nodo.module)

    permitidos = {
        "homex_nlp",
        "homex_nlp.contracts",
        "homex_nlp.engine",
    }

    assert imports_homex_nlp <= permitidos
