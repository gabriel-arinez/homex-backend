"""Ejecutor transaccional e idempotente del escenario de evaluación HOMEX."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.catalogo.importador import ErrorCatalogo, importar_catalogo
from apps.catalogo.models import ConceptoCatalogo, Producto, ValorCatalogo
from apps.clientes.models import Cliente
from apps.clientes.services import crear_cliente
from apps.core.tiempo_comercial import fecha_comercial_actual, reloj_comercial_simulado
from apps.ordenes_trabajo.models import OrdenTrabajo
from apps.pedidos.models import Pedido
from apps.pedidos.services import aprobar_proforma, cambiar_estado_pedido, cancelar_pedido
from apps.proformas.importador_homex.auditoria import (
    auditar_escenario,
    clave_idempotencia_escenario,
)
from apps.proformas.importador_homex.excepciones import (
    ErrorConflictoImportacion,
    ErrorImportacionHomex,
)
from apps.proformas.importador_homex.monto_letras import monto_a_letras_bob
from apps.proformas.importador_homex.validacion import (
    ResultadoValidacionEscenario,
    parsear_decimal,
    parsear_fecha,
)
from apps.proformas.models import Proforma
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

MARCADORES_CATALOGO_ESCENARIO = {
    "MARCA": [("EVAL_NO_ESPECIFICADA", "Marca no especificada [EVAL]"), ("GANESHA", "Ganesha")],
    "COLOR": [("EVAL_NO_ESPECIFICADO", "Color no especificado [EVAL]")],
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


def _marcador_cliente(source_id: str) -> str:
    return (
        f"[HOMEX_IMPORT perfil=ESCENARIO source_id={source_id} "
        "naturaleza=SIMULADO_NO_RESULTADO_MEDIDO]"
    )


def _marcador_proforma(source_id: str, obs_original: str | None) -> str:
    base = _marcador_cliente(source_id)
    if obs_original:
        return f"{base} {obs_original}"
    return base


def _hash_proforma_escenario(pf_data: dict) -> str:
    payload = json.dumps(pf_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _asegurar_catalogos_tecnicos(actor: User) -> list[str]:
    creados: list[str] = []
    for concepto_codigo, pares in MARCADORES_CATALOGO_ESCENARIO.items():
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


def _sincronizar_catalogo_escenario(
    validacion: ResultadoValidacionEscenario,
    *,
    actor: User,
) -> dict:
    productos_payload = []
    for item in validacion.catalogo:
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
        productos_payload.append(
            {
                "sku": item["sku"],
                "categoria": item["categoria"],
                "nombre": item["nombre"],
                "unidad_stock": item["unidad_stock"],
                "modalidad_abastecimiento": item["modalidad_abastecimiento"],
                "precio_lista": item["precio_lista"],
                "stock_inicial": item["stock_inicial"],
                "activo": True,
                "observaciones": (
                    f"[HOMEX_IMPORT perfil=ESCENARIO sku_fuente={item.get('sku_fuente')} "
                    "naturaleza=SIMULADO_NO_RESULTADO_MEDIDO]"
                ),
                "ficha": ficha,
            }
        )
    try:
        resultado = importar_catalogo(
            datos={"schema_version": 1, "productos": productos_payload},
            actor=actor,
            dry_run=False,
        )
    except ErrorCatalogo as exc:
        raise ErrorImportacionHomex(f"Error al importar catálogo escenario: {exc}") from exc

    return {
        "creados": resultado.creados,
        "existentes": resultado.existentes,
        "movimientos_stock": resultado.movimientos_stock,
    }


def _sincronizar_clientes_escenario(
    validacion: ResultadoValidacionEscenario,
    *,
    usuarios: dict[str, User],
) -> dict[str, Cliente]:
    clientes_map: dict[str, Cliente] = {}
    creados = 0
    existentes = 0

    for item in validacion.clientes:
        cid = item["id"]
        marcador = _marcador_cliente(cid)
        tipo = valor_catalogo("TIPO_CLIENTE", item["tipo_cliente"])
        actor = usuarios[item["created_by"]]
        existente = Cliente.objects.filter(observaciones__contains=marcador).first()
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
            observaciones=marcador,
        )
        clientes_map[cid] = cliente
        creados += 1

    return {"mapa": clientes_map, "creados": creados, "existentes": existentes}


def _crear_proforma_escenario(
    *,
    pf_data: dict,
    cliente: Cliente,
    actor: User,
) -> tuple[Proforma, bool]:
    clave = clave_idempotencia_escenario("PROFORMA", pf_data["id"])
    req_hash = _hash_proforma_escenario(pf_data)
    existente = Proforma.objects.select_related("estado").filter(clave_idempotencia=clave).first()
    if existente is not None:
        if existente.idempotencia_hash != req_hash or existente.vendedor_id != actor.id:
            raise ErrorConflictoImportacion(
                f"Conflicto de idempotencia en proforma {pf_data['id']}."
            )
        return existente, True

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
        observaciones=_marcador_proforma(pf_data["id"], pf_data.get("observaciones")),
        clave_idempotencia=clave,
        idempotencia_hash=req_hash,
    )

    for linea in pf_data["lineas"]:
        tipo_item = valor_catalogo("TIPO_ITEM", linea["tipo_item"])
        unidad = valor_catalogo("UNIDAD_MEDIDA", linea["unidad"])
        producto = Producto.objects.get(sku=linea["sku"]) if linea.get("sku") else None
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
    return proforma, False


@transaction.atomic
def ejecutar_escenario(
    validacion: ResultadoValidacionEscenario,
    *,
    actor_admin: User,
    fecha_corte: date,
    simular_reloj_virtual: bool,
    dry_run: bool = True,
) -> dict:
    """Ejecuta el escenario completo en orden de dependencias y cronológico."""
    fecha_real_hoy = timezone.localdate()
    usuarios = _cargar_actores(validacion)
    catalogos_creados = _asegurar_catalogos_tecnicos(actor_admin)
    resumen_catalogo = _sincronizar_catalogo_escenario(validacion, actor=actor_admin)
    resumen_clientes = _sincronizar_clientes_escenario(validacion, usuarios=usuarios)
    clientes_map: dict[str, Cliente] = resumen_clientes["mapa"]

    proformas_por_id = {p["id"]: p for p in validacion.proformas}
    recibos_por_id = {r["id"]: r for r in validacion.recibos_objetivo}
    ots_objetivo_por_pedido = {o["pedido_id"]: o for o in validacion.ordenes_trabajo_objetivo}

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

        pf_id = ev["proforma_id"]
        pf_data = proformas_por_id[pf_id]
        tipo = ev["tipo"]
        actor = usuarios[ev["actor"]] if ev.get("actor") else actor_admin

        with reloj_comercial_simulado(fecha_ev):
            if tipo == "CREAR_BORRADOR":
                proforma, ya_existia = _crear_proforma_escenario(
                    pf_data=pf_data,
                    cliente=clientes_map[pf_data["cliente_id"]],
                    actor=actor,
                )
                proformas_inst[pf_id] = proforma
                if ya_existia:
                    eventos_idempotentes += 1
                    pedido_existente = (
                        Pedido.objects.select_related("estado").filter(proforma=proforma).first()
                    )
                    if pedido_existente is not None:
                        pedidos_inst[f"PF:{pf_id}"] = pedido_existente
                else:
                    eventos_ejecutados += 1
                continue

            proforma = proformas_inst.get(pf_id)
            if proforma is None:
                raise ErrorImportacionHomex(
                    f"Evento {ev['id']} ({tipo}) ejecutado antes de CREAR_BORRADOR de {pf_id}."
                )
            proforma.refresh_from_db()

            if tipo == "ENVIAR_PROFORMA":
                if proforma.estado.codigo in ESTADOS_PROFORMA_POST_BORRADOR:
                    eventos_idempotentes += 1
                else:
                    proformas_inst[pf_id] = enviar_proforma(proforma_id=proforma.id, actor=actor)
                    eventos_ejecutados += 1

            elif tipo == "ANULAR_PROFORMA":
                if proforma.estado.codigo == "ANULADA":
                    eventos_idempotentes += 1
                else:
                    proformas_inst[pf_id] = anular_proforma(proforma_id=proforma.id, actor=actor)
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
                            f"VENCER_PROFORMA {ev['id']} sobre estado {proforma.estado.codigo}."
                        )
                    if not esta_vencida(
                        proforma.fecha, proforma.validez_oferta, fecha_comercial_actual()
                    ):
                        raise ErrorConflictoImportacion(
                            f"Proforma {pf_id} aún no vencida al {fecha_ev}."
                        )
                    proforma.estado = valor_catalogo("ESTADO_PROFORMA", "VENCIDA")
                    proforma.save(update_fields=["estado"])
                    eventos_ejecutados += 1

            elif tipo == "APROBAR_PROFORMA":
                ped_id_fuente = ev["pedido_id"]
                if proforma.estado.codigo == "APROBADA":
                    pedido = Pedido.objects.select_related("estado").get(proforma=proforma)
                    pedidos_inst[ped_id_fuente] = pedido
                    eventos_idempotentes += 1
                else:
                    pedido = aprobar_proforma(proforma_id=proforma.id, actor=actor)
                    fecha_conf_dt = datetime.combine(fecha_ev, time(12, 0), tzinfo=tz_local)
                    Pedido.objects.filter(pk=pedido.pk).update(fecha_confirmacion=fecha_conf_dt)
                    ot = OrdenTrabajo.objects.get(pedido=pedido)
                    ot_updates = {"fecha": fecha_ev}
                    ot_obj = ots_objetivo_por_pedido.get(ped_id_fuente)
                    if ot_obj and ot_obj.get("jefe_taller"):
                        ot_updates["jefe_taller"] = usuarios[ot_obj["jefe_taller"]]
                    OrdenTrabajo.objects.filter(pk=ot.pk).update(**ot_updates)
                    pedido.refresh_from_db()
                    pedidos_inst[ped_id_fuente] = pedido
                    eventos_ejecutados += 1

            elif tipo == "EMITIR_RECIBO":
                ped_id_fuente = ev["pedido_id"]
                pedido = pedidos_inst.get(ped_id_fuente) or Pedido.objects.get(proforma=proforma)
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
                _, ya_existia = emitir_recibo_idempotente(
                    pedido=pedido,
                    actor=actor,
                    clave_idempotencia=clave_idempotencia_escenario("RECIBO", ev["recibo_id"]),
                    nombre_completo=nombre_pagador,
                    monto_en_letras=monto_a_letras_bob(pago_actual),
                    concepto=rec_data["concepto"],
                    tipo_pago=valor_catalogo("TIPO_PAGO", rec_data["tipo_pago"]),
                    pago_actual=pago_actual,
                )
                if ya_existia:
                    eventos_idempotentes += 1
                else:
                    eventos_ejecutados += 1

            elif tipo in {"EN_PRODUCCION", "LISTO_ENTREGA", "ENTREGADO"}:
                ped_id_fuente = ev["pedido_id"]
                pedido = pedidos_inst.get(ped_id_fuente) or Pedido.objects.select_related(
                    "estado"
                ).get(proforma=proforma)
                pedido.refresh_from_db()
                orden_estados = ["CONFIRMADO", "EN_PRODUCCION", "LISTO_ENTREGA", "ENTREGADO"]
                if pedido.estado.codigo in orden_estados and orden_estados.index(
                    pedido.estado.codigo
                ) >= orden_estados.index(tipo):
                    eventos_idempotentes += 1
                else:
                    pedido = cambiar_estado_pedido(
                        pedido_id=pedido.id,
                        actor=actor,
                        estado_codigo=tipo,
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

    if dry_run:
        transaction.set_rollback(True)

    return {
        "modo": "DRY_RUN" if dry_run else "PERSISTENTE",
        "fecha_corte": fecha_corte.isoformat(),
        "simular_reloj_virtual": simular_reloj_virtual,
        "catalogos_tecnicos_creados": catalogos_creados,
        "catalogo": resumen_catalogo,
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
