"""ASR transcript limits close clearly without invoking NLP or truncating evidence."""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.capturas.audio import ruta_audio
from apps.capturas.models import ItemIA
from apps.capturas.nlp.adapter import AdaptadorNLP
from apps.capturas.pipeline import procesar_intento
from apps.capturas.services import recibir_captura_audio
from apps.proformas.services import crear_proforma
from tests.factories import cliente_persona, vendedor


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("length", [20000, 20001])
def test_asr_boundary_preserves_full_evidence_and_reports_clear_failure(
    django_user_model, tmp_path, length
):
    actor = vendedor(django_user_model.objects.create_user(username="asr-boundary"))
    quote = crear_proforma(actor=actor, cliente=cliente_persona(actor))
    text = ("Un escritorio. " + " " * length)[:length]
    asr = Mock()
    asr.transcribe.return_value = SimpleNamespace(
        text_original=text, latency_ms=7, model_version="controlled-asr"
    )
    adapter = Mock(wraps=AdaptadorNLP())
    with override_settings(HOMEX_AUDIO_TEMP_ROOT=tmp_path):
        receipt = recibir_captura_audio(
            actor=actor,
            clave_idempotencia=uuid4(),
            proforma_id=quote.id,
            archivo=SimpleUploadedFile(
                "synthetic.webm", b"controlled-test-audio", content_type="audio/webm"
            ),
        )
        state = procesar_intento(
            intento_id=receipt.intento.id, servicio_asr=asr, adaptador_nlp=adapter
        )
        receipt.intento.refresh_from_db()
        receipt.captura.refresh_from_db()
        assert receipt.captura.texto_transcrito == text
        assert ruta_audio(receipt.intento.id) is None
        if length == 20000:
            assert state == "FINALIZADO"
            assert adapter.extraer.call_count == 1
        else:
            assert state == "ERROR"
            assert receipt.intento.error_codigo == "TRANSCRIPT_TOO_LONG"
            assert "20000" in receipt.intento.error_detalle.replace(".", "").replace(",", "")
            assert adapter.extraer.call_count == 0
            assert not ItemIA.objects.filter(intento=receipt.intento).exists()
        assert not quote.detalles.exists()
