from django.db import migrations


def recuperar_historial_pedidos(apps, schema_editor):
    Pedido = apps.get_model("pedidos", "Pedido")
    HistorialEstadoPedido = apps.get_model("pedidos", "HistorialEstadoPedido")
    ValorCatalogo = apps.get_model("catalogo", "ValorCatalogo")
    RegistroProcedenciaImportacion = apps.get_model("proformas", "RegistroProcedenciaImportacion")

    confirmado = ValorCatalogo.objects.filter(
        concepto__codigo="ESTADO_PEDIDO", codigo="CONFIRMADO"
    ).first()
    procedencias = {
        proc.objeto_id: proc
        for proc in RegistroProcedenciaImportacion.objects.filter(entidad="PEDIDO")
    }

    for pedido in Pedido.objects.select_related(
        "estado", "proforma__vendedor", "created_by", "updated_by"
    ).iterator():
        if HistorialEstadoPedido.objects.filter(pedido=pedido).exists():
            continue
        proc = procedencias.get(pedido.id)
        origen = "IMPORTACION" if proc else "RECUPERACION"
        actor_inicial = pedido.created_by or (pedido.proforma.vendedor if pedido.proforma else None)
        if confirmado is not None and pedido.fecha_confirmacion is not None:
            HistorialEstadoPedido.objects.create(
                pedido=pedido,
                estado_anterior=None,
                estado_nuevo=confirmado,
                cambiado_por=actor_inicial,
                es_automatico=False,
                origen=origen,
                fecha=pedido.fecha_confirmacion,
                observaciones=(
                    "Confirmación recuperada desde evidencia persistida."
                    if pedido.estado_id != confirmado.id
                    else None
                ),
            )
        if confirmado is None or pedido.estado_id != confirmado.id:
            fecha_actual = proc.fecha_hora_comercial if proc else None
            if fecha_actual is not None:
                HistorialEstadoPedido.objects.create(
                    pedido=pedido,
                    estado_anterior=confirmado if confirmado is not None else None,
                    estado_nuevo=pedido.estado,
                    cambiado_por=pedido.updated_by or actor_inicial,
                    es_automatico=False,
                    origen="RECUPERACION",
                    fecha=fecha_actual,
                    observaciones="Estado actual recuperado desde evidencia persistida (historial previo incompleto).",
                )


class Migration(migrations.Migration):
    dependencies = [
        ("pedidos", "0003_historialestadopedido"),
        ("proformas", "0017_historialestadoproforma"),
    ]

    operations = [
        migrations.RunPython(recuperar_historial_pedidos, migrations.RunPython.noop),
    ]
