from django.db import migrations


def recuperar_historial_proformas(apps, schema_editor):
    Proforma = apps.get_model("proformas", "Proforma")
    HistorialEstadoProforma = apps.get_model("proformas", "HistorialEstadoProforma")
    RegistroProcedenciaImportacion = apps.get_model("proformas", "RegistroProcedenciaImportacion")

    procedencias = {
        proc.objeto_id: proc
        for proc in RegistroProcedenciaImportacion.objects.filter(entidad="PROFORMA")
    }

    for proforma in Proforma.objects.select_related("estado", "vendedor", "created_by", "updated_by").iterator():
        if HistorialEstadoProforma.objects.filter(proforma=proforma).exists():
            continue
        proc = procedencias.get(proforma.id)
        fecha_evidencia = (
            proforma.ultima_actividad_comercial
            or (proc.fecha_hora_comercial if proc else None)
            or proforma.actualizado_en
            or proforma.creado_en
        )
        if fecha_evidencia is None:
            continue
        es_borrador = proforma.estado.codigo == "BORRADOR"
        actor = (
            (proforma.created_by or proforma.vendedor)
            if es_borrador
            else (proforma.updated_by or proforma.created_by or proforma.vendedor)
        )
        origen = "IMPORTACION" if proc else "RECUPERACION"
        observaciones = (
            "Registro recuperado desde procedencia de importación."
            if (proc and es_borrador)
            else None
            if es_borrador
            else "Estado actual recuperado desde evidencia persistida (historial previo incompleto)."
        )
        HistorialEstadoProforma.objects.create(
            proforma=proforma,
            estado_anterior=None,
            estado_nuevo=proforma.estado,
            cambiado_por=actor,
            es_automatico=False,
            origen=origen,
            fecha=fecha_evidencia,
            observaciones=observaciones,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("proformas", "0017_historialestadoproforma"),
    ]

    operations = [
        migrations.RunPython(recuperar_historial_proformas, migrations.RunPython.noop),
    ]
