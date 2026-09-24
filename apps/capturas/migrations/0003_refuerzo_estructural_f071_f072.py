from django.db import migrations


SQL = """
-- Defaults físicos: permiten INSERT directo y conectan secuencias comerciales.
ALTER TABLE proformas ALTER COLUMN numero SET DEFAULT nextval('seq_proformas_numero');
ALTER TABLE proformas ALTER COLUMN fecha SET DEFAULT CURRENT_DATE;
ALTER TABLE proformas ALTER COLUMN subtotal SET DEFAULT 0;
ALTER TABLE proformas ALTER COLUMN descuento_total SET DEFAULT 0;
ALTER TABLE proformas ALTER COLUMN total SET DEFAULT 0;
ALTER TABLE proformas_detalle ALTER COLUMN precio_unitario SET DEFAULT 0;
ALTER TABLE proformas_detalle ALTER COLUMN descuento SET DEFAULT 0;
ALTER TABLE proformas_detalle ALTER COLUMN total SET DEFAULT 0;
ALTER TABLE especificaciones_mueble ALTER COLUMN schema_version SET DEFAULT 1;
ALTER TABLE capturas ALTER COLUMN estado SET DEFAULT 'PENDIENTE';
ALTER TABLE intentos_captura ALTER COLUMN estado SET DEFAULT 'PENDIENTE';
ALTER TABLE trabajos_outbox ALTER COLUMN tipo SET DEFAULT 'PROCESAR_CAPTURA';
ALTER TABLE trabajos_outbox ALTER COLUMN intentos_publicacion SET DEFAULT 0;
ALTER TABLE evaluaciones_nlp ALTER COLUMN version_metrica SET DEFAULT 'V1';
ALTER TABLE evaluaciones_nlp ALTER COLUMN campos_totales SET DEFAULT 0;
ALTER TABLE evaluaciones_nlp ALTER COLUMN campos_corregidos SET DEFAULT 0;
ALTER TABLE evaluaciones_nlp ALTER COLUMN campos_agregados SET DEFAULT 0;
ALTER TABLE evaluaciones_nlp ALTER COLUMN campos_eliminados SET DEFAULT 0;
ALTER TABLE mediciones_proceso ALTER COLUMN num_items SET DEFAULT 1;
ALTER TABLE pedidos ALTER COLUMN fecha_confirmacion SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE ordenes_trabajo ALTER COLUMN numero SET DEFAULT nextval('seq_ordenes_trabajo_numero');
ALTER TABLE ordenes_trabajo ALTER COLUMN fecha SET DEFAULT CURRENT_DATE;
ALTER TABLE notas_entrega ALTER COLUMN numero SET DEFAULT nextval('seq_notas_entrega_numero');
ALTER TABLE notas_entrega ALTER COLUMN fecha SET DEFAULT CURRENT_DATE;
ALTER TABLE recibos ALTER COLUMN numero SET DEFAULT nextval('seq_recibos_numero');
ALTER TABLE recibos ALTER COLUMN fecha SET DEFAULT CURRENT_DATE;
ALTER TABLE movimientos_stock ALTER COLUMN fecha SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE capturas ALTER COLUMN capturado_at SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE intentos_captura ALTER COLUMN inicio_at SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE trabajos_outbox ALTER COLUMN disponible_at SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE items_humano ALTER COLUMN revisado_at SET DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE productos ADD CONSTRAINT ck_productos_precio_lista_nonnegative CHECK (precio_lista >= 0);
ALTER TABLE productos ADD CONSTRAINT ck_productos_stock_nonnegative CHECK (stock >= 0);
ALTER TABLE productos_silla ADD CONSTRAINT ck_silla_color_secundario_requiere_primario CHECK (color_secundario_id IS NULL OR color_primario_id IS NOT NULL);
ALTER TABLE productos_silla ADD CONSTRAINT ck_silla_colores_distintos CHECK (color_secundario_id IS NULL OR color_secundario_id <> color_primario_id);
ALTER TABLE productos_silla ADD CONSTRAINT ck_silla_especificaciones_objeto CHECK (especificaciones IS NULL OR jsonb_typeof(especificaciones) = 'object');
ALTER TABLE productos_piso ADD CONSTRAINT ck_piso_espesor_positive CHECK (espesor_mm IS NULL OR espesor_mm > 0);
ALTER TABLE productos_piso ADD CONSTRAINT ck_piso_largo_positive CHECK (largo_mm IS NULL OR largo_mm > 0);
ALTER TABLE productos_piso ADD CONSTRAINT ck_piso_ancho_positive CHECK (ancho_mm IS NULL OR ancho_mm > 0);
ALTER TABLE productos_piso ADD CONSTRAINT ck_piso_m2_caja_positive CHECK (m2_por_caja IS NULL OR m2_por_caja > 0);
ALTER TABLE productos_descuento ADD CONSTRAINT ck_descuento_precios_nonnegative CHECK (precio_antes >= 0 AND precio_ahora >= 0);
ALTER TABLE productos_descuento ADD CONSTRAINT ck_descuento_precio_reducido CHECK (precio_ahora < precio_antes);
ALTER TABLE proformas ADD CONSTRAINT ck_proforma_validez_nonnegative CHECK (validez_oferta IS NULL OR validez_oferta >= 0);
ALTER TABLE proformas ADD CONSTRAINT ck_proforma_adelanto CHECK (porcentaje_adelanto IS NULL OR (porcentaje_adelanto >= 0 AND porcentaje_adelanto <= 100));
ALTER TABLE proformas ADD CONSTRAINT ck_proforma_importes CHECK (subtotal >= 0 AND descuento_total >= 0 AND total >= 0);
ALTER TABLE proformas_detalle ADD CONSTRAINT ck_detalle_cantidad_positive CHECK (cantidad > 0);
ALTER TABLE proformas_detalle ADD CONSTRAINT ck_detalle_precio_nonnegative CHECK (precio_unitario >= 0);
ALTER TABLE proformas_detalle ADD CONSTRAINT ck_detalle_descuento_nonnegative CHECK (descuento >= 0);
ALTER TABLE proformas_detalle ADD CONSTRAINT ck_detalle_total_nonnegative CHECK (total >= 0);
ALTER TABLE proformas_detalle ADD CONSTRAINT ck_detalle_snapshot_promocion CHECK ((precio_antes_snapshot IS NULL AND precio_ahora_snapshot IS NULL) OR (precio_antes_snapshot IS NOT NULL AND precio_ahora_snapshot IS NOT NULL));
ALTER TABLE especificaciones_mueble ADD CONSTRAINT ck_especificacion_schema_version CHECK (schema_version = 1);
ALTER TABLE especificaciones_mueble ADD CONSTRAINT ck_especificacion_espesor_objeto CHECK (espesor IS NULL OR jsonb_typeof(espesor) = 'object');
ALTER TABLE especificaciones_mueble ADD CONSTRAINT ck_especificacion_dimensiones_objeto CHECK (dimensiones IS NULL OR jsonb_typeof(dimensiones) = 'object');
ALTER TABLE especificaciones_mueble ADD CONSTRAINT ck_especificacion_accesorios_array CHECK (accesorios IS NULL OR jsonb_typeof(accesorios) = 'array');
ALTER TABLE transiciones_estado_pedido ADD CONSTRAINT ck_transicion_estados_distintos CHECK (estado_origen_id <> estado_destino_id);
ALTER TABLE ordenes_trabajo ADD CONSTRAINT ck_ot_fechas CHECK (fecha_fin IS NULL OR fecha_inicio IS NULL OR fecha_fin >= fecha_inicio);
ALTER TABLE recibos ADD CONSTRAINT ck_recibo_total_positive CHECK (total > 0);
ALTER TABLE recibos ADD CONSTRAINT ck_recibo_pago_actual_positive CHECK (pago_actual > 0);
ALTER TABLE recibos ADD CONSTRAINT ck_recibo_a_cuenta_nonnegative CHECK (a_cuenta >= 0);
ALTER TABLE recibos ADD CONSTRAINT ck_recibo_saldo_nonnegative CHECK (saldo >= 0);
ALTER TABLE archivos_adjuntos ADD CONSTRAINT ck_archivo_tamano_nonnegative CHECK (tamano_bytes IS NULL OR tamano_bytes >= 0);
ALTER TABLE archivos_adjuntos ADD CONSTRAINT ck_archivo_no_audio CHECK (mime_type IS NULL OR mime_type !~* '^audio/');
ALTER TABLE capturas ADD CONSTRAINT ck_captura_estado CHECK (estado IN ('PENDIENTE','PROCESANDO','COMPLETADA','ERROR'));
ALTER TABLE capturas ADD CONSTRAINT fk_captura_detalle_misma_proforma FOREIGN KEY (proforma_id, proforma_detalle_id) REFERENCES proformas_detalle(proforma_id, id);
ALTER TABLE intentos_captura ADD CONSTRAINT ck_intento_numero_positive CHECK (numero_intento > 0);
ALTER TABLE intentos_captura ADD CONSTRAINT ck_intento_estado CHECK (estado IN ('PENDIENTE','PROCESANDO','FINALIZADO','ERROR'));
ALTER TABLE intentos_captura ADD CONSTRAINT ck_intento_etapa CHECK (etapa_alcanzada IS NULL OR etapa_alcanzada IN ('ASR','NLP','COMPLETO'));
ALTER TABLE intentos_captura ADD CONSTRAINT ck_intento_intervalo CHECK (fin_at IS NULL OR fin_at >= inicio_at);
ALTER TABLE intentos_captura ADD CONSTRAINT ck_intento_latencias CHECK ((latencia_total_ms IS NULL OR latencia_total_ms >= 0) AND (latencia_asr_ms IS NULL OR latencia_asr_ms >= 0) AND (latencia_nlp_ms IS NULL OR latencia_nlp_ms >= 0));
ALTER TABLE intentos_captura ADD CONSTRAINT ck_intento_labels_array CHECK (labels_detectados IS NULL OR jsonb_typeof(labels_detectados) = 'array');
ALTER TABLE intentos_captura ADD CONSTRAINT ck_intento_resultado_objeto CHECK (resultado_raw IS NULL OR jsonb_typeof(resultado_raw) = 'object');
ALTER TABLE trabajos_outbox ADD CONSTRAINT ck_outbox_intentos_nonnegative CHECK (intentos_publicacion >= 0);
ALTER TABLE trabajos_outbox ADD CONSTRAINT ck_outbox_tipo CHECK (tipo IN ('PROCESAR_CAPTURA'));
ALTER TABLE items_ia ADD CONSTRAINT ck_item_ia_espesor_objeto CHECK (espesor IS NULL OR jsonb_typeof(espesor) = 'object');
ALTER TABLE items_ia ADD CONSTRAINT ck_item_ia_dimensiones_objeto CHECK (dimensiones IS NULL OR jsonb_typeof(dimensiones) = 'object');
ALTER TABLE items_ia ADD CONSTRAINT ck_item_ia_accesorios_array CHECK (accesorios IS NULL OR jsonb_typeof(accesorios) = 'array');
ALTER TABLE items_ia ADD CONSTRAINT ck_item_ia_cantidad_positive CHECK (cantidad IS NULL OR cantidad > 0);
ALTER TABLE items_ia ADD CONSTRAINT ck_item_ia_precio_nonnegative CHECK (precio_total IS NULL OR precio_total >= 0);
ALTER TABLE items_humano ADD CONSTRAINT ck_item_humano_espesor_objeto CHECK (espesor IS NULL OR jsonb_typeof(espesor) = 'object');
ALTER TABLE items_humano ADD CONSTRAINT ck_item_humano_dimensiones_objeto CHECK (dimensiones IS NULL OR jsonb_typeof(dimensiones) = 'object');
ALTER TABLE items_humano ADD CONSTRAINT ck_item_humano_accesorios_array CHECK (accesorios IS NULL OR jsonb_typeof(accesorios) = 'array');
ALTER TABLE items_humano ADD CONSTRAINT ck_item_humano_cantidad_positive CHECK (cantidad IS NULL OR cantidad > 0);
ALTER TABLE items_humano ADD CONSTRAINT ck_item_humano_precio_nonnegative CHECK (precio_total IS NULL OR precio_total >= 0);
ALTER TABLE evaluaciones_nlp ADD CONSTRAINT ck_eval_tiempo CHECK (tiempo_revision_ms IS NULL OR tiempo_revision_ms >= 0);
ALTER TABLE evaluaciones_nlp ADD CONSTRAINT ck_eval_intervalo CHECK (fin_revision_at IS NULL OR inicio_revision_at IS NULL OR fin_revision_at >= inicio_revision_at);
ALTER TABLE evaluaciones_nlp ADD CONSTRAINT ck_eval_counts CHECK (campos_totales >= 0 AND campos_corregidos >= 0 AND campos_agregados >= 0 AND campos_eliminados >= 0);
ALTER TABLE evaluaciones_nlp ADD CONSTRAINT ck_eval_precision_range CHECK ((precision_item IS NULL OR (precision_item >= 0 AND precision_item <= 1)) AND (precision_campo IS NULL OR (precision_campo >= 0 AND precision_campo <= 1)));
ALTER TABLE mediciones_proceso ADD CONSTRAINT ck_medicion_intervalo CHECK (fin_at >= inicio_at);
ALTER TABLE mediciones_proceso ADD CONSTRAINT ck_medicion_tiempo CHECK (tiempo_total_ms >= 0);
ALTER TABLE mediciones_proceso ADD CONSTRAINT ck_medicion_items CHECK (num_items > 0);
ALTER TABLE movimientos_stock ADD CONSTRAINT ck_mov_stock_cantidad_nonzero CHECK (cantidad <> 0);
ALTER TABLE movimientos_stock ADD CONSTRAINT ck_mov_stock_no_autorreferencia CHECK (movimiento_referencia_id IS NULL OR movimiento_referencia_id <> id);
CREATE UNIQUE INDEX uq_mov_stock_venta_pedido_producto ON movimientos_stock (pedido_id, producto_id) WHERE pedido_id IS NOT NULL;
CREATE INDEX ix_outbox_pendientes ON trabajos_outbox (disponible_at) WHERE publicado_at IS NULL;
"""

