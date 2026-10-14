"""AP6.0.21: validación de atributos y veto al rollback destructivo.

0009 ya fue integrada/aplicada: no se modifica su historial. Las bases con
especificaciones APROBADAS deben ejecutar la actualización transaccional
scripts/ap6021_upgrade_aprobadas.py antes de emplear migraciones normales.
"""
from django.db import migrations
from django.db.migrations.exceptions import IrreversibleError


SQL = r"""
CREATE OR REPLACE FUNCTION fn_validar_especificacion_mueble()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_tipo TEXT;
    elemento JSONB;
    atributo TEXT;
BEGIN
    SELECT fn_catalogo_codigo_valor(pd.tipo_item_id, 'TIPO_ITEM')
      INTO v_tipo FROM proformas_detalle pd
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
            FOREACH atributo IN ARRAY ARRAY['material', 'espesor', 'color', 'acabado', 'dimensiones']
            LOOP
                IF elemento ? atributo
                   AND jsonb_typeof(elemento->atributo) NOT IN ('string', 'object', 'null') THEN
                    RAISE EXCEPTION 'Componente: atributo % debe ser texto u objeto', atributo;
                END IF;
            END LOOP;
        END LOOP;
    END IF;
    IF NEW.datos_tecnicos ? 'accesorios' THEN
        IF jsonb_typeof(NEW.datos_tecnicos->'accesorios') <> 'array' THEN
            RAISE EXCEPTION 'datos_tecnicos.accesorios debe ser un array';
        END IF;
        FOR elemento IN SELECT value FROM jsonb_array_elements(NEW.datos_tecnicos->'accesorios')
        LOOP
            IF jsonb_typeof(elemento) <> 'string'
               OR NULLIF(BTRIM(elemento #>> '{}'), '') IS NULL THEN
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
            IF jsonb_typeof(elemento) <> 'string'
               OR NULLIF(BTRIM(elemento #>> '{}'), '') IS NULL THEN
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
"""


def prohibir_reversion_destructiva(apps, schema_editor):
    raise IrreversibleError(
        "AP6.0.21 no permite un rollback Django hacia columnas antiguas: "
        "0010/0009 perderían datos_tecnicos. Restaurar backup PostgreSQL "
        "verificado junto con la versión compatible de backend/frontend."
    )


class Migration(migrations.Migration):
    dependencies = [("proformas", "0009_datos_tecnicos_unicos_ap6021")]
    operations = [
        migrations.RunSQL(SQL, reverse_sql=migrations.RunSQL.noop),
        # Última operación forward => primera al revertir; detiene la reversión
        # antes de revertir 0009, incluso con una ficha JSONB no vacía.
        migrations.RunPython(
            migrations.RunPython.noop, reverse_code=prohibir_reversion_destructiva
        ),
    ]
