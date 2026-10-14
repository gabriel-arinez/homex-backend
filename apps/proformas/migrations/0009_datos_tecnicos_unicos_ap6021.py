from django.db import migrations, models


def consolidar_datos_tecnicos(apps, schema_editor):
    Especificacion = apps.get_model("proformas", "EspecificacionMueble")
    for especificacion in Especificacion.objects.all().iterator():
        datos = {}
        if especificacion.componentes:
            datos["componentes"] = especificacion.componentes
        if especificacion.accesorios:
            datos["accesorios"] = especificacion.accesorios
        if especificacion.texto_original:
            datos["descripcion_original"] = especificacion.texto_original
        if especificacion.advertencias:
            datos["advertencias"] = especificacion.advertencias

        generales = {}
        for campo in ("espesor", "color_principal", "color_secundario", "dimensiones"):
            valor = getattr(especificacion, campo)
            if valor not in (None, "", [], {}):
                generales[campo] = valor
        if generales:
            datos["caracteristicas_generales"] = generales

        especificacion.datos_tecnicos = datos
        especificacion.save(update_fields=["datos_tecnicos"])


SQL_VALIDACION = r"""
ALTER TABLE especificaciones_mueble
    DROP CONSTRAINT IF EXISTS ck_especificacion_schema_version,
    DROP CONSTRAINT IF EXISTS ck_especificacion_espesor_objeto,
    DROP CONSTRAINT IF EXISTS ck_especificacion_dimensiones_objeto,
    DROP CONSTRAINT IF EXISTS ck_especificacion_accesorios_array;

CREATE OR REPLACE FUNCTION fn_validar_especificacion_mueble()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_tipo TEXT;
    elemento JSONB;
BEGIN
    SELECT fn_catalogo_codigo_valor(pd.tipo_item_id, 'TIPO_ITEM')
      INTO v_tipo
      FROM proformas_detalle pd
     WHERE pd.id = NEW.proforma_detalle_id;

    IF v_tipo IS DISTINCT FROM 'MUEBLE_MEDIDA' THEN
        RAISE EXCEPTION 'especificaciones_mueble sólo puede asociarse a MUEBLE_MEDIDA';
    END IF;

    IF NEW.tipo_mueble_id IS NOT NULL
       AND (TG_OP = 'INSERT' OR NEW.tipo_mueble_id IS DISTINCT FROM OLD.tipo_mueble_id)
       AND NOT fn_catalogo_valor_pertenece_activo(NEW.tipo_mueble_id, 'TIPO_MUEBLE') THEN
        RAISE EXCEPTION 'tipo_mueble_id % no pertenece a TIPO_MUEBLE activo', NEW.tipo_mueble_id;
    END IF;

    IF NEW.datos_tecnicos IS NULL OR jsonb_typeof(NEW.datos_tecnicos) <> 'object' THEN
        RAISE EXCEPTION 'datos_tecnicos debe ser un objeto JSON';
    END IF;

    IF NEW.datos_tecnicos ? 'schema_version' THEN
        RAISE EXCEPTION 'schema_version no forma parte del formato comercial';
    END IF;

    IF NEW.datos_tecnicos ? 'componentes' THEN
        IF jsonb_typeof(NEW.datos_tecnicos->'componentes') <> 'array' THEN
            RAISE EXCEPTION 'datos_tecnicos.componentes debe ser un array';
        END IF;
        FOR elemento IN SELECT value FROM jsonb_array_elements(NEW.datos_tecnicos->'componentes')
        LOOP
            IF jsonb_typeof(elemento) <> 'object'
               OR jsonb_typeof(elemento->'nombre') <> 'string'
               OR NULLIF(BTRIM(elemento->>'nombre'), '') IS NULL THEN
                RAISE EXCEPTION 'Cada componente debe ser un objeto con nombre no vacío';
            END IF;
        END LOOP;
    END IF;

    IF NEW.datos_tecnicos ? 'accesorios' THEN
        IF jsonb_typeof(NEW.datos_tecnicos->'accesorios') <> 'array' THEN
            RAISE EXCEPTION 'datos_tecnicos.accesorios debe ser un array';
        END IF;
        FOR elemento IN SELECT value FROM jsonb_array_elements(NEW.datos_tecnicos->'accesorios')
        LOOP
            IF jsonb_typeof(elemento) <> 'string' OR NULLIF(BTRIM(elemento #>> '{}'), '') IS NULL THEN
                RAISE EXCEPTION 'Cada accesorio debe ser texto no vacío';
            END IF;
        END LOOP;
    END IF;

    IF NEW.datos_tecnicos ? 'advertencias' THEN
        IF jsonb_typeof(NEW.datos_tecnicos->'advertencias') <> 'array' THEN
            RAISE EXCEPTION 'datos_tecnicos.advertencias debe ser un array';
        END IF;
        FOR elemento IN SELECT value FROM jsonb_array_elements(NEW.datos_tecnicos->'advertencias')
        LOOP
            IF jsonb_typeof(elemento) <> 'string' OR NULLIF(BTRIM(elemento #>> '{}'), '') IS NULL THEN
                RAISE EXCEPTION 'Cada advertencia debe ser texto no vacío';
            END IF;
        END LOOP;
    END IF;

    IF NEW.datos_tecnicos ? 'descripcion_original'
       AND jsonb_typeof(NEW.datos_tecnicos->'descripcion_original') <> 'string' THEN
        RAISE EXCEPTION 'datos_tecnicos.descripcion_original debe ser texto';
    END IF;

    IF NEW.datos_tecnicos ? 'caracteristicas_generales'
       AND jsonb_typeof(NEW.datos_tecnicos->'caracteristicas_generales') <> 'object' THEN
        RAISE EXCEPTION 'datos_tecnicos.caracteristicas_generales debe ser un objeto';
    END IF;

    RETURN NEW;
END;
$$;

ALTER TABLE especificaciones_mueble
    ADD CONSTRAINT ck_especificacion_datos_tecnicos_objeto
    CHECK (jsonb_typeof(datos_tecnicos) = 'object');
"""


class Migration(migrations.Migration):
    dependencies = [("proformas", "0008_ap6_caja_historica_stock")]

    operations = [
        migrations.AddField(
            model_name="especificacionmueble",
            name="datos_tecnicos",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.RunPython(consolidar_datos_tecnicos, migrations.RunPython.noop),
        migrations.RunSQL(SQL_VALIDACION, migrations.RunSQL.noop),
        migrations.RemoveField(model_name="especificacionmueble", name="schema_version"),
        migrations.RemoveField(model_name="especificacionmueble", name="espesor"),
        migrations.RemoveField(model_name="especificacionmueble", name="color_principal"),
        migrations.RemoveField(model_name="especificacionmueble", name="color_secundario"),
        migrations.RemoveField(model_name="especificacionmueble", name="dimensiones"),
        migrations.RemoveField(model_name="especificacionmueble", name="accesorios"),
        migrations.RemoveField(model_name="especificacionmueble", name="componentes"),
        migrations.RemoveField(model_name="especificacionmueble", name="texto_original"),
        migrations.RemoveField(model_name="especificacionmueble", name="advertencias"),
    ]
