import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from homex_nlp.asr import AsrService
from rest_framework.test import APIClient

from apps.capturas.audio import ruta_audio
from apps.capturas.models import Captura, IntentoCaptura, ItemIA, TrabajoOutbox
from apps.capturas.outbox import publicar_pendientes, reconciliar_publicados
from apps.capturas.pipeline import procesar_intento
from apps.capturas.services import recibir_captura_audio, recibir_captura_texto
from apps.capturas.tasks import limpiar_audio_temporal_task
from apps.proformas.services import crear_proforma
from tests.factories import cliente_persona, vendedor


class TranscriptorPrueba:
    model_version = "asr-prueba-1"

    def transcribe(self, path: Path):
        assert path.exists()
        yield 0.0, 2.0, "Tres escritorios, total cien bolivianos"


class TranscriptorFallido:
    model_version = "asr-fallido-1"

    def transcribe(self, path: Path):
        raise RuntimeError("fallo simulado")
        yield  # pragma: no cover


def audio(nombre="dictado.webm"):
    return SimpleUploadedFile(nombre, b"audio-de-prueba", content_type="audio/webm")


def escenario(django_user_model, nombre):
    actor = vendedor(django_user_model.objects.create_user(username=nombre))
    proforma = crear_proforma(actor=actor, cliente=cliente_persona(actor, sufijo=nombre))
    return actor, proforma


@pytest.mark.django_db(transaction=True)
def test_api_audio_crea_temporal_privado_sin_persistir_ruta(django_user_model, tmp_path):
    actor, proforma = escenario(django_user_model, "f082-api-audio")
    cliente = APIClient()
    cliente.force_authenticate(actor)
    with override_settings(HOMEX_AUDIO_TEMP_ROOT=tmp_path):
        respuesta = cliente.post(
            "/api/v1/capturas/",
            {"clave_idempotencia": str(uuid4()), "proforma": proforma.id, "audio": audio()},
            format="multipart",
        )
        assert respuesta.status_code == 202
        intento = IntentoCaptura.objects.get(pk=respuesta.data["intento_id"])
        temporal = ruta_audio(intento.id)
        assert temporal is not None and temporal.exists()
        assert temporal.stat().st_mode & 0o077 == 0
        captura = intento.captura
        assert captura.texto_transcrito is None
        assert not any("audio" in campo.name for campo in Captura._meta.fields)


@pytest.mark.django_db(transaction=True)
def test_api_exige_exactamente_un_input_y_valida_formato_audio(django_user_model, tmp_path):
    actor, proforma = escenario(django_user_model, "f082-contrato-input")
    cliente = APIClient()
    cliente.force_authenticate(actor)
    base = {"clave_idempotencia": str(uuid4()), "proforma": proforma.id}
    with override_settings(HOMEX_AUDIO_TEMP_ROOT=tmp_path):
        assert cliente.post("/api/v1/capturas/", base, format="multipart").status_code == 400
        ambos = {**base, "texto": "Una mesa", "audio": audio()}
        assert cliente.post("/api/v1/capturas/", ambos, format="multipart").status_code == 400
        invalido = {
            **base,
            "clave_idempotencia": str(uuid4()),
            "audio": SimpleUploadedFile("dictado.txt", b"no-audio", content_type="text/plain"),
        }
        assert cliente.post("/api/v1/capturas/", invalido, format="multipart").status_code == 400


@pytest.mark.django_db(transaction=True)
def test_replay_audio_idempotente_reutiliza_captura_sin_duplicar_temporal(
    django_user_model, tmp_path
):
    actor, proforma = escenario(django_user_model, "f082-replay-audio")
    clave = uuid4()
    with override_settings(HOMEX_AUDIO_TEMP_ROOT=tmp_path):
        inicial = recibir_captura_audio(
            actor=actor, clave_idempotencia=clave, proforma_id=proforma.id, archivo=audio()
        )
        repetida = recibir_captura_audio(
            actor=actor, clave_idempotencia=clave, proforma_id=proforma.id, archivo=audio()
        )
        assert repetida.reutilizada is True
        assert repetida.captura.id == inicial.captura.id
        assert repetida.intento.id == inicial.intento.id
        assert len(list(tmp_path.glob("intento-*"))) == 1


