"""Validación del JSON técnico comercial único (AP6.0.21).

Los atributos desconocidos son válidos: no se inventan listas cerradas.
Sólo los atributos con semántica conocida tienen restricciones de tipos.
"""

from rest_framework.exceptions import ValidationError


def validar_datos_tecnicos(datos):
    if not isinstance(datos, dict):
        raise ValidationError("Debe ser un objeto JSON.")
    if "schema_version" in datos:
        raise ValidationError("schema_version no forma parte del formato comercial.")

    componentes = datos.get("componentes")
    if componentes is not None:
        if not isinstance(componentes, list):
            raise ValidationError("componentes debe ser un array.")
        for indice, componente in enumerate(componentes, start=1):
            if (
                not isinstance(componente, dict)
                or not isinstance(componente.get("nombre"), str)
                or not componente["nombre"].strip()
            ):
                raise ValidationError(f"Componente {indice}: nombre obligatorio.")
            for campo in ("material", "espesor", "color", "acabado", "dimensiones"):
                if (
                    campo in componente
                    and componente[campo] is not None
                    and not isinstance(componente[campo], (str, dict))
                ):
                    raise ValidationError(f"Componente {indice}: {campo} debe ser texto u objeto.")

    for campo in ("accesorios", "advertencias"):
        if campo not in datos:
            continue
        valores = datos[campo]
        if not isinstance(valores, list) or any(
            not isinstance(valor, str) or not valor.strip() for valor in valores
        ):
            raise ValidationError(f"{campo} debe ser una lista de textos no vacíos.")
    if "descripcion_original" in datos and not isinstance(datos["descripcion_original"], str):
        raise ValidationError("descripcion_original debe ser texto.")
    if "caracteristicas_generales" in datos and not isinstance(
        datos["caracteristicas_generales"], dict
    ):
        raise ValidationError("caracteristicas_generales debe ser un objeto.")
    return datos
