"""Huella optimista de la identidad y estado comercial del cliente AP4."""
import hashlib
import json

from apps.clientes.models import Cliente


def revision_cliente(cliente: Cliente) -> str:
    # Se calcula sobre el registro obtenido bajo SELECT FOR UPDATE al escribir.
    campos = (
        "id", "tipo_cliente_id", "nombres", "apellidos", "empresa",
        "celular", "direccion", "observaciones", "activo", "created_by_id",
        "updated_by_id",
    )
    datos = {campo: getattr(cliente, campo) for campo in campos}
    payload = json.dumps(datos, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
