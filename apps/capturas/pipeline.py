from __future__ import annotations

import logging
from decimal import Decimal
from time import perf_counter
from uuid import uuid4

from django.db import transaction
from django.utils import timezone
from homex_nlp.errors import HomexError

from apps.capturas.asr import construir_servicio_asr
from apps.capturas.audio import copiar_audio_para_asr, eliminar_audio, ruta_audio
from apps.capturas.bloqueo_ejecucion import bloqueo_intento
from apps.capturas.models import Captura, IntentoCaptura, ItemIA
from apps.capturas.nlp.adapter import AdaptadorNLP, ErrorContratoNLP

logger = logging.getLogger(__name__)


class EjecucionObsoleta(Exception):
    """El intento ya no pertenece a esta ejecución."""


def _texto_color(valor):
    if not valor:
        return None
    for clave in ("normalized_value", "value", "text"):
        if valor.get(clave):
            return str(valor[clave])[:150]
    return None


def _medida_texto(valor):
    return str(valor.get("original_text") or f"{valor['value']} {valor.get('unit') or ''}").strip()


def _espesor_v1(valores):
    partes = []
    for valor in valores:
        medida = _medida_texto(valor)
        componente = valor.get("component_ref")
        partes.append(f"{componente}: {medida}" if componente else medida)
    return {"espesor": "; ".join(partes)} if partes else None


def _dimensiones_v1(valores):
    dimensiones = {}
    for valor in valores:
        eje = valor.get("axis")
        if eje not in {"ancho", "alto", "profundidad", "largo", "diametro"}:
            continue
        medida = _medida_texto(valor)
        dimensiones[eje] = f"{dimensiones[eje]}; {medida}" if eje in dimensiones else medida
    return dimensiones or None


def _accesorios_v1(valores):
    accesorios = []
    for valor in valores:
        nombre = valor["name"]
        cantidad = valor.get("quantity")
        componente = valor.get("component_ref")
        texto = f"{cantidad} {nombre}" if cantidad is not None else nombre
        accesorios.append(f"{componente}: {texto}" if componente else texto)
    return accesorios or None


def _cerrar_error(
    intento_id: int,
    *,
    token,
    codigo: str,
    detalle: str,
    inicio: float,
) -> str:
    with transaction.atomic():
        intento = (
            IntentoCaptura.objects.select_for_update().select_related("captura").get(pk=intento_id)
        )
        if intento.estado != "PROCESANDO" or intento.ejecucion_token != token:
            return intento.estado
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
        return "ERROR"


def _persistir_transcripcion(*, intento_id: int, captura_id: int, token, texto: str) -> str:
    """Persiste la transcripción únicamente si la ejecución sigue vigente."""
    with transaction.atomic():
        intento = IntentoCaptura.objects.select_for_update().get(pk=intento_id)
        if intento.estado != "PROCESANDO" or intento.ejecucion_token != token:
            raise EjecucionObsoleta()
        captura = Captura.objects.select_for_update().get(pk=captura_id)
        if captura.texto_transcrito:
            return captura.texto_transcrito
        captura.texto_transcrito = texto
        captura.save(update_fields=["texto_transcrito"])
        return texto


def procesar_intento(*, intento_id: int, servicio_asr=None, adaptador_nlp=None) -> str:
    with bloqueo_intento(intento_id) as adquirido:
        if not adquirido:
            return "PROCESANDO"
        return _procesar_intento_bloqueado(
            intento_id=intento_id,
            servicio_asr=servicio_asr,
            adaptador_nlp=adaptador_nlp,
        )


def _procesar_intento_bloqueado(*, intento_id: int, servicio_asr=None, adaptador_nlp=None) -> str:
    inicio = perf_counter()
    with transaction.atomic():
        intento = (
            IntentoCaptura.objects.select_for_update().select_related("captura").get(pk=intento_id)
        )
        if intento.estado in {"FINALIZADO", "ERROR", "PROCESANDO"}:
            return intento.estado
        token = uuid4()
        intento.estado = "PROCESANDO"
        intento.ejecucion_token = token
        intento.save(update_fields=["estado", "ejecucion_token"])
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
                intento_id=intento_id,
                captura_id=captura_id,
                token=token,
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
            moneda=(
                captura.proforma.moneda.codigo
                if captura.proforma_id
                else captura.moneda_contexto_codigo
            ),
        )
        with transaction.atomic():
            intento = (
                IntentoCaptura.objects.select_for_update()
                .select_related("captura")
                .get(pk=intento_id)
            )
            if intento.estado != "PROCESANDO" or intento.ejecucion_token != token:
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
            if captura.modo_captura == "ASISTIDA_CREACION_MUEBLE":
                from apps.capturas.proyeccion_prf03 import proyectar

                intento.proyeccion_configurador = proyectar(resultado.resultado_original)
            intento.save()
            if resultado.propuesta is not None:
                precio = resultado.propuesta.precio or {}
                ItemIA.objects.create(
                    intento=intento,
                    nombre=resultado.propuesta.nombre,
                    espesor=_espesor_v1(resultado.propuesta.espesores),
                    color_principal=_texto_color(resultado.propuesta.color_principal),
                    color_secundario=_texto_color(resultado.propuesta.color_secundario),
                    dimensiones=_dimensiones_v1(resultado.propuesta.dimensiones),
                    accesorios=(
                        _accesorios_v1(resultado.propuesta.accesorios)
                        or (
                            [
                                c["name"]
                                for c in resultado.propuesta.componentes
                                if c["name"].casefold() in {"cajones", "puertas"}
                            ]
                            or None
                        )
                        if captura.modo_captura == "LEGADA"
                        else _accesorios_v1(resultado.propuesta.accesorios)
                    ),
                    cantidad=resultado.propuesta.cantidad,
                    precio_total=Decimal(precio["line_total"])
                    if precio.get("line_total")
                    else None,
                    observaciones=resultado.propuesta.observaciones,
                )
            Captura.objects.filter(pk=captura_id).update(estado="COMPLETADA")
        return "FINALIZADO"
    except EjecucionObsoleta:
        return IntentoCaptura.objects.get(pk=intento_id).estado
    except ErrorContratoNLP:
        return _cerrar_error(
            intento_id,
            token=token,
            codigo="NLP_CONTRACT_INCOMPATIBLE",
            detalle="El contrato del motor NLP no es compatible con el backend.",
            inicio=inicio,
        )
    except HomexError as exc:
        return _cerrar_error(
            intento_id,
            token=token,
            codigo=exc.detail.code,
            detalle=exc.detail.message,
            inicio=inicio,
        )
    except Exception:
        return _cerrar_error(
            intento_id,
            token=token,
            codigo="PIPELINE_ERROR",
            detalle="No se pudo procesar la captura.",
            inicio=inicio,
        )
