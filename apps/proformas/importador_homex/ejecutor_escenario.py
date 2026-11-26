"""Ejecutor transaccional e idempotente del escenario de evaluación HOMEX (v05 y v06)."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.catalogo.importador import ErrorCatalogo, importar_catalogo
from apps.catalogo.models import ConceptoCatalogo, ImagenProducto, Producto, ValorCatalogo
from apps.catalogo.services import reemplazar_imagen_principal
from apps.clientes.models import Cliente
from apps.clientes.services import crear_cliente
from apps.core.tiempo_comercial import fecha_comercial_actual, reloj_comercial_simulado
from apps.movimientos_stock.models import MovimientoStock
from apps.notas_entrega.models import NotaEntrega
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.ordenes_trabajo.services import (
    cambiar_estado_orden_trabajo,
    puede_cambiar_estado_orden_trabajo,
)
from apps.pedidos.models import Pedido
from apps.pedidos.services import aprobar_proforma, cambiar_estado_pedido, cancelar_pedido
from apps.proformas.importador_homex.auditoria import (
    auditar_escenario,
    clave_idempotencia_escenario,
)
from apps.proformas.importador_homex.excepciones import (
    ErrorConciliacionImportacion,
    ErrorConflictoImportacion,
    ErrorImportacionHomex,
)
from apps.proformas.importador_homex.monto_letras import monto_a_letras_bob
from apps.proformas.importador_homex.seguridad_zip import PaqueteMaestroHomex
from apps.proformas.importador_homex.validacion import (
    ResultadoValidacionEscenario,
    parsear_decimal,
    parsear_fecha,
    parsear_fecha_hora,
)
from apps.proformas.models import Proforma, RegistroProcedenciaImportacion
from apps.proformas.services import (
    agregar_detalle,
    anular_proforma,
    crear_especificacion,
    crear_proforma,
    enviar_proforma,
    marcar_no_concretada,
    valor_catalogo,
)
from apps.proformas.vigencia import esta_vencida
from apps.recibos.services import emitir_recibo_idempotente

CATALOGOS_TECNICOS_ESCENARIO = {
    "MARCA": [
        ("EVAL_NO_ESPECIFICADA", "Sin especificar"),
        ("GANESHA", "Ganesha"),
    ],
    "COLOR": [
        ("EVAL_NO_ESPECIFICADO", "Sin especificar"),
        ("ROJO", "Rojo"),
    ],
    "MATERIAL_PISO": [
        ("HDF", "HDF"),
    ],
}

ESTADOS_PROFORMA_POST_BORRADOR = {
    "EN_REVISION",
    "ENVIADA",
    "APROBADA",
    "VENCIDA",
    "ANULADA",
    "NO_CONCRETADA",
    "RECHAZADA",
}


def _marcador_cliente_v05(source_id: str) -> str:
    return (
        f"[HOMEX_IMPORT perfil=ESCENARIO source_id={source_id} "
        "naturaleza=SIMULADO_NO_RESULTADO_MEDIDO]"
    )


def _marcador_proforma_v05(source_id: str, obs_original: str | None) -> str:
    base = _marcador_cliente_v05(source_id)
    if obs_original:
        return f"{base} {obs_original}"
    return base


def _hash_payload(data: object) -> str:
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _registrar_procedencia(
    *,
    entidad: str,
    source_id: str,
    objeto_id: int,
    naturaleza: str,
    payload_hash: str,
    fecha_hora_comercial: datetime | None = None,
    metadatos: dict | None = None,
) -> None:
    RegistroProcedenciaImportacion.objects.update_or_create(
        perfil="ESCENARIO",
        entidad=entidad,
        source_id=source_id,
        defaults={
            "objeto_id": objeto_id,
            "naturaleza": naturaleza,
            "payload_hash": payload_hash,
            "fecha_hora_comercial": fecha_hora_comercial,
            "metadatos": metadatos or {},
        },
    )


def _asegurar_catalogos_tecnicos(actor: User) -> list[str]:
    creados: list[str] = []
    for concepto_codigo, pares in CATALOGOS_TECNICOS_ESCENARIO.items():
        concepto, _ = ConceptoCatalogo.objects.get_or_create(
            codigo=concepto_codigo,
            defaults={"activo": True, "created_by": actor, "updated_by": actor},
        )
        for codigo, nombre in pares:
            obj, creado = ValorCatalogo.objects.get_or_create(
                concepto=concepto,
                codigo=codigo,
                defaults={
                    "nombre": nombre,
                    "activo": True,
                    "created_by": actor,
                    "updated_by": actor,
                },
            )
            if not obj.activo:
                raise ErrorConflictoImportacion(
                    f"Valor de catálogo {concepto_codigo}.{codigo} existe pero está inactivo."
                )
            if codigo in {"EVAL_NO_ESPECIFICADA", "EVAL_NO_ESPECIFICADO"} and obj.nombre != nombre:
                obj.nombre = nombre
                obj.updated_by = actor
                obj.save(update_fields=["nombre", "updated_by"])
            if creado:
                creados.append(f"{concepto_codigo}.{codigo}")
    return creados


def _cargar_actores(validacion: ResultadoValidacionEscenario) -> dict[str, User]:
    usernames = (
        {c["created_by"] for c in validacion.clientes if c.get("created_by")}
        | {p["vendedor"] for p in validacion.proformas if p.get("vendedor")}
        | {e["actor"] for e in validacion.eventos if e.get("actor")}
        | {o["jefe_taller"] for o in validacion.ordenes_trabajo_objetivo if o.get("jefe_taller")}
    )
    usuarios = {u.username: u for u in User.objects.filter(username__in=usernames)}
    faltantes = sorted(usernames - set(usuarios))
    if faltantes:
        raise ErrorImportacionHomex(
            f"Faltan usuarios comerciales en la base de datos: {', '.join(faltantes)}"
        )
    return usuarios


def _verificar_no_mezcla_versiones(validacion: ResultadoValidacionEscenario) -> None:
    if validacion.version in {"0.6", "0.7"}:
        hay_v05 = Cliente.objects.filter(observaciones__contains="perfil=ESCENARIO").exists()
        if hay_v05:
            raise ErrorConflictoImportacion(
                "No se puede importar v06 sobre una base que contiene marcadores v05."
            )


def _sincronizar_catalogo_escenario(
    validacion: ResultadoValidacionEscenario,
    *,
    actor: User,
) -> dict:
    es_v06 = validacion.version in {"0.6", "0.7"}
    apertura_por_sku = {a["sku"]: a for a in validacion.apertura_stock_esperada}
    productos_payload = []
    mapa_sku_comercial: dict[str, str] = {}
    creados_tot = 0
    existentes_tot = 0
    movs_tot = 0

    for item in validacion.catalogo:
        source_id = item["sku"]
        sku_visible = item.get("sku_comercial") or source_id if es_v06 else source_id
        mapa_sku_comercial[source_id] = sku_visible

        ficha = item.get("ficha")
        if item["categoria"] == "PISO_FLOTANTE" and isinstance(ficha, dict):
            ficha = {
                k: v
                for k, v in ficha.items()
                if k
                in {
                    "marca",
                    "modelo",
                    "tipo",
                    "material",
                    "diseno",
                    "espesor_mm",
                    "acabado",
                    "largo_mm",
                    "ancho_mm",
                    "m2_por_caja",
                }
            }
        elif item["categoria"] == "OTRO":
            ficha = None

        obs = (
            item.get("observaciones")
            if es_v06
            else (
                f"[HOMEX_IMPORT perfil=ESCENARIO sku_fuente={item.get('sku_fuente')} "
                "naturaleza=SIMULADO_NO_RESULTADO_MEDIDO]"
            )
        )

        productos_payload.append(
            {
                "sku": sku_visible,
                "categoria": item["categoria"],
                "nombre": item["nombre"],
                "unidad_stock": item["unidad_stock"],
                "modalidad_abastecimiento": item["modalidad_abastecimiento"],
                "precio_lista": item["precio_lista"],
                "stock_inicial": item["stock_inicial"],
                "activo": True,
                "observaciones": obs,
                "ficha": ficha,
            }
        )

    try:
        for item_payload in productos_payload:
            source_id = next(
                it["sku"]
                for it in validacion.catalogo
                if (it.get("sku_comercial") or it["sku"] if es_v06 else it["sku"])
                == item_payload["sku"]
            )
            ap = apertura_por_sku.get(source_id) if es_v06 else None
            if ap is not None:
                dt_ap = parsear_fecha_hora(
                    ap["fecha_hora_simulada"], f"{ap['id']}.fecha_hora_simulada"
                )
                with reloj_comercial_simulado(dt_ap.date(), fecha_hora=dt_ap):
                    res_item = importar_catalogo(
                        datos={"schema_version": 1, "productos": [item_payload]},
                        actor=actor,
                        dry_run=False,
                    )
            else:
                res_item = importar_catalogo(
                    datos={"schema_version": 1, "productos": [item_payload]},
                    actor=actor,
                    dry_run=False,
                )
            creados_tot += res_item.creados
            existentes_tot += res_item.existentes
            movs_tot += res_item.movimientos_stock
    except ErrorCatalogo as exc:
        raise ErrorImportacionHomex(f"Error al importar catálogo escenario: {exc}") from exc

    productos_por_source: dict[str, Producto] = {}
    for item in validacion.catalogo:
        source_id = item["sku"]
        sku_visible = mapa_sku_comercial[source_id]
        prod = Producto.objects.get(sku=sku_visible)
        productos_por_source[source_id] = prod
        if es_v06:
            _registrar_procedencia(
                entidad="PRODUCTO",
                source_id=source_id,
                objeto_id=prod.id,
                naturaleza=item.get("naturaleza", "SIMULADO_NO_RESULTADO_MEDIDO"),
                payload_hash=_hash_payload(item),
                metadatos={
                    "sku_comercial": sku_visible,
                    "sku_fuente": item.get("sku_fuente"),
                    "referencias": item.get("referencias", []),
                    "criterio_stock": item.get("criterio_stock"),
                },
            )
            ap = apertura_por_sku.get(source_id)
            if ap:
                dt_ap = parsear_fecha_hora(
                    ap["fecha_hora_simulada"], f"{ap['id']}.fecha_hora_simulada"
                )
                mov = MovimientoStock.objects.filter(
                    producto=prod, tipo_movimiento__codigo="CARGA_INICIAL"
                ).first()
                if mov is not None:
                    _registrar_procedencia(
                        entidad="MOVIMIENTO_STOCK",
                        source_id=ap["id"],
                        objeto_id=mov.id,
                        naturaleza=ap.get("naturaleza", "SIMULADO_NO_RESULTADO_MEDIDO"),
                        payload_hash=_hash_payload(ap),
                        fecha_hora_comercial=dt_ap,
                        metadatos={"sku": source_id, "tipo": "CARGA_INICIAL"},
                    )

    return {
        "creados": creados_tot,
        "existentes": existentes_tot,
        "movimientos_stock": movs_tot,
        "productos_por_source": productos_por_source,
    }


def _sincronizar_imagenes_escenario(
    validacion: ResultadoValidacionEscenario,
    *,
    paquete: PaqueteMaestroHomex | None,
    productos_por_source: dict[str, Producto],
    actor: User,
    rutas_subidas: list[str] | None = None,
) -> tuple[dict, list[str]]:
    if validacion.version not in {"0.6", "0.7"}:
        return {"asignadas": 0, "idempotentes": 0, "pendientes_omitidas": 0}, []

    if paquete is None:
        raise ErrorImportacionHomex("El paquete v06 requiere acceso al ZIP para adjuntar imágenes.")

    asignadas = 0
    idempotentes = 0
    pendientes_omitidas = 0
    if rutas_subidas is None:
        rutas_subidas = []

    for entry in validacion.asociaciones_imagenes:
        if entry.get("asignacion_automatica_propuesta") is not True:
            pendientes_omitidas += 1
            continue

        sku_esc = entry["sku_escenario"]
        prod = productos_por_source.get(sku_esc)
        if prod is None:
            raise ErrorImportacionHomex(
                f"Imagen referencia SKU inexistente en escenario: {sku_esc}"
            )

        sha_esp = entry["sha256"]
        existente = prod.imagenes.filter(principal=True, sha256=sha_esp).first()
        if existente is not None:
            idempotentes += 1
            continue

        ruta_paquete = entry["ruta_paquete"]
        contenido = paquete.leer_bytes(ruta_paquete)
        nombre_archivo = Path(ruta_paquete).name
        ext = Path(nombre_archivo).suffix.lower()
        content_type = "image/jpeg" if ext in {".jpg", ".jpeg"} else "image/png"
        archivo = SimpleUploadedFile(nombre_archivo, contenido, content_type=content_type)

        prod = reemplazar_imagen_principal(producto=prod, archivo=archivo, actor=actor)
        img_obj = prod.imagenes.filter(principal=True).first()
        if img_obj is not None:
            ImagenProducto.objects.filter(pk=img_obj.pk).update(sha256=sha_esp)
            if img_obj.ruta_storage:
                rutas_subidas.append(img_obj.ruta_storage)
            for v_ruta in (img_obj.variantes or {}).values():
                if v_ruta:
                    rutas_subidas.append(v_ruta)
            _registrar_procedencia(
                entidad="IMAGEN_PRODUCTO",
                source_id=f"{sku_esc}:{sha_esp[:12]}",
                objeto_id=img_obj.id,
                naturaleza="SIMULADO_NO_RESULTADO_MEDIDO",
                payload_hash=_hash_payload(entry),
                metadatos={
                    "sku_escenario": sku_esc,
                    "estado": entry.get("estado"),
                    "nota": entry.get("nota"),
                    "sha256": sha_esp,
                },
            )
        asignadas += 1

    return {
        "asignadas": asignadas,
        "idempotentes": idempotentes,
        "pendientes_omitidas": pendientes_omitidas,
    }, rutas_subidas


def _limpiar_media_subida(rutas: list[str]) -> None:
    for ruta in rutas:
        try:
            if ruta and default_storage.exists(ruta):
                default_storage.delete(ruta)
        except OSError:
            pass


def _sincronizar_clientes_escenario(
    validacion: ResultadoValidacionEscenario,
    *,
    usuarios: dict[str, User],
) -> dict:
    es_v06 = validacion.version in {"0.6", "0.7"}
    clientes_map: dict[str, Cliente] = {}
    creados = 0
    existentes = 0

    for item in validacion.clientes:
        cid = item["id"]
        tipo = valor_catalogo("TIPO_CLIENTE", item["tipo_cliente"])
        actor = usuarios[item["created_by"]]
        p_hash = _hash_payload(item)

        if es_v06:
            proc = RegistroProcedenciaImportacion.objects.filter(
                perfil="ESCENARIO", entidad="CLIENTE", source_id=cid
            ).first()
            existente = Cliente.objects.filter(pk=proc.objeto_id).first() if proc else None
            if proc and existente is None:
                raise ErrorConflictoImportacion(
                    f"Procedencia de cliente {cid} apunta a id inexistente {proc.objeto_id}."
                )
            if proc and proc.payload_hash != p_hash:
                raise ErrorConflictoImportacion(f"Conflicto de idempotencia en cliente {cid}.")
            obs_cliente = item.get("observaciones")
        else:
            marcador = _marcador_cliente_v05(cid)
            existente = Cliente.objects.filter(observaciones__contains=marcador).first()
            obs_cliente = marcador

        if existente is not None:
            coincide = (
                existente.tipo_cliente_id == tipo.id
                and (existente.nombres or None) == item.get("nombres")
                and (existente.apellidos or None) == item.get("apellidos")
                and (existente.empresa or None) == item.get("empresa")
            )
            if not coincide:
                raise ErrorConflictoImportacion(f"Cliente {cid} ya existe con atributos distintos.")
            clientes_map[cid] = existente
            existentes += 1
            continue

        cliente = crear_cliente(
            actor=actor,
            tipo_cliente=tipo,
            nombres=item.get("nombres"),
            apellidos=item.get("apellidos"),
            empresa=item.get("empresa"),
            celular=item.get("celular"),
            direccion=item.get("direccion"),
            observaciones=obs_cliente,
        )
        if es_v06:
            _registrar_procedencia(
                entidad="CLIENTE",
                source_id=cid,
                objeto_id=cliente.id,
                naturaleza=item.get("naturaleza", "SIMULADO_NO_RESULTADO_MEDIDO"),
                payload_hash=p_hash,
            )
        clientes_map[cid] = cliente
        creados += 1

    return {"mapa": clientes_map, "creados": creados, "existentes": existentes}


def _crear_proforma_escenario(
    *,
    pf_data: dict,
    cliente: Cliente,
    actor: User,
    productos_por_source: dict[str, Producto],
    es_v06: bool,
    fecha_hora_ev: datetime | None,
) -> tuple[Proforma, bool]:
    clave = clave_idempotencia_escenario("PROFORMA", pf_data["id"])
    req_hash = _hash_payload(pf_data)
    existente = Proforma.objects.select_related("estado").filter(clave_idempotencia=clave).first()
    if existente is not None:
        if existente.idempotencia_hash != req_hash or existente.vendedor_id != actor.id:
            raise ErrorConflictoImportacion(
                f"Conflicto de idempotencia en proforma {pf_data['id']}."
            )
        return existente, True

    obs = (
        pf_data.get("observaciones")
        if es_v06
        else _marcador_proforma_v05(pf_data["id"], pf_data.get("observaciones"))
    )

    proforma = crear_proforma(
        actor=actor,
        moneda_codigo=pf_data.get("moneda", "BOB"),
        cliente=cliente,
        titulo=pf_data.get("titulo"),
        plazo_entrega=pf_data.get("plazo_entrega"),
        validez_oferta=pf_data.get("validez_oferta"),
        porcentaje_adelanto=parsear_decimal(
            pf_data["porcentaje_adelanto"], f"{pf_data['id']}.porcentaje_adelanto"
        )
        if pf_data.get("porcentaje_adelanto") is not None
        else None,
        observaciones=obs,
        clave_idempotencia=clave,
        idempotencia_hash=req_hash,
    )

    for linea in pf_data["lineas"]:
        tipo_item = valor_catalogo("TIPO_ITEM", linea["tipo_item"])
        unidad = valor_catalogo("UNIDAD_MEDIDA", linea["unidad"])
        sku_ref = linea.get("sku")
        producto = productos_por_source[sku_ref] if sku_ref else None
        datos_detalle = {
            "tipo_item": tipo_item,
            "producto": producto,
            "nombre": linea["nombre"],
            "descripcion": linea.get("descripcion"),
            "cantidad": parsear_decimal(linea["cantidad"], f"{pf_data['id']}.cantidad"),
            "unidad": unidad,
            "modo_calculo": linea.get("modo_calculo", "PRECIO_UNITARIO"),
            "precio_unitario": parsear_decimal(
                linea["precio_unitario"], f"{pf_data['id']}.precio_unitario"
            ),
            "descuento": parsear_decimal(
                linea.get("descuento", "0.00"), f"{pf_data['id']}.descuento"
            ),
        }
        detalle = agregar_detalle(proforma_id=proforma.id, actor=actor, **datos_detalle)

        espec = linea.get("especificacion")
        if espec:
            tipo_mueble = (
                valor_catalogo("TIPO_MUEBLE", espec["tipo_mueble"])
                if espec.get("tipo_mueble")
                else None
            )
            crear_especificacion(
                detalle_id=detalle.id,
                actor=actor,
                tipo_mueble=tipo_mueble,
                datos_tecnicos=espec.get("datos_tecnicos") or {},
                observaciones=espec.get("observaciones"),
            )

    proforma.refresh_from_db()
    if proforma.total != parsear_decimal(pf_data["total"], f"{pf_data['id']}.total"):
        raise ErrorImportacionHomex(
            f"Total recalculado por PostgreSQL difiere en {pf_data['id']}: "
            f"{proforma.total} != {pf_data['total']}"
        )
    if es_v06:
        _registrar_procedencia(
            entidad="PROFORMA",
            source_id=pf_data["id"],
            objeto_id=proforma.id,
            naturaleza=pf_data.get("naturaleza", "SIMULADO_NO_RESULTADO_MEDIDO"),
            payload_hash=req_hash,
            fecha_hora_comercial=fecha_hora_ev,
            metadatos={"mes_cohorte": pf_data.get("mes_cohorte")},
        )
    return proforma, False


def ejecutar_escenario(
    validacion: ResultadoValidacionEscenario,
    *,
    actor_admin: User,
    fecha_corte: date,
    simular_reloj_virtual: bool,
    dry_run: bool = True,
    paquete: PaqueteMaestroHomex | None = None,
) -> dict:
    """Ejecuta el escenario completo en orden de dependencias y cronológico."""
    rutas_media_subidas: list[str] = []
    try:
        with transaction.atomic():
            _verificar_no_mezcla_versiones(validacion)
            es_v06 = validacion.version in {"0.6", "0.7"}
            fecha_real_hoy = timezone.localdate()
            usuarios = _cargar_actores(validacion)
            catalogos_creados = _asegurar_catalogos_tecnicos(actor_admin)
            resumen_catalogo = _sincronizar_catalogo_escenario(validacion, actor=actor_admin)
            productos_por_source: dict[str, Producto] = resumen_catalogo.pop("productos_por_source")

            resumen_imagenes, _ = _sincronizar_imagenes_escenario(
                validacion,
                paquete=paquete,
                productos_por_source=productos_por_source,
                actor=actor_admin,
                rutas_subidas=rutas_media_subidas,
            )
            resumen_clientes = _sincronizar_clientes_escenario(validacion, usuarios=usuarios)
            clientes_map: dict[str, Cliente] = resumen_clientes["mapa"]

            proformas_por_id = {p["id"]: p for p in validacion.proformas}
            pedidos_obj_por_id = {p["id"]: p for p in validacion.pedidos_objetivo}
            recibos_por_id = {r["id"]: r for r in validacion.recibos_objetivo}
            ots_objetivo_por_pedido = {
                o["pedido_id"]: o for o in validacion.ordenes_trabajo_objetivo
            }

            proformas_inst: dict[str, Proforma] = {}
            pedidos_inst: dict[str, Pedido] = {}
            eventos_ejecutados = 0
            eventos_idempotentes = 0
            eventos_excluidos_corte = 0
            tz_local = ZoneInfo(settings.TIME_ZONE)

            for ev in validacion.eventos:
                fecha_ev = parsear_fecha(ev["fecha"], f"{ev['id']}.fecha")
                if fecha_ev > fecha_corte:
                    eventos_excluidos_corte += 1
                    continue

                es_futuro = fecha_ev > fecha_real_hoy or ev.get("posterior_a_fecha_preparacion")
                if es_futuro and not simular_reloj_virtual:
                    raise ErrorImportacionHomex(
                        f"El evento {ev['id']} ({fecha_ev}) es posterior a la fecha actual "
                        f"({fecha_real_hoy}); requiere --simular-reloj-virtual."
                    )

                fecha_hora_ev = (
                    parsear_fecha_hora(ev["fecha_hora_simulada"], f"{ev['id']}.fecha_hora_simulada")
                    if ev.get("fecha_hora_simulada")
                    else datetime.combine(fecha_ev, time(12, 0), tzinfo=tz_local)
                )

                pf_id = ev["proforma_id"]
                pf_data = proformas_por_id[pf_id]
                tipo = ev["tipo"]
                actor = usuarios[ev["actor"]] if ev.get("actor") else actor_admin

                with reloj_comercial_simulado(fecha_ev, fecha_hora=fecha_hora_ev):
                    if tipo == "CREAR_BORRADOR":
                        proforma, ya_existia = _crear_proforma_escenario(
                            pf_data=pf_data,
                            cliente=clientes_map[pf_data["cliente_id"]],
                            actor=actor,
                            productos_por_source=productos_por_source,
                            es_v06=es_v06,
                            fecha_hora_ev=fecha_hora_ev,
                        )
                        proformas_inst[pf_id] = proforma
                        if ya_existia:
                            eventos_idempotentes += 1
                            pedido_existente = (
                                Pedido.objects.select_related("estado")
                                .filter(proforma=proforma)
                                .first()
                            )
                            if pedido_existente is not None:
                                pedidos_inst[f"PF:{pf_id}"] = pedido_existente
                        else:
                            eventos_ejecutados += 1
                        continue

                    proforma = proformas_inst.get(pf_id)
                    if proforma is None:
                        raise ErrorImportacionHomex(
                            f"Evento {ev['id']} ({tipo}) ejecutado antes de "
                            f"CREAR_BORRADOR de {pf_id}."
                        )
                    proforma.refresh_from_db()

                    if tipo == "ENVIAR_PROFORMA":
                        if proforma.estado.codigo in ESTADOS_PROFORMA_POST_BORRADOR:
                            eventos_idempotentes += 1
                        else:
                            proformas_inst[pf_id] = enviar_proforma(
                                proforma_id=proforma.id, actor=actor
                            )
                            eventos_ejecutados += 1

                    elif tipo == "ANULAR_PROFORMA":
                        if proforma.estado.codigo == "ANULADA":
                            eventos_idempotentes += 1
                        else:
                            proformas_inst[pf_id] = anular_proforma(
                                proforma_id=proforma.id, actor=actor
                            )
                            eventos_ejecutados += 1

                    elif tipo == "MARCAR_NO_CONCRETADA":
                        if proforma.estado.codigo == "NO_CONCRETADA":
                            eventos_idempotentes += 1
                        else:
                            proformas_inst[pf_id] = marcar_no_concretada(
                                proforma_id=proforma.id, actor=actor
                            )
                            eventos_ejecutados += 1

                    elif tipo == "VENCER_PROFORMA":
                        if proforma.estado.codigo == "VENCIDA":
                            eventos_idempotentes += 1
                        else:
                            if proforma.estado.codigo != "EN_REVISION":
                                raise ErrorConflictoImportacion(
                                    f"VENCER_PROFORMA {ev['id']} sobre estado "
                                    f"{proforma.estado.codigo}."
                                )
                            if not esta_vencida(
                                proforma.fecha, proforma.validez_oferta, fecha_comercial_actual()
                            ):
                                raise ErrorConflictoImportacion(
                                    f"Proforma {pf_id} aún no vencida al {fecha_ev}."
                                )
                            estado_anterior = proforma.estado
                            proforma.estado = valor_catalogo("ESTADO_PROFORMA", "VENCIDA")
                            proforma.ultima_actividad_comercial = fecha_hora_ev
                            proforma.save(update_fields=["estado", "ultima_actividad_comercial"])
                            from apps.proformas.services import registrar_historial_estado_proforma

                            registrar_historial_estado_proforma(
                                proforma=proforma,
                                estado_anterior=estado_anterior,
                                estado_nuevo=proforma.estado,
                                actor=None,
                                es_automatico=True,
                                origen="IMPORTACION",
                                fecha=fecha_hora_ev,
                                observaciones="Vencimiento registrado durante importación.",
                            )
                            eventos_ejecutados += 1

                    elif tipo == "APROBAR_PROFORMA":
                        ped_id_fuente = ev["pedido_id"]
                        if proforma.estado.codigo == "APROBADA":
                            pedido = Pedido.objects.select_related("estado").get(proforma=proforma)
                            pedidos_inst[ped_id_fuente] = pedido
                            eventos_idempotentes += 1
                        else:
                            pedido = aprobar_proforma(
                                proforma_id=proforma.id,
                                actor=actor,
                                exigir_contacto_cliente=validacion.version
                                not in {"0.4", "0.5", "0.6"},
                            )
                            ot = OrdenTrabajo.objects.get(pedido=pedido)
                            ot_updates: dict = {"fecha": fecha_ev}
                            ped_obj = pedidos_obj_por_id.get(ped_id_fuente)
                            if ped_obj and ped_obj.get("fecha_entrega_programada"):
                                ot_updates["fecha_entrega"] = parsear_fecha(
                                    ped_obj["fecha_entrega_programada"],
                                    f"{ped_id_fuente}.fecha_entrega_programada",
                                )
                            ot_obj = ots_objetivo_por_pedido.get(ped_id_fuente)
                            if ot_obj and ot_obj.get("jefe_taller"):
                                ot_updates["jefe_taller"] = usuarios[ot_obj["jefe_taller"]]
                            OrdenTrabajo.objects.filter(pk=ot.pk).update(**ot_updates)
                            if es_v06:
                                _registrar_procedencia(
                                    entidad="PEDIDO",
                                    source_id=ped_id_fuente,
                                    objeto_id=pedido.id,
                                    naturaleza=ev.get("naturaleza", "SIMULADO_NO_RESULTADO_MEDIDO"),
                                    payload_hash=_hash_payload(
                                        ped_obj or {"pedido_id": ped_id_fuente}
                                    ),
                                    fecha_hora_comercial=fecha_hora_ev,
                                )
                                _registrar_procedencia(
                                    entidad="ORDEN_TRABAJO",
                                    source_id=ped_id_fuente,
                                    objeto_id=ot.id,
                                    naturaleza=ev.get("naturaleza", "SIMULADO_NO_RESULTADO_MEDIDO"),
                                    payload_hash=_hash_payload(
                                        ot_obj or {"pedido_id": ped_id_fuente}
                                    ),
                                    fecha_hora_comercial=fecha_hora_ev,
                                )
                            pedido.refresh_from_db()
                            pedidos_inst[ped_id_fuente] = pedido
                            eventos_ejecutados += 1

                    elif tipo == "EMITIR_RECIBO":
                        ped_id_fuente = ev["pedido_id"]
                        pedido = pedidos_inst.get(ped_id_fuente) or Pedido.objects.get(
                            proforma=proforma
                        )
                        rec_data = recibos_por_id[ev["recibo_id"]]
                        cli = proforma.cliente
                        nombre_pagador = (
                            cli.empresa
                            if cli.tipo_cliente.codigo == "EMPRESA" and cli.empresa
                            else f"{cli.nombres or ''} {cli.apellidos or ''}".strip()
                        )
                        pago_actual = parsear_decimal(
                            rec_data["pago_actual"], f"{ev['recibo_id']}.pago_actual"
                        )
                        recibo_obj, ya_existia = emitir_recibo_idempotente(
                            pedido=pedido,
                            actor=actor,
                            clave_idempotencia=clave_idempotencia_escenario(
                                "RECIBO", ev["recibo_id"]
                            ),
                            nombre_completo=nombre_pagador,
                            monto_en_letras=monto_a_letras_bob(pago_actual),
                            concepto=rec_data["concepto"],
                            tipo_pago=valor_catalogo("TIPO_PAGO", rec_data["tipo_pago"]),
                            pago_actual=pago_actual,
                        )
                        if es_v06 and not ya_existia:
                            _registrar_procedencia(
                                entidad="RECIBO",
                                source_id=ev["recibo_id"],
                                objeto_id=recibo_obj.id,
                                naturaleza=ev.get("naturaleza", "SIMULADO_NO_RESULTADO_MEDIDO"),
                                payload_hash=_hash_payload(rec_data),
                                fecha_hora_comercial=fecha_hora_ev,
                            )
                        if ya_existia:
                            eventos_idempotentes += 1
                        else:
                            eventos_ejecutados += 1

                    elif tipo in {"INICIAR_OT", "TERMINAR_OT"}:
                        ped_id_fuente = ev["pedido_id"]
                        pedido = pedidos_inst.get(ped_id_fuente) or Pedido.objects.select_related(
                            "estado"
                        ).get(proforma=proforma)
                        ot = (
                            OrdenTrabajo.objects.filter(pedido=pedido)
                            .select_related("estado")
                            .first()
                        )
                        if ot is None:
                            eventos_idempotentes += 1
                        else:
                            if tipo == "INICIAR_OT":
                                if ot.estado.codigo in {"EN_PROCESO", "TERMINADA"}:
                                    eventos_idempotentes += 1
                                else:
                                    cambiar_estado_orden_trabajo(
                                        orden_trabajo_id=ot.id,
                                        actor=actor,
                                        estado_codigo="EN_PROCESO",
                                    )
                                    pedido.refresh_from_db()
                                    pedidos_inst[ped_id_fuente] = pedido
                                    eventos_ejecutados += 1
                            else:
                                if ot.estado.codigo == "TERMINADA":
                                    eventos_idempotentes += 1
                                else:
                                    cambiar_estado_orden_trabajo(
                                        orden_trabajo_id=ot.id,
                                        actor=actor,
                                        estado_codigo="TERMINADA",
                                    )
                                    pedido.refresh_from_db()
                                    pedidos_inst[ped_id_fuente] = pedido
                                    eventos_ejecutados += 1

                    elif tipo in {"EN_PRODUCCION", "LISTO_ENTREGA", "ENTREGADO"}:
                        ped_id_fuente = ev["pedido_id"]
                        pedido = pedidos_inst.get(ped_id_fuente) or Pedido.objects.select_related(
                            "estado"
                        ).get(proforma=proforma)
                        pedido.refresh_from_db()
                        orden_estados = [
                            "CONFIRMADO",
                            "EN_PRODUCCION",
                            "LISTO_ENTREGA",
                            "ENTREGADO",
                        ]
                        if pedido.estado.codigo in orden_estados and orden_estados.index(
                            pedido.estado.codigo
                        ) >= orden_estados.index(tipo):
                            eventos_idempotentes += 1
                        else:
                            if tipo == "EN_PRODUCCION":
                                ot_pend = (
                                    OrdenTrabajo.objects.filter(pedido=pedido)
                                    .exclude(estado__codigo__in=["TERMINADA", "CANCELADA"])
                                    .select_related("estado")
                                    .first()
                                )
                                tiene_muebles = pedido.proforma.detalles.filter(
                                    tipo_item__codigo="MUEBLE_MEDIDA"
                                ).exists()
                                if (
                                    validacion.version in {"0.4", "0.5", "0.6"}
                                    and ot_pend is not None
                                    and tiene_muebles
                                ):
                                    actor_taller = (
                                        actor
                                        if puede_cambiar_estado_orden_trabajo(actor)
                                        else (
                                            usuarios.get("antonio.flores")
                                            or next(
                                                (
                                                    u
                                                    for u in usuarios.values()
                                                    if puede_cambiar_estado_orden_trabajo(u)
                                                ),
                                                actor,
                                            )
                                        )
                                    )
                                    if ot_pend.estado.codigo == "PENDIENTE":
                                        cambiar_estado_orden_trabajo(
                                            orden_trabajo_id=ot_pend.id,
                                            actor=actor_taller,
                                            estado_codigo="EN_PROCESO",
                                        )
                                    pedido.refresh_from_db()
                                else:
                                    pedido = cambiar_estado_pedido(
                                        pedido_id=pedido.id,
                                        actor=actor,
                                        estado_codigo="EN_PRODUCCION",
                                    )
                            else:
                                if tipo == "LISTO_ENTREGA" and validacion.version in {
                                    "0.4",
                                    "0.5",
                                    "0.6",
                                }:
                                    ot_pend = (
                                        OrdenTrabajo.objects.filter(pedido=pedido)
                                        .exclude(estado__codigo__in=["TERMINADA", "CANCELADA"])
                                        .select_related("estado")
                                        .first()
                                    )
                                    if ot_pend is not None:
                                        tiene_muebles = pedido.proforma.detalles.filter(
                                            tipo_item__codigo="MUEBLE_MEDIDA"
                                        ).exists()
                                        if tiene_muebles:
                                            actor_taller = (
                                                actor
                                                if puede_cambiar_estado_orden_trabajo(actor)
                                                else (
                                                    usuarios.get("antonio.flores")
                                                    or next(
                                                        (
                                                            u
                                                            for u in usuarios.values()
                                                            if puede_cambiar_estado_orden_trabajo(u)
                                                        ),
                                                        actor,
                                                    )
                                                )
                                            )
                                            if ot_pend.estado.codigo == "PENDIENTE":
                                                cambiar_estado_orden_trabajo(
                                                    orden_trabajo_id=ot_pend.id,
                                                    actor=actor_taller,
                                                    estado_codigo="EN_PROCESO",
                                                )
                                            cambiar_estado_orden_trabajo(
                                                orden_trabajo_id=ot_pend.id,
                                                actor=actor_taller,
                                                estado_codigo="TERMINADA",
                                            )
                                pedido = cambiar_estado_pedido(
                                    pedido_id=pedido.id,
                                    actor=actor,
                                    estado_codigo=tipo,
                                )
                            if es_v06 and tipo == "LISTO_ENTREGA":
                                nota = NotaEntrega.objects.filter(pedido=pedido).first()
                                if nota is not None:
                                    _registrar_procedencia(
                                        entidad="NOTA_ENTREGA",
                                        source_id=ped_id_fuente,
                                        objeto_id=nota.id,
                                        naturaleza=ev.get(
                                            "naturaleza", "SIMULADO_NO_RESULTADO_MEDIDO"
                                        ),
                                        payload_hash=_hash_payload(
                                            {"pedido_id": ped_id_fuente, "fecha": ev["fecha"]}
                                        ),
                                        fecha_hora_comercial=fecha_hora_ev,
                                    )
                            pedidos_inst[ped_id_fuente] = pedido
                            eventos_ejecutados += 1

                    elif tipo == "CANCELAR_PEDIDO":
                        ped_id_fuente = ev["pedido_id"]
                        pedido = pedidos_inst.get(ped_id_fuente) or Pedido.objects.select_related(
                            "estado"
                        ).get(proforma=proforma)
                        pedido.refresh_from_db()
                        if pedido.estado.codigo == "CANCELADO":
                            eventos_idempotentes += 1
                        else:
                            pedido = cancelar_pedido(pedido_id=pedido.id, actor=actor)
                            pedidos_inst[ped_id_fuente] = pedido
                            eventos_ejecutados += 1

            auditoria = auditar_escenario(validacion, fecha_corte=fecha_corte)

            resultado = {
                "version_escenario": validacion.version,
                "modo": "DRY_RUN" if dry_run else "PERSISTENTE",
                "fecha_corte": fecha_corte.isoformat(),
                "simular_reloj_virtual": simular_reloj_virtual,
                "catalogos_tecnicos_creados": catalogos_creados,
                "catalogo": resumen_catalogo,
                "imagenes": resumen_imagenes,
                "clientes": {
                    "creados": resumen_clientes["creados"],
                    "existentes": resumen_clientes["existentes"],
                },
                "eventos": {
                    "ejecutados": eventos_ejecutados,
                    "idempotentes": eventos_idempotentes,
                    "excluidos_por_corte": eventos_excluidos_corte,
                },
                "auditoria": auditoria,
            }

            if dry_run:
                transaction.set_rollback(True)

            if not auditoria["conforme"]:
                raise ErrorConciliacionImportacion(
                    f"Conciliación con discrepancias: {auditoria['discrepancias']}",
                    reporte=resultado,
                )

        if dry_run:
            _limpiar_media_subida(rutas_media_subidas)

        return resultado
    except Exception:
        _limpiar_media_subida(rutas_media_subidas)
        raise
