from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.catalogo.models import Producto, ValorCatalogo
from apps.catalogo.services import precio_catalogo_vigente
from apps.clientes.models import Cliente
from apps.clientes.services import crear_cliente
from apps.core.exceptions import ConflictoComercial
from apps.proformas.models import DetalleProforma, EspecificacionMueble, Proforma
from apps.proformas.revision import revision_proforma


class ErrorComercial(ValidationError):
    pass


def valor_catalogo(concepto: str, codigo: str) -> ValorCatalogo:
    try:
        return ValorCatalogo.objects.get(concepto__codigo=concepto, codigo=codigo, activo=True)
    except ValorCatalogo.DoesNotExist as exc:
        raise ErrorComercial({"catalogo": f"No existe {concepto}.{codigo} activo."}) from exc


def _verificar_cliente_visible(*, actor, cliente: Cliente | None, proforma=None) -> None:
    """Una FK valida no autoriza a utilizar datos comerciales de otro vendedor."""
    if cliente is None:
        return
    permitidos = Cliente.objects.filter(pk=cliente.pk)
    if proforma is None or proforma.cliente_id != cliente.pk:
        permitidos = permitidos.filter(activo=True)
    if not (actor.is_staff or actor.is_superuser):
        permitidos = permitidos.filter(created_by=actor)
    if not permitidos.exists():
        raise NotFound("El cliente no existe.")


def _validar_contenido_emitido(proforma_id: int) -> None:
    """No permitir que una revisión pierda los requisitos con los que fue emitida."""
    proforma = Proforma.objects.select_related("estado").get(pk=proforma_id)
    if proforma.estado.codigo not in {"EN_REVISION", "ENVIADA"}:
        return
    if proforma.cliente_id is None:
        raise ConflictoComercial({"cliente": "Una proforma en revisión requiere cliente."})
    detalles = DetalleProforma.objects.filter(proforma_id=proforma_id)
    if not detalles.exists() or proforma.total <= 0:
        raise ConflictoComercial(
            {"detalles": "Una proforma en revisión requiere líneas e importe positivo."}
        )


def _siguiente_numero_proforma() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval('seq_proformas_numero')")
        return cursor.fetchone()[0]


@transaction.atomic
def crear_proforma(*, actor, moneda_codigo="BOB", **datos) -> Proforma:
    _verificar_cliente_visible(actor=actor, cliente=datos.get("cliente"))
    return Proforma.objects.create(
        numero=_siguiente_numero_proforma(),
        vendedor=actor,
        estado=valor_catalogo("ESTADO_PROFORMA", "BORRADOR"),
        moneda=valor_catalogo("MONEDA", moneda_codigo),
        fecha=timezone.localdate(),
        created_by=actor,
        updated_by=actor,
        **datos,
    )


def _proforma_bloqueada(proforma_id: int, actor) -> Proforma:
    try:
        proforma = Proforma.objects.select_for_update().get(pk=proforma_id)
    except Proforma.DoesNotExist as exc:
        raise ErrorComercial({"proforma": "La proforma no existe."}) from exc
    if proforma.vendedor_id != actor.id and not (actor.is_staff or actor.is_superuser):
        raise ErrorComercial({"proforma": "No puede modificar una proforma de otro vendedor."})
    return proforma


def _exigir_proforma_editable(proforma: Proforma, campo: str = "proforma") -> None:
    if proforma.estado.codigo not in {"BORRADOR", "EN_REVISION"}:
        raise ConflictoComercial(
            {campo: "Sólo una proforma BORRADOR o EN_REVISION admite cambios."}
        )


def _validar_modo(modo: str, importe_negociado):
    if modo != "PRECIO_UNITARIO":
        raise ErrorComercial({"modo_calculo": "Los ítems nuevos sólo admiten PRECIO_UNITARIO."})
    if importe_negociado is not None:
        raise ErrorComercial(
            {"importe_negociado": "No se admite en el flujo nuevo de precio unitario."}
        )


def _validar_precio_unitario(modo: str, precio_unitario) -> None:
    """Impide persistir líneas nuevas sin un precio comercial utilizable."""
    if modo != "PRECIO_UNITARIO":
        return
    try:
        precio = Decimal(precio_unitario)
    except (InvalidOperation, TypeError, ValueError):
        precio = None
    if precio is None or not precio.is_finite() or precio <= 0:
        raise ErrorComercial(
            {"precio_unitario": "Debe registrar un precio unitario mayor que cero."}
        )


