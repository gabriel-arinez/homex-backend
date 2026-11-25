from rest_framework import serializers

from apps.catalogo.models import ValorCatalogo


def validar_celular_8_digitos(celular: str | None, *, requerido: bool = True) -> str | None:
    limpio = (celular or "").strip() if isinstance(celular, str) else ""
    if not limpio:
        return "Ingrese un número de celular de 8 dígitos." if requerido else None
    if not limpio.isdigit() or len(limpio) != 8:
        return "El celular debe tener exactamente 8 dígitos."
    return None


def validar_identidad_cliente(datos, *, instance=None):
    tipo = datos.get("tipo_cliente") or (instance.tipo_cliente if instance else None)
    if tipo is None:
        raise serializers.ValidationError({"tipo_cliente": "Seleccione un tipo de cliente."})
    if tipo.concepto.codigo != "TIPO_CLIENTE" or tipo.codigo not in {"PERSONA", "EMPRESA"}:
        raise serializers.ValidationError({"tipo_cliente": "El tipo de cliente no es válido."})
    if instance and tipo.id != instance.tipo_cliente_id:
        raise serializers.ValidationError(
            {"tipo_cliente": "El tipo no puede cambiar después de registrar el cliente."}
        )

    def valor(campo):
        actual = datos.get(campo, getattr(instance, campo, None) if instance else None)
        return actual.strip() if isinstance(actual, str) else actual

    errores = {}
    if not valor("nombres"):
        errores["nombres"] = "Ingrese los nombres del cliente o contacto."
    if not valor("apellidos"):
        errores["apellidos"] = "Ingrese los apellidos del cliente o contacto."
    if tipo.codigo == "EMPRESA" and not valor("empresa"):
        errores["empresa"] = "Ingrese la empresa o razón social."
    if tipo.codigo == "PERSONA" and valor("empresa"):
        errores["empresa"] = "Una persona natural no utiliza razón social."

    celular = valor("celular")
    direccion = valor("direccion")
    exigir_contacto = instance is None or "celular" in datos or "direccion" in datos
    if exigir_contacto or celular is not None:
        error_celular = validar_celular_8_digitos(
            celular,
            requerido=bool(instance is None or "celular" in datos),
        )
        if error_celular:
            errores["celular"] = error_celular
    if (instance is None or "direccion" in datos) and not direccion:
        errores["direccion"] = "Ingrese la dirección del cliente."

    if errores:
        raise serializers.ValidationError(errores)
    return datos


def tipos_cliente_activos():
    return ValorCatalogo.objects.filter(concepto__codigo="TIPO_CLIENTE", activo=True)