@pytest.mark.django_db(transaction=True)
def test_pipeline_asr_nlp_elimina_audio_y_persiste_evidencia(django_user_model, tmp_path):
    actor, proforma = escenario(django_user_model, "f082-pipeline")
    with override_settings(HOMEX_AUDIO_TEMP_ROOT=tmp_path):
        recepcion = recibir_captura_audio(
            actor=actor,
            clave_idempotencia=uuid4(),
            proforma_id=proforma.id,
            archivo=audio(),
        )
        assert (
            procesar_intento(
                intento_id=recepcion.intento.id,
                servicio_asr=AsrService(TranscriptorPrueba()),
            )
            == "FINALIZADO"
        )
        recepcion.intento.refresh_from_db()
        recepcion.captura.refresh_from_db()
        assert recepcion.intento.estado == "FINALIZADO"
        assert recepcion.intento.etapa_alcanzada == "COMPLETO"
        assert recepcion.intento.modelo_asr_version == "asr-prueba-1"
        assert recepcion.intento.resultado_raw["schema_version"] == "1.0"
        assert recepcion.captura.estado == "COMPLETADA"
        assert recepcion.captura.texto_transcrito == "Tres escritorios, total cien bolivianos"
        assert ruta_audio(recepcion.intento.id) is None
        assert ItemIA.objects.filter(intento=recepcion.intento).count() <= 1


@pytest.mark.django_db(transaction=True)
def test_fallo_asr_cierra_intento_y_elimina_audio(django_user_model, tmp_path):
    actor, proforma = escenario(django_user_model, "f082-asr-error")
    with override_settings(HOMEX_AUDIO_TEMP_ROOT=tmp_path):
        recepcion = recibir_captura_audio(
            actor=actor,
            clave_idempotencia=uuid4(),
            proforma_id=proforma.id,
            archivo=audio(),
        )
        assert (
            procesar_intento(
                intento_id=recepcion.intento.id,
                servicio_asr=AsrService(TranscriptorFallido()),
            )
            == "ERROR"
        )
        recepcion.intento.refresh_from_db()
        assert recepcion.intento.estado == "ERROR"
        assert recepcion.intento.error_codigo == "TRANSCRIPTION_FAILED"
        assert ruta_audio(recepcion.intento.id) is None


@pytest.mark.django_db(transaction=True)
def test_redelivery_procesa_texto_sin_requerir_audio(django_user_model, tmp_path):
    actor, proforma = escenario(django_user_model, "f082-redelivery")
    with override_settings(HOMEX_AUDIO_TEMP_ROOT=tmp_path):
        recepcion = recibir_captura_texto(
            actor=actor,
            clave_idempotencia=uuid4(),
            proforma_id=proforma.id,
            texto="Tres escritorios, total cien bolivianos",
        )
        IntentoCaptura.objects.filter(pk=recepcion.intento.id).update(estado="PROCESANDO")
        trabajo = TrabajoOutbox.objects.get(intento=recepcion.intento)
        TrabajoOutbox.objects.filter(pk=trabajo.pk).update(
            publicado_at=timezone.now() - timedelta(hours=2)
        )
        with override_settings(HOMEX_OUTBOX_RECONCILE_SECONDS=3600):
            assert reconciliar_publicados() == 1
        assert procesar_intento(intento_id=recepcion.intento.id) == "FINALIZADO"
        assert procesar_intento(intento_id=recepcion.intento.id) == "FINALIZADO"
        assert ItemIA.objects.filter(intento_id=recepcion.intento.id).count() <= 1


@pytest.mark.django_db(transaction=True)
def test_entrega_duplicada_no_ejecuta_un_segundo_worker(django_user_model):
    actor, proforma = escenario(django_user_model, "f082-entrega-duplicada")
    recepcion = recibir_captura_texto(
        actor=actor,
        clave_idempotencia=uuid4(),
        proforma_id=proforma.id,
        texto="Una mesa",
    )
    IntentoCaptura.objects.filter(pk=recepcion.intento.id).update(estado="PROCESANDO")
    assert procesar_intento(intento_id=recepcion.intento.id) == "PROCESANDO"
    assert not ItemIA.objects.filter(intento_id=recepcion.intento.id).exists()


