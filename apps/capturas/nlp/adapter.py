from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

import homex_nlp
from homex_nlp.contracts import ExtractionRequest, ExtractionResult
from homex_nlp.engine import RulesEngine

VERSION_PAQUETE_SOPORTADA = "0.1.0"
VERSION_CONTRATO_SOPORTADA = "1.0"
MODO_OPERATIVO = "RULES_ONLY"


class ErrorContratoNLP(ValueError):
    """Error explícito y seguro en la frontera con homex-nlp."""


class PaqueteNLPNoSoportado(ErrorContratoNLP):
    pass


class ContratoNLPNoSoportado(ErrorContratoNLP):
    pass


class ModoNLPNoSoportado(ErrorContratoNLP):
    pass


@dataclass(frozen=True, slots=True)
class PropuestaMueble:
    nombre: str | None
    tipo_mueble_candidato: str | None
    cantidad: int | None
    componentes: tuple[dict[str, Any], ...]
    dimensiones: tuple[dict[str, Any], ...]
    espesores: tuple[dict[str, Any], ...]
    color_principal: dict[str, Any] | None
    color_secundario: dict[str, Any] | None
    accesorios: tuple[dict[str, Any], ...]
    precio: dict[str, Any] | None
    observaciones: str | None
    evidencia_pendiente: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResultadoNLP:
    version_contrato: str
    solicitud_id: str
    estado: str
    texto_original: str
    propuesta: PropuestaMueble | None
    candidatos: tuple[dict[str, Any], ...]
    advertencias: tuple[dict[str, Any], ...]
    motor: dict[str, Any]
    error: dict[str, Any] | None
    latencia_nlp_ms: int | None
    resultado_original: dict[str, Any]


class AdaptadorNLP:
    """Único punto de consumo del contrato público homex-nlp v1."""

    def __init__(self, motor: RulesEngine | None = None) -> None:
        self._validar_version_paquete()
        self._motor = motor or RulesEngine()

    @staticmethod
    def _validar_version_paquete() -> None:
        if homex_nlp.__version__ != VERSION_PAQUETE_SOPORTADA:
            raise PaqueteNLPNoSoportado(
                "Versión homex-nlp no soportada: "
                f"{homex_nlp.__version__}; esperada {VERSION_PAQUETE_SOPORTADA}."
            )

    def extraer(
        self,
        *,
        solicitud_id: str,
        texto: str,
        moneda: str,
        perfil_dominio_version: str | None = None,
    ) -> ResultadoNLP:
        solicitud = ExtractionRequest(
            request_id=solicitud_id,
            text=texto,
            currency_context=moneda,
            domain_profile_version=perfil_dominio_version,
        )
        resultado = self._motor.extract(solicitud)
        return self.transformar(resultado, exigir_rules_only=True)

    def transformar(
        self,
        resultado: ExtractionResult | Mapping[str, Any],
        *,
        exigir_rules_only: bool = True,
    ) -> ResultadoNLP:
        if isinstance(resultado, ExtractionResult):
            contrato = resultado
        else:
            version = resultado.get("schema_version")
            self._validar_version_contrato(version)
            contrato = ExtractionResult.model_validate(dict(resultado))

        self._validar_version_contrato(contrato.schema_version)
        if exigir_rules_only and contrato.engine.mode != MODO_OPERATIVO:
            raise ModoNLPNoSoportado(
                f"Modo NLP no soportado: {contrato.engine.mode}; esperado {MODO_OPERATIVO}."
            )

        original = contrato.model_dump(mode="json")
        propuesta = self._mapear_propuesta(original.get("item_proposal"))
        return ResultadoNLP(
            version_contrato=contrato.schema_version,
            solicitud_id=contrato.request_id,
            estado=contrato.status,
            texto_original=contrato.text_original,
            propuesta=propuesta,
            candidatos=tuple(deepcopy(original["candidates"])),
            advertencias=tuple(deepcopy(original["warnings"])),
            motor=deepcopy(original["engine"]),
            error=deepcopy(original["error"]),
            latencia_nlp_ms=contrato.latency_nlp_ms,
            resultado_original=deepcopy(original),
        )

    @staticmethod
    def _validar_version_contrato(version: object) -> None:
        if version != VERSION_CONTRATO_SOPORTADA:
            raise ContratoNLPNoSoportado(
                f"schema_version no soportada: {version!r}; "
                f"esperada {VERSION_CONTRATO_SOPORTADA!r}."
            )

    @staticmethod
    def _mapear_propuesta(propuesta: dict[str, Any] | None) -> PropuestaMueble | None:
        if propuesta is None:
            return None
        return PropuestaMueble(
            nombre=propuesta["name"],
            tipo_mueble_candidato=propuesta["furniture_type_candidate"],
            cantidad=propuesta["quantity"],
            componentes=tuple(deepcopy(propuesta["components"])),
            dimensiones=tuple(deepcopy(propuesta["dimensions"])),
            espesores=tuple(deepcopy(propuesta["thicknesses"])),
            color_principal=deepcopy(propuesta["primary_color"]),
            color_secundario=deepcopy(propuesta["secondary_color"]),
            accesorios=tuple(deepcopy(propuesta["accessories"])),
            precio=deepcopy(propuesta["price"]),
            observaciones=propuesta["observations"],
            evidencia_pendiente=tuple(propuesta["unresolved"]),
        )
