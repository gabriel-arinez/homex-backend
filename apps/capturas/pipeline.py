from __future__ import annotations

import logging
from decimal import Decimal
from time import perf_counter

from django.db import transaction
from django.utils import timezone
from homex_nlp.errors import HomexError

from apps.capturas.asr import construir_servicio_asr
from apps.capturas.audio import copiar_audio_para_asr, eliminar_audio, ruta_audio
from apps.capturas.models import Captura, IntentoCaptura, ItemIA
from apps.capturas.nlp.adapter import AdaptadorNLP


logger = logging.getLogger(__name__)


def _texto_color(valor):
    if not valor:
        return None
    for clave in ("normalized_value", "value", "text"):
        if valor.get(clave):
            return str(valor[clave])[:150]
    return None


def _cerrar_error(intento_id: int, *, codigo: str, detalle: str, inicio: float) -> None:
    with transaction.atomic():
        intento = (
            IntentoCaptura.objects.select_for_update().select_related("captura").get(pk=intento_id)
        )
        if intento.estado in {"FINALIZADO", "ERROR"}:
            return
        intento.estado = "ERROR"
        intento.fin_at = timezone.now()
        intento.latencia_total_ms = int((perf_counter() - inicio) * 1000)
        intento.error_codigo = codigo[:100]
        intento.error_detalle = detalle
        intento.save(
            update_fields=["estado", "fin_at", "latencia_total_ms", "error_codigo", "error_detalle"]
        )
        Captura.objects.filter(pk=intento.captura_id).exclude(estado="COMPLETADA").update(
            estado="ERROR"
        )


def _persistir_transcripcion(*, captura_id: int, texto: str) -> str:
    """Persiste el texto antes de permitir que el audio original sea eliminado."""
    with transaction.atomic():
        captura = Captura.objects.select_for_update().get(pk=captura_id)
        if captura.texto_transcrito:
            return captura.texto_transcrito
        captura.texto_transcrito = texto
        captura.save(update_fields=["texto_transcrito"])
        return texto


def procesar_intento(*, intento_id: int, servicio_asr=None, adaptador_nlp=None) -> str:
    inicio = perf_counter()
    with transaction.atomic():
        intento = (
            IntentoCaptura.objects.select_for_update().select_related("captura").get(pk=intento_id)
        )
        if intento.estado in {"FINALIZADO", "ERROR", "PROCESANDO"}:
            return intento.estado
        intento.estado = "PROCESANDO"
        intento.save(update_fields=["estado"])
        Captura.objects.filter(pk=intento.captura_id).exclude(estado="COMPLETADA").update(
            estado="PROCESANDO"
        )
        captura_id = intento.captura_id

    try:
        captura = Captura.objects.select_related("proforma__moneda").get(pk=captura_id)
        texto = captura.texto_transcrito
        latencia_asr = None
        modelo_asr = None
        if not texto:
            if ruta_audio(intento_id) is None:
                raise RuntimeError("Audio temporal no disponible.")
            servicio = servicio_asr or construir_servicio_asr()
            copia_asr = copiar_audio_para_asr(intento_id)
            transcripcion = servicio.transcribe(copia_asr)
            texto = _persistir_transcripcion(
                captura_id=captura_id,
                texto=transcripcion.text_original,
            )
            latencia_asr = transcripcion.latency_ms
            modelo_asr = transcripcion.model_version
            try:
                eliminar_audio(intento_id)
            except OSError:
                logger.warning(
                    "No se pudo eliminar inmediatamente el audio temporal del intento %s; "
                    "se delega a la limpieza de huérfanos.",
                    intento_id,
                )

        resultado = (adaptador_nlp or AdaptadorNLP()).extraer(
            solicitud_id=f"captura-{captura_id}-intento-{intento_id}",
            texto=texto,
            moneda=captura.proforma.moneda.codigo,
        )
        with transaction.atomic():
            intento = (
                IntentoCaptura.objects.select_for_update()
                .select_related("captura")
                .get(pk=intento_id)
            )
            if intento.estado in {"FINALIZADO", "ERROR"}:
                return intento.estado
            intento.estado = "FINALIZADO"
            intento.etapa_alcanzada = "COMPLETO"
            intento.modelo_asr_version = modelo_asr
            intento.modelo_nlp_version = str(resultado.motor.get("rules_version") or "RULES_ONLY")
            intento.fin_at = timezone.now()
            intento.latencia_asr_ms = latencia_asr
            intento.latencia_nlp_ms = resultado.latencia_nlp_ms
            intento.latencia_total_ms = int((perf_counter() - inicio) * 1000)
            intento.labels_detectados = [
                candidato.get("label") for candidato in resultado.candidatos
            ]
            intento.resultado_raw = resultado.resultado_original
            intento.save()
            if resultado.propuesta is not None:
                precio = resultado.propuesta.precio or {}
                ItemIA.objects.create(
                    intento=intento,
                    nombre=resultado.propuesta.nombre,
                    espesor=list(resultado.propuesta.espesores) or None,
                    color_principal=_texto_color(resultado.propuesta.color_principal),
                    color_secundario=_texto_color(resultado.propuesta.color_secundario),
                    dimensiones=list(resultado.propuesta.dimensiones) or None,
                    accesorios=list(resultado.propuesta.accesorios) or None,
                    cantidad=resultado.propuesta.cantidad,
                    precio_total=Decimal(precio["line_total"])
                    if precio.get("line_total")
                    else None,
                    observaciones=resultado.propuesta.observaciones,
                )
            Captura.objects.filter(pk=captura_id).update(estado="COMPLETADA")
        return "FINALIZADO"
    except HomexError as exc:
        _cerrar_error(intento_id, codigo=exc.detail.code, detalle=exc.detail.message, inicio=inicio)
        return "ERROR"
    except Exception:
        _cerrar_error(
            intento_id,
            codigo="PIPELINE_ERROR",
            detalle="No se pudo procesar la captura.",
            inicio=inicio,
        )
        return "ERROR"
