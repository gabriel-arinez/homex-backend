from django.db import migrations


SQL = r'''
INSERT INTO catalogo_valores (concepto_id, codigo, nombre, activo)
SELECT c.id, v.codigo, v.nombre, TRUE
FROM catalogo_conceptos c
CROSS JOIN (VALUES
    ('M2', 'Metro cuadrado'),
    ('BARRA', 'Barra'),
    ('JUEGO', 'Juego')
) AS v(codigo, nombre)
WHERE c.codigo = 'UNIDAD_MEDIDA'
ON CONFLICT (concepto_id, codigo) DO UPDATE SET nombre = EXCLUDED.nombre, activo = TRUE;

INSERT INTO catalogo_valores (concepto_id, codigo, nombre, activo)
SELECT c.id, v.codigo, v.nombre, TRUE
FROM catalogo_conceptos c
CROSS JOIN (VALUES
    ('EN_REVISION', 'En revisión'),
    ('NO_CONCRETADA', 'No concretada')
) AS v(codigo, nombre)
WHERE c.codigo = 'ESTADO_PROFORMA'
ON CONFLICT (concepto_id, codigo) DO UPDATE SET nombre = EXCLUDED.nombre, activo = TRUE;

INSERT INTO transiciones_estado_pedido (estado_origen_id, estado_destino_id)
SELECT origen.id, destino.id
FROM catalogo_valores origen
JOIN catalogo_conceptos c ON c.id = origen.concepto_id AND c.codigo = 'ESTADO_PEDIDO'
JOIN catalogo_valores destino ON destino.concepto_id = origen.concepto_id
WHERE origen.codigo = 'CONFIRMADO' AND destino.codigo = 'LISTO_ENTREGA'
ON CONFLICT DO NOTHING;

ALTER TABLE especificaciones_mueble DROP CONSTRAINT ck_especificacion_schema_version;
ALTER TABLE especificaciones_mueble ADD CONSTRAINT ck_especificacion_schema_version
CHECK (schema_version IN (1, 2));

CREATE OR REPLACE FUNCTION fn_actualizar_stock_desde_movimiento()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_stock NUMERIC(14,4);
BEGIN
 SELECT stock INTO v_stock FROM productos WHERE id=NEW.producto_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Producto % no existe',NEW.producto_id; END IF;
 IF v_stock+NEW.cantidad<0 THEN
  RAISE EXCEPTION 'Stock insuficiente para producto %: disponible %, movimiento %',NEW.producto_id,v_stock,NEW.cantidad;
 END IF;
 PERFORM set_config('homex.stock_update_context','MOVIMIENTO_STOCK',TRUE);
 UPDATE productos SET stock=v_stock+NEW.cantidad WHERE id=NEW.producto_id;
 PERFORM set_config('homex.stock_update_context','',TRUE);
 RETURN NEW;
END; $$;

CREATE OR REPLACE FUNCTION fn_validar_producto_catalogos()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_categoria TEXT; v_unidad TEXT;
BEGIN
    IF NOT fn_catalogo_valor_pertenece_activo(NEW.categoria_id, 'CATEGORIA_PRODUCTO') THEN
        RAISE EXCEPTION 'categoria_id % no pertenece a CATEGORIA_PRODUCTO activo', NEW.categoria_id;
    END IF;
    IF NOT fn_catalogo_valor_pertenece_activo(NEW.unidad_stock_id, 'UNIDAD_MEDIDA') THEN
        RAISE EXCEPTION 'unidad_stock_id % no pertenece a UNIDAD_MEDIDA activa', NEW.unidad_stock_id;
    END IF;
    v_categoria := fn_catalogo_codigo_valor(NEW.categoria_id, 'CATEGORIA_PRODUCTO');
    v_unidad := fn_catalogo_codigo_valor(NEW.unidad_stock_id, 'UNIDAD_MEDIDA');
    IF v_categoria = 'PISO_FLOTANTE' AND v_unidad <> 'M2' THEN
        RAISE EXCEPTION 'Un PISO_FLOTANTE nuevo debe manejar stock en M2';
    ELSIF v_categoria = 'SILLA' AND v_unidad <> 'PIEZA' THEN
        RAISE EXCEPTION 'Una SILLA debe manejar stock en PIEZA';
    ELSIF v_categoria = 'OTRO' AND v_unidad NOT IN ('PIEZA','JUEGO','BARRA') THEN
        RAISE EXCEPTION 'Un producto OTRO debe usar PIEZA, JUEGO o BARRA';
    END IF;
    RETURN NEW;
END; $$;

CREATE OR REPLACE FUNCTION fn_validar_producto_piso()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_categoria TEXT; v_unidad TEXT;
BEGIN
    SELECT fn_catalogo_codigo_valor(p.categoria_id, 'CATEGORIA_PRODUCTO'),
           fn_catalogo_codigo_valor(p.unidad_stock_id, 'UNIDAD_MEDIDA')
      INTO v_categoria, v_unidad FROM productos p WHERE p.id = NEW.producto_id;
    IF v_categoria IS DISTINCT FROM 'PISO_FLOTANTE' THEN
        RAISE EXCEPTION 'productos_piso sólo puede asociarse a PISO_FLOTANTE';
    END IF;
    -- CAJA sólo se tolera en fichas históricas ya existentes. Una ficha nueva exige M2.
    IF TG_OP = 'INSERT' AND v_unidad IS DISTINCT FROM 'M2' THEN
        RAISE EXCEPTION 'Un piso nuevo debe manejar stock en M2';
    END IF;
    IF v_unidad NOT IN ('M2','CAJA') THEN
        RAISE EXCEPTION 'Unidad de piso incompatible: %', v_unidad;
    END IF;
    IF NEW.marca_id IS NOT NULL AND (TG_OP='INSERT' OR NEW.marca_id IS DISTINCT FROM OLD.marca_id)
       AND NOT fn_catalogo_valor_pertenece_activo(NEW.marca_id, 'MARCA') THEN
        RAISE EXCEPTION 'marca_id % no pertenece a MARCA activa', NEW.marca_id;
    END IF;
    RETURN NEW;
END; $$;

CREATE OR REPLACE FUNCTION fn_validar_proforma_detalle()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_tipo TEXT; v_categoria TEXT; v_unidad TEXT; v_producto_activo BOOLEAN;
BEGIN
    IF TG_OP='INSERT' OR NEW.tipo_item_id IS DISTINCT FROM OLD.tipo_item_id THEN
      IF NOT fn_catalogo_valor_pertenece_activo(NEW.tipo_item_id,'TIPO_ITEM') THEN
        RAISE EXCEPTION 'tipo_item_id inválido'; END IF;
    END IF;
    IF TG_OP='INSERT' OR NEW.unidad_id IS DISTINCT FROM OLD.unidad_id THEN
      IF NOT fn_catalogo_valor_pertenece_activo(NEW.unidad_id,'UNIDAD_MEDIDA') THEN
        RAISE EXCEPTION 'unidad_id inválida'; END IF;
    END IF;
    v_tipo := fn_catalogo_codigo_valor(NEW.tipo_item_id,'TIPO_ITEM');
    v_unidad := fn_catalogo_codigo_valor(NEW.unidad_id,'UNIDAD_MEDIDA');
    IF NEW.cantidad <= 0 THEN RAISE EXCEPTION 'cantidad debe ser positiva'; END IF;
    IF v_unidad IN ('PIEZA','JUEGO','BARRA','CAJA') AND NEW.cantidad <> TRUNC(NEW.cantidad) THEN
      RAISE EXCEPTION 'La unidad % requiere cantidad entera', v_unidad;
    END IF;
    IF v_tipo='MUEBLE_MEDIDA' THEN
      IF NEW.producto_id IS NOT NULL OR NEW.familia_producto_id IS NOT NULL THEN
        RAISE EXCEPTION 'MUEBLE_MEDIDA no apunta al catálogo'; END IF;
      IF v_unidad NOT IN ('PIEZA','JUEGO') THEN
        RAISE EXCEPTION 'MUEBLE_MEDIDA se cotiza en PIEZA o JUEGO'; END IF;
      RETURN NEW;
    END IF;
    IF NEW.producto_id IS NULL THEN
      IF NEW.familia_producto_id IS NULL THEN
        RAISE EXCEPTION 'Un ítem de catálogo requiere producto o familia pendiente'; END IF;
      IF NOT EXISTS (SELECT 1 FROM familias_producto f WHERE f.id=NEW.familia_producto_id AND f.activo) THEN
        RAISE EXCEPTION 'Familia pendiente inexistente o inactiva'; END IF;
      RETURN NEW;
    END IF;
    IF NEW.familia_producto_id IS NOT NULL AND NOT EXISTS (
      SELECT 1 FROM productos p WHERE p.id=NEW.producto_id AND p.familia_id=NEW.familia_producto_id
    ) THEN RAISE EXCEPTION 'El producto no pertenece a la familia indicada'; END IF;
    SELECT p.activo, fn_catalogo_codigo_valor(p.categoria_id,'CATEGORIA_PRODUCTO')
      INTO v_producto_activo,v_categoria FROM productos p WHERE p.id=NEW.producto_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Producto % no existe',NEW.producto_id; END IF;
    IF NOT v_producto_activo AND (TG_OP='INSERT' OR NEW.producto_id IS DISTINCT FROM OLD.producto_id) THEN
      RAISE EXCEPTION 'Producto % inactivo',NEW.producto_id; END IF;
    IF v_tipo='SILLA' AND (v_categoria<>'SILLA' OR v_unidad<>'PIEZA') THEN
      RAISE EXCEPTION 'SILLA requiere producto SILLA y PIEZA';
    ELSIF v_tipo='PISO_FLOTANTE' AND (v_categoria<>'PISO_FLOTANTE' OR v_unidad NOT IN ('M2','CAJA')) THEN
      RAISE EXCEPTION 'PISO_FLOTANTE requiere producto de piso y M2 (CAJA sólo histórica)';
    ELSIF v_tipo='OTRO' AND (v_categoria<>'OTRO' OR v_unidad NOT IN ('PIEZA','JUEGO','BARRA')) THEN
      RAISE EXCEPTION 'OTRO requiere PIEZA, JUEGO o BARRA';
    END IF;
    IF TG_OP='INSERT' AND v_tipo='PISO_FLOTANTE' AND v_unidad='CAJA' THEN
      RAISE EXCEPTION 'Una línea nueva de piso debe usar M2'; END IF;
    RETURN NEW;
END; $$;

CREATE OR REPLACE FUNCTION fn_validar_movimiento_stock()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
 v_tipo TEXT; v_tipo_original TEXT; v_producto_original BIGINT;
 v_cantidad_original NUMERIC(14,4); v_pedido_original BIGINT;
 v_requerido NUMERIC(14,4); v_estado_pedido TEXT; v_unidad TEXT;
BEGIN
 IF NOT fn_catalogo_valor_pertenece_activo(NEW.tipo_movimiento_id,'TIPO_MOVIMIENTO') THEN
   RAISE EXCEPTION 'tipo_movimiento_id inválido'; END IF;
 SELECT fn_catalogo_codigo_valor(p.unidad_stock_id,'UNIDAD_MEDIDA') INTO v_unidad
 FROM productos p WHERE p.id=NEW.producto_id;
 IF v_unidad IN ('PIEZA','JUEGO','BARRA','CAJA') AND NEW.cantidad<>TRUNC(NEW.cantidad) THEN
   RAISE EXCEPTION 'La unidad % requiere movimiento entero',v_unidad; END IF;
 v_tipo:=fn_catalogo_codigo_valor(NEW.tipo_movimiento_id,'TIPO_MOVIMIENTO');
 IF v_tipo='VENTA' THEN
   IF NEW.pedido_id IS NULL OR NEW.movimiento_referencia_id IS NOT NULL OR NEW.cantidad>=0 THEN
     RAISE EXCEPTION 'VENTA requiere pedido, cantidad negativa y ninguna referencia'; END IF;
   SELECT fn_catalogo_codigo_valor(pe.estado_id,'ESTADO_PEDIDO') INTO v_estado_pedido FROM pedidos pe WHERE pe.id=NEW.pedido_id;
   IF v_estado_pedido IS DISTINCT FROM 'CONFIRMADO' THEN RAISE EXCEPTION 'VENTA requiere pedido CONFIRMADO'; END IF;
   SELECT SUM(pd.cantidad) INTO v_requerido FROM pedidos pe JOIN proformas_detalle pd ON pd.proforma_id=pe.proforma_id
    WHERE pe.id=NEW.pedido_id AND pd.producto_id=NEW.producto_id;
   IF v_requerido IS NULL OR NEW.cantidad<>-v_requerido THEN RAISE EXCEPTION 'VENTA no coincide exactamente con pedido'; END IF;
 ELSIF v_tipo='CARGA_INICIAL' THEN
   IF NEW.pedido_id IS NOT NULL OR NEW.movimiento_referencia_id IS NOT NULL OR NEW.cantidad<=0 THEN RAISE EXCEPTION 'CARGA_INICIAL inválida'; END IF;
 ELSIF v_tipo='AJUSTE' THEN
   IF NEW.pedido_id IS NOT NULL OR NULLIF(BTRIM(NEW.observaciones),'') IS NULL THEN RAISE EXCEPTION 'AJUSTE requiere motivo y no pedido'; END IF;
   IF NEW.movimiento_referencia_id IS NOT NULL THEN
    SELECT ms.producto_id INTO v_producto_original FROM movimientos_stock ms WHERE ms.id=NEW.movimiento_referencia_id;
    IF NOT FOUND OR v_producto_original<>NEW.producto_id THEN RAISE EXCEPTION 'Referencia de AJUSTE inválida'; END IF;
   END IF;
 ELSIF v_tipo='REVERSA_VENTA' THEN
   IF NEW.pedido_id IS NOT NULL OR NEW.movimiento_referencia_id IS NULL OR NEW.cantidad<=0 THEN RAISE EXCEPTION 'REVERSA_VENTA inválida'; END IF;
   SELECT fn_catalogo_codigo_valor(ms.tipo_movimiento_id,'TIPO_MOVIMIENTO'),ms.producto_id,ms.cantidad,ms.pedido_id
    INTO v_tipo_original,v_producto_original,v_cantidad_original,v_pedido_original FROM movimientos_stock ms WHERE ms.id=NEW.movimiento_referencia_id FOR UPDATE;
   IF NOT FOUND OR v_tipo_original IS DISTINCT FROM 'VENTA' OR v_producto_original<>NEW.producto_id OR NEW.cantidad<>ABS(v_cantidad_original) THEN
    RAISE EXCEPTION 'REVERSA_VENTA no coincide exactamente con VENTA'; END IF;
   IF EXISTS(SELECT 1 FROM movimientos_stock r WHERE r.movimiento_referencia_id=NEW.movimiento_referencia_id
      AND fn_catalogo_valor_es(r.tipo_movimiento_id,'TIPO_MOVIMIENTO','REVERSA_VENTA')) THEN RAISE EXCEPTION 'VENTA ya reversada'; END IF;
 ELSE RAISE EXCEPTION 'Tipo movimiento no soportado'; END IF;
 RETURN NEW;
END; $$;

CREATE OR REPLACE FUNCTION fn_confirmar_pedido_descontar_stock()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_tipo_venta BIGINT; v_stock NUMERIC(14,4); v_requerido NUMERIC(14,4); v_producto_id BIGINT;
BEGIN
 IF NOT fn_catalogo_valor_es(NEW.estado_id,'ESTADO_PEDIDO','CONFIRMADO') THEN RETURN NEW; END IF;
 IF EXISTS(SELECT 1 FROM proformas_detalle pd WHERE pd.proforma_id=NEW.proforma_id AND pd.producto_id IS NULL
    AND NOT fn_catalogo_valor_es(pd.tipo_item_id,'TIPO_ITEM','MUEBLE_MEDIDA')) THEN
   RAISE EXCEPTION 'No se puede aprobar: existe una variante de catálogo pendiente'; END IF;
 v_tipo_venta:=fn_catalogo_id('TIPO_MOVIMIENTO','VENTA');
 FOR v_producto_id,v_requerido IN SELECT pd.producto_id,SUM(pd.cantidad) FROM proformas_detalle pd
   WHERE pd.proforma_id=NEW.proforma_id AND pd.producto_id IS NOT NULL GROUP BY pd.producto_id ORDER BY pd.producto_id
 LOOP
   SELECT stock INTO v_stock FROM productos WHERE id=v_producto_id FOR UPDATE;
   IF NOT FOUND OR v_stock<v_requerido THEN RAISE EXCEPTION 'Stock insuficiente para producto %. Disponible %, requerido %',v_producto_id,v_stock,v_requerido; END IF;
 END LOOP;
 FOR v_producto_id,v_requerido IN SELECT pd.producto_id,SUM(pd.cantidad) FROM proformas_detalle pd
   WHERE pd.proforma_id=NEW.proforma_id AND pd.producto_id IS NOT NULL GROUP BY pd.producto_id ORDER BY pd.producto_id
 LOOP
  INSERT INTO movimientos_stock(producto_id,tipo_movimiento_id,cantidad,pedido_id,observaciones,created_by_id)
  VALUES(v_producto_id,v_tipo_venta,-v_requerido,NEW.id,'Salida por aprobación de proforma / pedido #'||NEW.id,COALESCE(NEW.updated_by_id,NEW.created_by_id));
 END LOOP;
 RETURN NEW;
END; $$;

CREATE OR REPLACE FUNCTION fn_preparar_proforma_para_emision()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE v_nuevo_estado TEXT; v_faltantes INTEGER; v_cliente clientes%ROWTYPE;
BEGIN
 v_nuevo_estado:=fn_catalogo_codigo_valor(NEW.estado_id,'ESTADO_PROFORMA');
 IF TG_OP='UPDATE' AND fn_catalogo_valor_es(OLD.estado_id,'ESTADO_PROFORMA','APROBADA') THEN
   IF NEW IS DISTINCT FROM OLD THEN RAISE EXCEPTION 'Una proforma APROBADA es inmutable'; END IF;
 END IF;
 IF TG_OP='UPDATE' AND NOT fn_catalogo_valor_es(OLD.estado_id,'ESTADO_PROFORMA','BORRADOR')
    AND NEW.cliente_id IS DISTINCT FROM OLD.cliente_id THEN RAISE EXCEPTION 'Cliente congelado tras emisión'; END IF;
 IF TG_OP='UPDATE' AND OLD.estado_id IS NOT DISTINCT FROM NEW.estado_id THEN RETURN NEW; END IF;
 IF v_nuevo_estado IN ('EN_REVISION','ENVIADA','APROBADA') THEN
  IF NEW.cliente_id IS NULL THEN RAISE EXCEPTION 'Una proforma emitida requiere cliente'; END IF;
  SELECT * INTO v_cliente FROM clientes WHERE id=NEW.cliente_id AND activo=TRUE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Cliente inexistente o inactivo'; END IF;
  IF NOT EXISTS(SELECT 1 FROM proformas_detalle WHERE proforma_id=NEW.id) THEN RAISE EXCEPTION 'La proforma requiere detalles'; END IF;
  IF NEW.total<=0 THEN RAISE EXCEPTION 'La proforma requiere total positivo'; END IF;
  SELECT COUNT(*) INTO v_faltantes FROM proformas_detalle pd WHERE pd.proforma_id=NEW.id
    AND fn_catalogo_valor_es(pd.tipo_item_id,'TIPO_ITEM','MUEBLE_MEDIDA')
    AND NOT EXISTS(SELECT 1 FROM especificaciones_mueble em WHERE em.proforma_detalle_id=pd.id);
  IF v_faltantes>0 THEN RAISE EXCEPTION 'Hay muebles sin especificación'; END IF;
  IF NEW.cliente_nombre_snapshot IS NULL THEN
    NEW.cliente_nombre_snapshot:=NULLIF(BTRIM(CONCAT_WS(' ',v_cliente.nombres,v_cliente.apellidos)),'');
    NEW.cliente_empresa_snapshot:=v_cliente.empresa; NEW.cliente_celular_snapshot:=v_cliente.celular; NEW.cliente_direccion_snapshot:=v_cliente.direccion;
  END IF;
 END IF;
 RETURN NEW;
END; $$;
'''


class Migration(migrations.Migration):
    dependencies = [
        ("catalogo", "0008_alter_producto_stock_familiaproducto_and_more"),
        ("movimientos_stock", "0004_alter_movimientostock_cantidad"),
        ("proformas", "0005_detalleproforma_familia_producto_and_more"),
    ]
    operations = [migrations.RunSQL(SQL, reverse_sql=migrations.RunSQL.noop)]
