"""Soporte transaccional aislado de fecha comercial en triggers de pedido y stock."""

from django.db import migrations

SQL = """
ALTER TABLE movimientos_stock
    ALTER COLUMN registrado_en SET DEFAULT CURRENT_TIMESTAMP;

CREATE OR REPLACE FUNCTION public.fn_validar_nuevo_pedido()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_estado_proforma TEXT;
    v_fecha_simulada TIMESTAMPTZ;
BEGIN
    IF NOT fn_catalogo_valor_es(NEW.estado_id, 'ESTADO_PEDIDO', 'CONFIRMADO') THEN
        RAISE EXCEPTION 'Un pedido nuevo debe crearse en estado CONFIRMADO';
    END IF;

    SELECT fn_catalogo_codigo_valor(p.estado_id, 'ESTADO_PROFORMA')
    INTO v_estado_proforma
    FROM proformas p
    WHERE p.id = NEW.proforma_id;

    IF v_estado_proforma IS DISTINCT FROM 'APROBADA' THEN
        RAISE EXCEPTION 'Sólo una proforma APROBADA puede generar un pedido';
    END IF;

    v_fecha_simulada := NULLIF(current_setting('homex.fecha_comercial_simulada', true), '')::timestamptz;
    IF v_fecha_simulada IS NOT NULL THEN
        NEW.fecha_confirmacion := v_fecha_simulada;
    ELSIF NEW.fecha_confirmacion IS NULL THEN
        NEW.fecha_confirmacion := CURRENT_TIMESTAMP;
    END IF;

    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.fn_confirmar_pedido_descontar_stock()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_tipo_venta BIGINT;
    v_stock NUMERIC(14,4);
    v_modalidad VARCHAR(20);
    v_requerido NUMERIC(14,4);
    v_producto_id BIGINT;
    v_fecha_mov TIMESTAMPTZ;
BEGIN
    IF NOT fn_catalogo_valor_es(NEW.estado_id, 'ESTADO_PEDIDO', 'CONFIRMADO') THEN
        RETURN NEW;
    END IF;
    IF EXISTS(
        SELECT 1
          FROM proformas_detalle pd
         WHERE pd.proforma_id = NEW.proforma_id
           AND pd.producto_id IS NULL
           AND NOT fn_catalogo_valor_es(pd.tipo_item_id, 'TIPO_ITEM', 'MUEBLE_MEDIDA')
    ) THEN
        RAISE EXCEPTION 'No se puede aprobar: existe una variante de catálogo pendiente';
    END IF;

    v_tipo_venta := fn_catalogo_id('TIPO_MOVIMIENTO', 'VENTA');
    v_fecha_mov := COALESCE(
        NULLIF(current_setting('homex.fecha_comercial_simulada', true), '')::timestamptz,
        CURRENT_TIMESTAMP
    );

    FOR v_producto_id, v_requerido IN
        SELECT pd.producto_id, SUM(pd.cantidad)
          FROM proformas_detalle pd
         WHERE pd.proforma_id = NEW.proforma_id
           AND pd.producto_id IS NOT NULL
         GROUP BY pd.producto_id
         ORDER BY pd.producto_id
    LOOP
        SELECT p.stock, p.modalidad_abastecimiento
          INTO v_stock, v_modalidad
          FROM productos p
         WHERE p.id = v_producto_id
           FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Producto % no existe', v_producto_id;
        END IF;
        IF v_modalidad = 'CON_STOCK' AND v_stock < v_requerido THEN
            RAISE EXCEPTION 'Stock insuficiente para producto %. Disponible %, requerido %',
                v_producto_id, v_stock, v_requerido;
        END IF;
    END LOOP;

    FOR v_producto_id, v_requerido IN
        SELECT pd.producto_id, SUM(pd.cantidad)
          FROM proformas_detalle pd
          JOIN productos p ON p.id = pd.producto_id
         WHERE pd.proforma_id = NEW.proforma_id
           AND pd.producto_id IS NOT NULL
           AND p.modalidad_abastecimiento = 'CON_STOCK'
         GROUP BY pd.producto_id
         ORDER BY pd.producto_id
    LOOP
        INSERT INTO movimientos_stock(
            producto_id, fecha, tipo_movimiento_id, cantidad, pedido_id, observaciones, created_by_id
        )
        VALUES(
            v_producto_id,
            v_fecha_mov,
            v_tipo_venta,
            -v_requerido,
            NEW.id,
            'Salida por aprobación de proforma / pedido #' || NEW.id,
            COALESCE(NEW.updated_by_id, NEW.created_by_id)
        );
    END LOOP;

    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.fn_cancelar_pedido_revertir_stock()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_tipo_reversa BIGINT;
    v_estado_ot_cancelada BIGINT;
    v_venta RECORD;
    v_fecha_mov TIMESTAMPTZ;
BEGIN
    IF NOT fn_catalogo_valor_es(NEW.estado_id, 'ESTADO_PEDIDO', 'CANCELADO')
       OR fn_catalogo_valor_es(OLD.estado_id, 'ESTADO_PEDIDO', 'CANCELADO') THEN
        RETURN NEW;
    END IF;

    v_tipo_reversa := fn_catalogo_id('TIPO_MOVIMIENTO', 'REVERSA_VENTA');
    IF v_tipo_reversa IS NULL THEN
        RAISE EXCEPTION 'No existe TIPO_MOVIMIENTO.REVERSA_VENTA activo';
    END IF;

    v_fecha_mov := COALESCE(
        NULLIF(current_setting('homex.fecha_comercial_simulada', true), '')::timestamptz,
        CURRENT_TIMESTAMP
    );

    FOR v_venta IN
        SELECT ms.id, ms.producto_id, ms.cantidad
        FROM movimientos_stock ms
        WHERE ms.pedido_id = NEW.id
          AND fn_catalogo_valor_es(ms.tipo_movimiento_id, 'TIPO_MOVIMIENTO', 'VENTA')
        ORDER BY ms.producto_id
    LOOP
        INSERT INTO movimientos_stock (
            producto_id, fecha, tipo_movimiento_id, cantidad,
            movimiento_referencia_id, observaciones, created_by_id
        ) VALUES (
            v_venta.producto_id,
            v_fecha_mov,
            v_tipo_reversa,
            ABS(v_venta.cantidad),
            v_venta.id,
            'Reversa automática por cancelación del pedido #' || NEW.id,
            COALESCE(NEW.updated_by_id, NEW.created_by_id)
        );
    END LOOP;

    v_estado_ot_cancelada := fn_catalogo_id('ESTADO_ORDEN_TRABAJO', 'CANCELADA');
    IF v_estado_ot_cancelada IS NOT NULL THEN
        UPDATE ordenes_trabajo
        SET estado_id = v_estado_ot_cancelada,
            updated_by_id = COALESCE(NEW.updated_by_id, NEW.created_by_id)
        WHERE pedido_id = NEW.id;
    END IF;

    RETURN NEW;
END;
$function$;
"""