REVERSE = (
    """
DROP INDEX IF EXISTS ix_outbox_pendientes;
DROP INDEX IF EXISTS uq_mov_stock_venta_pedido_producto;
ALTER TABLE capturas DROP CONSTRAINT IF EXISTS fk_captura_detalle_misma_proforma;
"""
    + "\n".join(
        f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint};"
        for table, constraint in [
            ("productos", "ck_productos_precio_lista_nonnegative"),
            ("productos", "ck_productos_stock_nonnegative"),
            ("productos_silla", "ck_silla_color_secundario_requiere_primario"),
            ("productos_silla", "ck_silla_colores_distintos"),
            ("productos_silla", "ck_silla_especificaciones_objeto"),
            ("productos_piso", "ck_piso_espesor_positive"),
            ("productos_piso", "ck_piso_largo_positive"),
            ("productos_piso", "ck_piso_ancho_positive"),
            ("productos_piso", "ck_piso_m2_caja_positive"),
            ("productos_descuento", "ck_descuento_precios_nonnegative"),
            ("productos_descuento", "ck_descuento_precio_reducido"),
            ("proformas", "ck_proforma_validez_nonnegative"),
            ("proformas", "ck_proforma_adelanto"),
            ("proformas", "ck_proforma_importes"),
            ("proformas_detalle", "ck_detalle_cantidad_positive"),
            ("proformas_detalle", "ck_detalle_precio_nonnegative"),
            ("proformas_detalle", "ck_detalle_descuento_nonnegative"),
            ("proformas_detalle", "ck_detalle_total_nonnegative"),
            ("proformas_detalle", "ck_detalle_snapshot_promocion"),
            ("especificaciones_mueble", "ck_especificacion_schema_version"),
            ("especificaciones_mueble", "ck_especificacion_espesor_objeto"),
            ("especificaciones_mueble", "ck_especificacion_dimensiones_objeto"),
            ("especificaciones_mueble", "ck_especificacion_accesorios_array"),
            ("transiciones_estado_pedido", "ck_transicion_estados_distintos"),
            ("ordenes_trabajo", "ck_ot_fechas"),
            ("recibos", "ck_recibo_total_positive"),
            ("recibos", "ck_recibo_pago_actual_positive"),
            ("recibos", "ck_recibo_a_cuenta_nonnegative"),
            ("recibos", "ck_recibo_saldo_nonnegative"),
            ("archivos_adjuntos", "ck_archivo_tamano_nonnegative"),
            ("archivos_adjuntos", "ck_archivo_no_audio"),
            ("capturas", "ck_captura_estado"),
            ("intentos_captura", "ck_intento_numero_positive"),
            ("intentos_captura", "ck_intento_estado"),
            ("intentos_captura", "ck_intento_etapa"),
            ("intentos_captura", "ck_intento_intervalo"),
            ("intentos_captura", "ck_intento_latencias"),
            ("intentos_captura", "ck_intento_labels_array"),
            ("intentos_captura", "ck_intento_resultado_objeto"),
            ("trabajos_outbox", "ck_outbox_intentos_nonnegative"),
            ("trabajos_outbox", "ck_outbox_tipo"),
            ("items_ia", "ck_item_ia_espesor_objeto"),
            ("items_ia", "ck_item_ia_dimensiones_objeto"),
            ("items_ia", "ck_item_ia_accesorios_array"),
            ("items_ia", "ck_item_ia_cantidad_positive"),
            ("items_ia", "ck_item_ia_precio_nonnegative"),
            ("items_humano", "ck_item_humano_espesor_objeto"),
            ("items_humano", "ck_item_humano_dimensiones_objeto"),
            ("items_humano", "ck_item_humano_accesorios_array"),
            ("items_humano", "ck_item_humano_cantidad_positive"),
            ("items_humano", "ck_item_humano_precio_nonnegative"),
            ("evaluaciones_nlp", "ck_eval_tiempo"),
            ("evaluaciones_nlp", "ck_eval_intervalo"),
            ("evaluaciones_nlp", "ck_eval_counts"),
            ("evaluaciones_nlp", "ck_eval_precision_range"),
            ("mediciones_proceso", "ck_medicion_intervalo"),
            ("mediciones_proceso", "ck_medicion_tiempo"),
            ("mediciones_proceso", "ck_medicion_items"),
            ("movimientos_stock", "ck_mov_stock_cantidad_nonzero"),
            ("movimientos_stock", "ck_mov_stock_no_autorreferencia"),
        ]
    )
    + """
ALTER TABLE proformas ALTER COLUMN numero DROP DEFAULT;
ALTER TABLE proformas ALTER COLUMN fecha DROP DEFAULT;
ALTER TABLE proformas ALTER COLUMN subtotal DROP DEFAULT;
ALTER TABLE proformas ALTER COLUMN descuento_total DROP DEFAULT;
ALTER TABLE proformas ALTER COLUMN total DROP DEFAULT;
ALTER TABLE proformas_detalle ALTER COLUMN precio_unitario DROP DEFAULT;
ALTER TABLE proformas_detalle ALTER COLUMN descuento DROP DEFAULT;
ALTER TABLE proformas_detalle ALTER COLUMN total DROP DEFAULT;
ALTER TABLE especificaciones_mueble ALTER COLUMN schema_version DROP DEFAULT;
ALTER TABLE capturas ALTER COLUMN estado DROP DEFAULT;
ALTER TABLE intentos_captura ALTER COLUMN estado DROP DEFAULT;
ALTER TABLE trabajos_outbox ALTER COLUMN tipo DROP DEFAULT;
ALTER TABLE trabajos_outbox ALTER COLUMN intentos_publicacion DROP DEFAULT;
ALTER TABLE evaluaciones_nlp ALTER COLUMN version_metrica DROP DEFAULT;
ALTER TABLE evaluaciones_nlp ALTER COLUMN campos_totales DROP DEFAULT;
ALTER TABLE evaluaciones_nlp ALTER COLUMN campos_corregidos DROP DEFAULT;
ALTER TABLE evaluaciones_nlp ALTER COLUMN campos_agregados DROP DEFAULT;
ALTER TABLE evaluaciones_nlp ALTER COLUMN campos_eliminados DROP DEFAULT;
ALTER TABLE mediciones_proceso ALTER COLUMN num_items DROP DEFAULT;
ALTER TABLE pedidos ALTER COLUMN fecha_confirmacion DROP DEFAULT;
ALTER TABLE ordenes_trabajo ALTER COLUMN numero DROP DEFAULT;
ALTER TABLE ordenes_trabajo ALTER COLUMN fecha DROP DEFAULT;
ALTER TABLE notas_entrega ALTER COLUMN numero DROP DEFAULT;
ALTER TABLE notas_entrega ALTER COLUMN fecha DROP DEFAULT;
ALTER TABLE recibos ALTER COLUMN numero DROP DEFAULT;
ALTER TABLE recibos ALTER COLUMN fecha DROP DEFAULT;
ALTER TABLE movimientos_stock ALTER COLUMN fecha DROP DEFAULT;
ALTER TABLE capturas ALTER COLUMN capturado_at DROP DEFAULT;
ALTER TABLE intentos_captura ALTER COLUMN inicio_at DROP DEFAULT;
ALTER TABLE trabajos_outbox ALTER COLUMN disponible_at DROP DEFAULT;
ALTER TABLE items_humano ALTER COLUMN revisado_at DROP DEFAULT;
"""
)


class Migration(migrations.Migration):
    dependencies = [
        ("capturas", "0002_integridad_postgresql"),
        ("catalogo", "0005_descuentoproducto_ck_descuento_precios_ordenados_and_more"),
        ("proformas", "0003_reglas_comerciales_f072"),
    ]
    operations = [migrations.RunSQL(SQL, REVERSE)]