def _precio_catalogo(proforma: Proforma, producto: Producto, datos: dict) -> dict:
    if proforma.moneda.codigo == "USD":
        if datos.get("precio_unitario") is None:
            raise ErrorComercial(
                {"precio_unitario": "Una cotización USD requiere precio explícito."}
            )
        return datos
    antes, ahora, descuento_unitario = precio_catalogo_vigente(producto)
    if descuento_unitario < 0:
        raise ErrorComercial({"producto": "La promoción tiene precios inconsistentes."})

    # El catálogo propone el precio, pero el vendedor conserva autoridad sobre
    # precio unitario y descuento en la proforma.
    datos.setdefault("precio_unitario", ahora)
    datos.setdefault("descuento", Decimal("0.00"))
    if descuento_unitario > 0:
        datos["precio_antes_snapshot"] = antes
        datos["precio_ahora_snapshot"] = ahora
    else:
        datos["precio_antes_snapshot"] = None
        datos["precio_ahora_snapshot"] = None

    # Los snapshots ANTES/AHORA representan una promoción real; sin promoción quedan NULL.
    return datos


@transaction.atomic
def agregar_detalle(*, proforma_id: int, actor, **datos) -> DetalleProforma:
    proforma = _proforma_bloqueada(proforma_id, actor)
    _exigir_proforma_editable(proforma)
    modo = datos.get("modo_calculo", "PRECIO_UNITARIO")
    _validar_modo(modo, datos.get("importe_negociado"))
    producto = datos.get("producto")
    if producto is None and datos.get("producto_id"):
        producto = Producto.objects.get(pk=datos["producto_id"])
    if producto is not None:
        if DetalleProforma.objects.filter(proforma=proforma, producto=producto).exists():
            raise ConflictoComercial({"producto": "La variante ya está incluida en esta proforma."})
        datos = _precio_catalogo(proforma, producto, datos)
    _validar_precio_unitario(modo, datos.get("precio_unitario"))
    return DetalleProforma.objects.create(proforma=proforma, **datos)


@transaction.atomic
def actualizar_detalle(*, detalle_id: int, actor, **datos) -> DetalleProforma:
    detalle = DetalleProforma.objects.only("id", "proforma_id").get(pk=detalle_id)
    # Orden global de locks: cabecera y después línea, también frente al PUT integral.
    proforma = _proforma_bloqueada(detalle.proforma_id, actor)
    detalle = DetalleProforma.objects.select_for_update().get(pk=detalle_id)
    _exigir_proforma_editable(proforma, "detalle")
    modo = datos.get("modo_calculo", detalle.modo_calculo)
    importe = datos.get("importe_negociado", detalle.importe_negociado)
    if detalle.modo_calculo == "TOTAL_NEGOCIADO" and modo == "TOTAL_NEGOCIADO":
        if importe != detalle.importe_negociado or (
            "precio_unitario" in datos and datos["precio_unitario"] != detalle.precio_unitario
        ):
            raise ConflictoComercial(
                {"modo_calculo": "El importe histórico negociado no se convierte automáticamente."}
            )
    else:
        _validar_modo(modo, importe)
        _validar_precio_unitario(
            modo,
            datos.get("precio_unitario", detalle.precio_unitario),
        )
    for campo, valor in datos.items():
        setattr(detalle, campo, valor)
    detalle.save()
    _validar_contenido_emitido(proforma.id)
    return detalle


@transaction.atomic
def enviar_proforma(*, proforma_id: int, actor) -> Proforma:
    proforma = _proforma_bloqueada(proforma_id, actor)
    if proforma.estado.codigo != "BORRADOR":
        raise ConflictoComercial({"estado": "Sólo una proforma BORRADOR puede enviarse."})
    proforma.estado = valor_catalogo("ESTADO_PROFORMA", "EN_REVISION")
    proforma.updated_by = actor
    proforma.save(update_fields=["estado", "updated_by"])
    proforma.refresh_from_db()
    return proforma


@transaction.atomic
def crear_especificacion(*, detalle_id: int, actor, **datos) -> EspecificacionMueble:
    detalle = DetalleProforma.objects.only("id", "proforma_id").get(pk=detalle_id)
    # Orden global de locks: cabecera y después línea, también frente al PUT integral.
    proforma = _proforma_bloqueada(detalle.proforma_id, actor)
    detalle = DetalleProforma.objects.select_for_update().get(pk=detalle_id)
    _exigir_proforma_editable(proforma, "detalle")
    return EspecificacionMueble.objects.create(proforma_detalle=detalle, **datos)