REVERSE_SQL = """
ALTER TABLE movimientos_stock
    ALTER COLUMN registrado_en DROP DEFAULT;

CREATE OR REPLACE FUNCTION public.fn_validar_nuevo_pedido()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_estado_proforma TEXT;
BEGIN
    IF NOT fn_catalogo_valor_es(NEW.estado_id, 'ESTADO_PEDIDO', 'CONFIRMADO') THEN
        RAISE EXCEPTION 'Un pedido nuevo debe crearse en estado CONFIRMADO';
    END IF;

    SELECT fn_catalogo_codigo_valor(p.estado_id, 'ESTADO_PROFORMA')
    INTO v_estado_proforma
    FROM proformas p
    WHERE p.id = NEW.proforma_id;

    IF v_estado_proforma IS DISTINCT FROM 'APROBADA' THEN
        RAISE EXCEPTION 'Sólo una proforma APROBADA puede generar un pedido';
    END IF;

    IF NEW.fecha_confirmacion IS NULL THEN
        NEW.fecha_confirmacion := CURRENT_TIMESTAMP;
    END IF;

    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.fn_confirmar_pedido_descontar_stock()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_tipo_venta BIGINT;
    v_stock NUMERIC(14,4);
    v_modalidad VARCHAR(20);
    v_requerido NUMERIC(14,4);
    v_producto_id BIGINT;
BEGIN
    IF NOT fn_catalogo_valor_es(NEW.estado_id, 'ESTADO_PEDIDO', 'CONFIRMADO') THEN
        RETURN NEW;
    END IF;
    IF EXISTS(
        SELECT 1
          FROM proformas_detalle pd
         WHERE pd.proforma_id = NEW.proforma_id
           AND pd.producto_id IS NULL
           AND NOT fn_catalogo_valor_es(pd.tipo_item_id, 'TIPO_ITEM', 'MUEBLE_MEDIDA')
    ) THEN
        RAISE EXCEPTION 'No se puede aprobar: existe una variante de catálogo pendiente';
    END IF;

    v_tipo_venta := fn_catalogo_id('TIPO_MOVIMIENTO', 'VENTA');

    FOR v_producto_id, v_requerido IN
        SELECT pd.producto_id, SUM(pd.cantidad)
          FROM proformas_detalle pd
         WHERE pd.proforma_id = NEW.proforma_id
           AND pd.producto_id IS NOT NULL
         GROUP BY pd.producto_id
         ORDER BY pd.producto_id
    LOOP
        SELECT p.stock, p.modalidad_abastecimiento
          INTO v_stock, v_modalidad
          FROM productos p
         WHERE p.id = v_producto_id
           FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Producto % no existe', v_producto_id;
        END IF;
        IF v_modalidad = 'CON_STOCK' AND v_stock < v_requerido THEN
            RAISE EXCEPTION 'Stock insuficiente para producto %. Disponible %, requerido %',
                v_producto_id, v_stock, v_requerido;
        END IF;
    END LOOP;

    FOR v_producto_id, v_requerido IN
        SELECT pd.producto_id, SUM(pd.cantidad)
          FROM proformas_detalle pd
          JOIN productos p ON p.id = pd.producto_id
         WHERE pd.proforma_id = NEW.proforma_id
           AND pd.producto_id IS NOT NULL
           AND p.modalidad_abastecimiento = 'CON_STOCK'
         GROUP BY pd.producto_id
         ORDER BY pd.producto_id
    LOOP
        INSERT INTO movimientos_stock(
            producto_id, tipo_movimiento_id, cantidad, pedido_id, observaciones, created_by_id
        )
        VALUES(
            v_producto_id,
            v_tipo_venta,
            -v_requerido,
            NEW.id,
            'Salida por aprobación de proforma / pedido #' || NEW.id,
            COALESCE(NEW.updated_by_id, NEW.created_by_id)
        );
    END LOOP;

    RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.fn_cancelar_pedido_revertir_stock()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_tipo_reversa BIGINT;
    v_estado_ot_cancelada BIGINT;
    v_venta RECORD;
BEGIN
    IF NOT fn_catalogo_valor_es(NEW.estado_id, 'ESTADO_PEDIDO', 'CANCELADO')
       OR fn_catalogo_valor_es(OLD.estado_id, 'ESTADO_PEDIDO', 'CANCELADO') THEN
        RETURN NEW;
    END IF;

    v_tipo_reversa := fn_catalogo_id('TIPO_MOVIMIENTO', 'REVERSA_VENTA');
    IF v_tipo_reversa IS NULL THEN
        RAISE EXCEPTION 'No existe TIPO_MOVIMIENTO.REVERSA_VENTA activo';
    END IF;

    FOR v_venta IN
        SELECT ms.id, ms.producto_id, ms.cantidad
        FROM movimientos_stock ms
        WHERE ms.pedido_id = NEW.id
          AND fn_catalogo_valor_es(ms.tipo_movimiento_id, 'TIPO_MOVIMIENTO', 'VENTA')
        ORDER BY ms.producto_id
    LOOP
        INSERT INTO movimientos_stock (
            producto_id, tipo_movimiento_id, cantidad,
            movimiento_referencia_id, observaciones, created_by_id
        ) VALUES (
            v_venta.producto_id,
            v_tipo_reversa,
            ABS(v_venta.cantidad),
            v_venta.id,
            'Reversa automática por cancelación del pedido #' || NEW.id,
            COALESCE(NEW.updated_by_id, NEW.created_by_id)
        );
    END LOOP;

    v_estado_ot_cancelada := fn_catalogo_id('ESTADO_ORDEN_TRABAJO', 'CANCELADA');
    IF v_estado_ot_cancelada IS NOT NULL THEN
        UPDATE ordenes_trabajo
        SET estado_id = v_estado_ot_cancelada,
            updated_by_id = COALESCE(NEW.updated_by_id, NEW.created_by_id)
        WHERE pedido_id = NEW.id;
    END IF;

    RETURN NEW;
END;
$function$;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("movimientos_stock", "0007_movimientostock_registrado_en"),
        ("pedidos", "0002_pedido_fecha_entrega_efectiva"),
        ("proformas", "0015_proforma_ultima_actividad_comercial_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=SQL, reverse_sql=REVERSE_SQL),
    ]