@pytest.mark.django_db(transaction=True)
def test_worker_tardio_no_reescribe_intento_terminal(django_user_model):
    actor, proforma = escenario(django_user_model, "f082-worker-tardio")
    recepcion = recibir_captura_texto(
        actor=actor,
        clave_idempotencia=uuid4(),
        proforma_id=proforma.id,
        texto="Tres escritorios, total cien bolivianos",
    )
    assert procesar_intento(intento_id=recepcion.intento.id) == "FINALIZADO"
    recepcion.intento.refresh_from_db()
    evidencia = recepcion.intento.resultado_raw
    fin = recepcion.intento.fin_at
    assert procesar_intento(intento_id=recepcion.intento.id) == "FINALIZADO"
    recepcion.intento.refresh_from_db()
    assert recepcion.intento.resultado_raw == evidencia
    assert recepcion.intento.fin_at == fin


@pytest.mark.django_db(transaction=True)
def test_redis_indisponible_no_pierde_outbox(django_user_model):
    actor, proforma = escenario(django_user_model, "f082-redis-error")
    recepcion = recibir_captura_texto(
        actor=actor,
        clave_idempotencia=uuid4(),
        proforma_id=proforma.id,
        texto="Una mesa",
    )

    def redis_caido(**kwargs):
        raise ConnectionError("redis caído")

    assert publicar_pendientes(enviar=redis_caido) == {"publicados": 0, "errores": 1}
    trabajo = TrabajoOutbox.objects.get(intento=recepcion.intento)
    assert trabajo.publicado_at is None
    assert trabajo.intentos_publicacion == 1
    assert trabajo.ultimo_error == "ConnectionError"


@pytest.mark.django_db(transaction=True)
def test_publicacion_y_reconciliacion_outbox(django_user_model):
    actor, proforma = escenario(django_user_model, "f082-reconciliar")
    recepcion = recibir_captura_texto(
        actor=actor,
        clave_idempotencia=uuid4(),
        proforma_id=proforma.id,
        texto="Una mesa",
    )
    enviados = []

    def enviar(**kwargs):
        enviados.append(kwargs)

    assert publicar_pendientes(enviar=enviar) == {"publicados": 1, "errores": 0}
    trabajo = TrabajoOutbox.objects.get(intento=recepcion.intento)
    assert enviados[0]["task_id"] == trabajo.clave_unica
    TrabajoOutbox.objects.filter(pk=trabajo.pk).update(
        publicado_at=timezone.now() - timedelta(hours=2)
    )
    with override_settings(HOMEX_OUTBOX_RECONCILE_SECONDS=3600):
        assert reconciliar_publicados() == 1
    trabajo.refresh_from_db()
    assert trabajo.publicado_at is None
    assert trabajo.ultimo_error == "RECONCILIADO"


@pytest.mark.django_db(transaction=True)
def test_limpieza_elimina_huerfano_vencido(django_user_model, tmp_path):
    actor, proforma = escenario(django_user_model, "f082-limpieza")
    with override_settings(HOMEX_AUDIO_TEMP_ROOT=tmp_path, HOMEX_AUDIO_TTL_SECONDS=60):
        recepcion = recibir_captura_audio(
            actor=actor,
            clave_idempotencia=uuid4(),
            proforma_id=proforma.id,
            archivo=audio(),
        )
        temporal = ruta_audio(recepcion.intento.id)
        assert temporal is not None
        antiguo = (timezone.now() - timedelta(minutes=2)).timestamp()
        os.utime(temporal, (antiguo, antiguo))
        assert limpiar_audio_temporal_task.run() == 1
        assert not temporal.exists()


@pytest.mark.django_db(transaction=True)
def test_no_existe_endpoint_historico_de_audio(django_user_model):
    actor, _ = escenario(django_user_model, "f082-sin-audio-historico")
    cliente = APIClient()
    cliente.force_authenticate(actor)
    assert cliente.get("/api/v1/capturas/1/audio/").status_code == 404
