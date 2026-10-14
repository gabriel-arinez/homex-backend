import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_ap6021_migra_especificacion_heredada_sin_perder_informacion():
    executor = MigrationExecutor(connection)
    origen = [("proformas", "0008_ap6_caja_historica_stock")]
    destino = [("proformas", "0009_datos_tecnicos_unicos_ap6021")]
    executor.migrate(origen)
    apps = executor.loader.project_state(origen).apps

    Valor = apps.get_model("catalogo", "ValorCatalogo")
    Proforma = apps.get_model("proformas", "Proforma")
    Detalle = apps.get_model("proformas", "DetalleProforma")
    Especificacion = apps.get_model("proformas", "EspecificacionMueble")
    Usuario = apps.get_model("accounts", "User")

    def valor(concepto, codigo):
        return Valor.objects.get(concepto__codigo=concepto, codigo=codigo)

    usuario = Usuario.objects.create(username="migracion-ap6021")
    proforma = Proforma.objects.create(
        numero=990021,
        estado=valor("ESTADO_PROFORMA", "BORRADOR"),
        moneda=valor("MONEDA", "BOB"),
        titulo="Migración AP6.0.21",
        fecha=timezone.localdate(),
        vendedor=usuario,
    )
    detalle = Detalle.objects.create(
        proforma=proforma,
        tipo_item=valor("TIPO_ITEM", "MUEBLE_MEDIDA"),
        nombre="Escritorio legado",
        cantidad=1,
        unidad=valor("UNIDAD_MEDIDA", "PIEZA"),
        modo_calculo="PRECIO_UNITARIO",
        precio_unitario="500.00",
        descuento="0.00",
    )
    # El test parte de una base que pytest creó en HEAD y retrocedió de estado.
    # La función PostgreSQL no es reversible; se desactiva el trigger sólo para
    # sembrar la fila histórica y se reactiva antes de ejecutar la migración.
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE especificaciones_mueble DISABLE TRIGGER USER")
    try:
        Especificacion.objects.create(
            proforma_detalle=detalle,
            schema_version=2,
            espesor={"espesor": "18 mm"},
            color_principal="Nogal",
            dimensiones={"ancho": "1.20 m"},
            accesorios=["Pasacables"],
            componentes=[{"nombre": "Mesón", "material": "Melamina"}],
            texto_original="Escritorio nogal con color pendiente",
            advertencias=["color a elección"],
            observaciones="Validar acabado",
        )
    finally:
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE especificaciones_mueble ENABLE TRIGGER USER")

    executor = MigrationExecutor(connection)
    executor.migrate(destino)
    apps_nuevas = executor.loader.project_state(destino).apps
    migrada = apps_nuevas.get_model("proformas", "EspecificacionMueble").objects.get(
        proforma_detalle_id=detalle.id
    )

    assert migrada.datos_tecnicos == {
        "componentes": [{"nombre": "Mesón", "material": "Melamina"}],
        "accesorios": ["Pasacables"],
        "descripcion_original": "Escritorio nogal con color pendiente",
        "advertencias": ["color a elección"],
        "caracteristicas_generales": {
            "espesor": {"espesor": "18 mm"},
            "color_principal": "Nogal",
            "dimensiones": {"ancho": "1.20 m"},
        },
    }
    assert migrada.observaciones == "Validar acabado"
    columnas = {
        columna.name
        for columna in connection.introspection.get_table_description(
            connection.cursor(), "especificaciones_mueble"
        )
    }
    assert columnas == {
        "id",
        "proforma_detalle_id",
        "tipo_mueble_id",
        "datos_tecnicos",
        "observaciones",
    }