@transaction.atomic
def actualizar_proforma(*, proforma_id: int, actor, **datos) -> Proforma:
    proforma = _proforma_bloqueada(proforma_id, actor)
    _exigir_proforma_editable(proforma)
    if "cliente" in datos:
        _verificar_cliente_visible(actor=actor, cliente=datos["cliente"], proforma=proforma)
    for campo, valor in datos.items():
        setattr(proforma, campo, valor)
    proforma.updated_by = actor
    proforma.save()
    return proforma


@transaction.atomic
def eliminar_detalle(*, detalle_id: int, actor) -> None:
    detalle = DetalleProforma.objects.only("id", "proforma_id").get(pk=detalle_id)
    # Orden global de locks: cabecera y después línea, también frente al PUT integral.
    proforma = _proforma_bloqueada(detalle.proforma_id, actor)
    detalle = DetalleProforma.objects.select_for_update().get(pk=detalle_id)
    _exigir_proforma_editable(proforma, "detalle")
    detalle.delete()
    _validar_contenido_emitido(proforma.id)


@transaction.atomic
def actualizar_especificacion(*, detalle_id: int, actor, **datos) -> EspecificacionMueble:
    detalle = DetalleProforma.objects.only("id", "proforma_id").get(pk=detalle_id)
    # Orden global de locks: cabecera y después línea, también frente al PUT integral.
    proforma = _proforma_bloqueada(detalle.proforma_id, actor)
    detalle = DetalleProforma.objects.select_for_update().get(pk=detalle_id)
    _exigir_proforma_editable(proforma, "detalle")
    especificacion = EspecificacionMueble.objects.select_for_update().get(proforma_detalle=detalle)
    for campo, valor in datos.items():
        setattr(especificacion, campo, valor)
    especificacion.save()
    return especificacion


@transaction.atomic
def marcar_no_concretada(*, proforma_id: int, actor) -> Proforma:
    proforma = _proforma_bloqueada(proforma_id, actor)
    if proforma.estado.codigo not in {"EN_REVISION", "ENVIADA"}:
        raise ConflictoComercial({"estado": "Sólo una proforma en revisión puede no concretarse."})
    proforma.estado = valor_catalogo("ESTADO_PROFORMA", "NO_CONCRETADA")
    proforma.updated_by = actor
    proforma.save(update_fields=["estado", "updated_by"])
    return proforma


@transaction.atomic
def reabrir_proforma(*, proforma_id: int, actor) -> Proforma:
    proforma = _proforma_bloqueada(proforma_id, actor)
    if proforma.estado.codigo != "NO_CONCRETADA":
        raise ConflictoComercial({"estado": "Sólo NO_CONCRETADA puede reabrirse."})
    proforma.estado = valor_catalogo("ESTADO_PROFORMA", "EN_REVISION")
    proforma.updated_by = actor
    proforma.save(update_fields=["estado", "updated_by"])
    return proforma


def _guardar_especificacion_integral(*, detalle, actor, datos):
    if datos is None:
        if hasattr(detalle, "especificacionmueble"):
            # EN_REVISION admite nuevas líneas incompletas para su revisión,
            # pero no debe perder una ficha ya registrada por una edición integral.
            if detalle.proforma.estado.codigo != "BORRADOR":
                raise ConflictoComercial(
                    {"especificacion": "No puede eliminar una ficha existente en revisión."}
                )
            detalle.especificacionmueble.delete()
        return
    datos.pop("proforma_detalle", None)
    if hasattr(detalle, "especificacionmueble"):
        actualizar_especificacion(detalle_id=detalle.id, actor=actor, **datos)
    else:
        crear_especificacion(detalle_id=detalle.id, actor=actor, **datos)


def _sincronizar_detalles(*, proforma, actor, detalles, sesion_borrador=None):
    no_enviada = object()
    existentes = {detalle.id: detalle for detalle in proforma.detalles.all()}
    conservados = set()
    for datos_originales in detalles:
        datos = dict(datos_originales)
        captura_id = datos.pop("captura_asistida_id", None)
        detalle_id = datos.pop("id", None)
        if captura_id and detalle_id is not None:
            raise ConflictoComercial({"captura_asistida_id": "Sólo para líneas nuevas."})
        especificacion = datos.pop("especificacion", no_enviada)
        datos.pop("proforma", None)
        if detalle_id is None:
            detalle = agregar_detalle(proforma_id=proforma.id, actor=actor, **datos)
        else:
            if detalle_id not in existentes:
                raise ConflictoComercial(
                    {"detalles": f"La línea {detalle_id} no pertenece a esta proforma."}
                )
            detalle = actualizar_detalle(detalle_id=detalle_id, actor=actor, **datos)
            conservados.add(detalle_id)
        if especificacion is not no_enviada:
            _guardar_especificacion_integral(
                detalle=detalle,
                actor=actor,
                datos=dict(especificacion) if especificacion is not None else None,
            )
        if captura_id:
            from apps.capturas.asistidas import vincular_asistida

            vincular_asistida(
                captura_id=captura_id, detalle=detalle, actor=actor, sesion_borrador=sesion_borrador
            )
    for detalle_id in existentes.keys() - conservados:
        eliminar_detalle(detalle_id=detalle_id, actor=actor)


