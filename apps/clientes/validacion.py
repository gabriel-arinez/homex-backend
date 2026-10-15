from rest_framework import serializers

from apps.catalogo.models import ValorCatalogo


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
    if errores:
        raise serializers.ValidationError(errores)
    return datos


def tipos_cliente_activos():
    return ValorCatalogo.objects.filter(concepto__codigo="TIPO_CLIENTE", activo=True)
