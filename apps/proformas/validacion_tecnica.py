"""Validación aditiva del JSON técnico comercial único."""

from rest_framework.exceptions import ValidationError

from apps.catalogo.atributos_mueble import MAX_COMPONENTES, MAX_CONJUNTOS, normalizar


def _texto(valor, mensaje, *, maximo=500):
    if not isinstance(valor, str) or not valor.strip() or len(valor) > maximo:
        raise ValidationError(mensaje)


def _atributos(valores, contexto):
    if valores is None:
        return
    if not isinstance(valores, list):
        raise ValidationError(f"{contexto}.atributos debe ser un array.")
    vistos = set()
    for indice, atributo in enumerate(valores, 1):
        if not isinstance(atributo, dict):
            raise ValidationError(f"{contexto}.atributos[{indice}] debe ser un objeto.")
        _texto(atributo.get("nombre"), f"{contexto}: nombre de atributo obligatorio.", maximo=150)
        valor = atributo.get("valor")
        if (
            not isinstance(valor, (str, int, float))
            or isinstance(valor, bool)
            or not str(valor).strip()
        ):
            raise ValidationError(f"{contexto}: valor de atributo obligatorio.")
        clave = normalizar(str(atributo.get("codigo") or atributo["nombre"]))
        if clave in vistos:
            raise ValidationError(f"{contexto}: atributo duplicado {atributo['nombre']}.")
        vistos.add(clave)


def validar_datos_tecnicos(datos, anteriores=None):
    if not isinstance(datos, dict):
        raise ValidationError("Debe ser un objeto JSON.")
    if "schema_version" in datos:
        raise ValidationError("schema_version no forma parte del formato comercial.")

    componentes = datos.get("componentes")
    componentes = [] if componentes is None else componentes
    if not isinstance(componentes, list):
        raise ValidationError("componentes debe ser un array.")
    excede_legacy = len(componentes) > MAX_COMPONENTES and anteriores == datos
    if len(componentes) > MAX_COMPONENTES and not excede_legacy:
        raise ValidationError(f"Máximo {MAX_COMPONENTES} componentes por mueble.")

    uids = set()
    for indice, componente in enumerate(componentes, start=1):
        if not isinstance(componente, dict):
            raise ValidationError(f"Componente {indice}: debe ser un objeto.")
        _texto(componente.get("nombre"), f"Componente {indice}: nombre obligatorio.", maximo=200)
        for campo in ("material", "espesor", "color", "acabado", "dimensiones"):
            if (
                campo in componente
                and componente[campo] is not None
                and not isinstance(componente[campo], (str, dict))
            ):
                raise ValidationError(f"Componente {indice}: {campo} debe ser texto u objeto.")
        if "cantidad_interna" in componente and componente["cantidad_interna"] is not None:
            cantidad = componente["cantidad_interna"]
            if isinstance(cantidad, bool) or not isinstance(cantidad, int) or cantidad <= 0:
                raise ValidationError(
                    f"Componente {indice}: cantidad_interna debe ser entera positiva."
                )
        uid = componente.get("uid")
        if uid is not None:
            _texto(uid, f"Componente {indice}: uid obligatorio.", maximo=100)
            if uid in uids:
                raise ValidationError(f"Componente {indice}: uid repetido.")
            uids.add(uid)
        conjunto_uid = componente.get("conjunto_uid")
        if conjunto_uid is not None:
            _texto(conjunto_uid, f"Componente {indice}: conjunto_uid inválido.", maximo=100)
        _atributos(componente.get("atributos"), f"Componente {indice}")

    conjuntos = datos.get("conjuntos")
    if conjuntos is not None:
        if not isinstance(conjuntos, list):
            raise ValidationError("conjuntos debe ser un array.")
        if len(conjuntos) > MAX_CONJUNTOS and anteriores != datos:
            raise ValidationError(f"Máximo {MAX_CONJUNTOS} conjuntos por mueble.")
        conjuntos_uid = set()
        referencias = {componente.get("conjunto_uid") for componente in componentes}
        for indice, conjunto in enumerate(conjuntos, 1):
            if not isinstance(conjunto, dict):
                raise ValidationError(f"Conjunto {indice}: debe ser un objeto.")
            _texto(conjunto.get("uid"), f"Conjunto {indice}: uid obligatorio.", maximo=100)
            _texto(conjunto.get("nombre"), f"Conjunto {indice}: nombre obligatorio.", maximo=200)
            if conjunto["uid"] in conjuntos_uid:
                raise ValidationError(f"Conjunto {indice}: uid repetido.")
            conjuntos_uid.add(conjunto["uid"])
            if conjunto["uid"] not in referencias:
                raise ValidationError(f"Conjunto {indice}: requiere al menos un componente.")
        if None in referencias:
            referencias.remove(None)
        ajenas = referencias - conjuntos_uid
        if ajenas:
            raise ValidationError("Hay componentes vinculados a conjuntos inexistentes.")
        if conjuntos and any("uid" not in componente for componente in componentes):
            raise ValidationError("Los componentes agrupados requieren uid estable.")

    generales = datos.get("caracteristicas_generales")
    if generales is not None:
        if not isinstance(generales, dict):
            raise ValidationError("caracteristicas_generales debe ser un objeto.")
        _atributos(generales.get("atributos"), "Características generales")

    for campo in ("accesorios", "advertencias"):
        if campo in datos:
            valores = datos[campo]
            if not isinstance(valores, list) or any(
                not isinstance(valor, str) or not valor.strip() for valor in valores
            ):
                raise ValidationError(f"{campo} debe ser una lista de textos no vacíos.")
    if "descripcion_original" in datos and not isinstance(datos["descripcion_original"], str):
        raise ValidationError("descripcion_original debe ser texto.")
    return datos