def _datos_cabecera_integral(datos):
    campos = {
        "cliente",
        "titulo",
        "plazo_entrega",
        "validez_oferta",
        "porcentaje_adelanto",
        "observaciones",
        "prospecto_nombre",
        "prospecto_empresa",
        "prospecto_celular",
        "prospecto_direccion",
    }
    return {campo: datos[campo] for campo in campos if campo in datos}


@transaction.atomic
def _crear_proforma_integral(*, actor, request_hash: str, **datos) -> Proforma:
    clave = datos.pop("clave_idempotencia")
    emitir = datos.pop("emitir", False)
    detalles = datos.pop("detalles", [])
    cliente_nuevo = datos.pop("cliente_nuevo", None)
    moneda_codigo = datos.pop("moneda_codigo")
    if cliente_nuevo:
        datos["cliente"] = crear_cliente(actor=actor, **cliente_nuevo)
    proforma = crear_proforma(
        actor=actor,
        moneda_codigo=moneda_codigo,
        clave_idempotencia=clave,
        idempotencia_hash=request_hash,
        **_datos_cabecera_integral(datos),
    )
    _sincronizar_detalles(
        proforma=proforma,
        actor=actor,
        detalles=detalles,
        sesion_borrador=datos.pop("sesion_borrador", None),
    )
    if emitir:
        proforma = enviar_proforma(proforma_id=proforma.id, actor=actor)
    return proforma


def crear_proforma_integral(*, actor, request_hash: str, **datos) -> tuple[Proforma, bool]:
    clave = datos["clave_idempotencia"]
    existente = Proforma.objects.filter(clave_idempotencia=clave).first()
    if existente:
        if existente.vendedor_id != actor.id or existente.idempotencia_hash != request_hash:
            raise ConflictoComercial(
                {"clave_idempotencia": "La clave ya fue utilizada con otra operación."}
            )
        return existente, True
    try:
        return _crear_proforma_integral(actor=actor, request_hash=request_hash, **datos), False
    except IntegrityError:
        existente = Proforma.objects.filter(clave_idempotencia=clave).first()
        if (
            existente
            and existente.vendedor_id == actor.id
            and existente.idempotencia_hash == request_hash
        ):
            return existente, True
        raise


@transaction.atomic
def actualizar_proforma_integral(*, proforma_id: int, actor, **datos) -> Proforma:
    proforma = _proforma_bloqueada(proforma_id, actor)
    _exigir_proforma_editable(proforma)
    revision_esperada = datos.pop("revision_esperada", None)
    if not revision_esperada or revision_esperada != revision_proforma(proforma):
        raise ConflictoComercial(
            {"revision_esperada": "La proforma cambió desde que abriste el editor."}
        )
    datos.pop("clave_idempotencia", None)
    emitir = datos.pop("emitir", False)
    detalles = datos.pop("detalles", [])
    cliente_nuevo = datos.pop("cliente_nuevo", None)
    moneda_codigo = datos.pop("moneda_codigo")
    if cliente_nuevo:
        datos["cliente"] = crear_cliente(actor=actor, **cliente_nuevo)
    datos["moneda"] = valor_catalogo("MONEDA", moneda_codigo)
    actualizar_proforma(
        proforma_id=proforma.id,
        actor=actor,
        **_datos_cabecera_integral(datos),
        moneda=datos["moneda"],
    )
    _sincronizar_detalles(
        proforma=proforma,
        actor=actor,
        detalles=detalles,
        sesion_borrador=datos.pop("sesion_borrador", None),
    )
    proforma.refresh_from_db()
    if emitir and proforma.estado.codigo == "BORRADOR":
        proforma = enviar_proforma(proforma_id=proforma.id, actor=actor)
    _validar_contenido_emitido(proforma.id)
    return proforma
