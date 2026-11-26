from rest_framework import serializers


class EstadoConteoSerializer(serializers.Serializer):
    codigo = serializers.CharField()
    nombre = serializers.CharField()
    cantidad = serializers.IntegerField()


class VariacionEnteroSerializer(serializers.Serializer):
    actual = serializers.IntegerField()
    anterior = serializers.IntegerField(allow_null=True)
    diferencia = serializers.IntegerField(allow_null=True)
    variacion_porcentaje = serializers.DecimalField(max_digits=8, decimal_places=2, allow_null=True)


class RangoPeriodoSerializer(serializers.Serializer):
    fecha_desde = serializers.DateField()
    fecha_hasta = serializers.DateField()


class ComparacionPeriodoComercialSerializer(serializers.Serializer):
    periodo_anterior = RangoPeriodoSerializer()
    proformas_formalizadas = VariacionEnteroSerializer()
    borradores = VariacionEnteroSerializer()
    pedidos_generados = VariacionEnteroSerializer()
    pedidos_confirmados_periodo = VariacionEnteroSerializer()
    pedidos_no_cancelados = VariacionEnteroSerializer()


class CoberturaFormalizacionSerializer(serializers.Serializer):
    con_marca_temporal = serializers.IntegerField()
    aproximadas_por_fecha = serializers.IntegerField()
    anuladas_sin_evidencia_formalizacion = serializers.IntegerField()


class IndicadoresComercialesSerializer(serializers.Serializer):
    total_proformas = serializers.IntegerField()
    borradores = serializers.IntegerField()
    proformas_formalizadas = serializers.IntegerField()
    pedidos_generados = serializers.IntegerField()
    pedidos_derivados_cohorte = serializers.IntegerField()
    pedidos_no_cancelados_cohorte = serializers.IntegerField()
    pedidos_confirmados_periodo = serializers.IntegerField()
    pedidos_no_cancelados = serializers.IntegerField()
    tasa_conversion_cohorte = serializers.DecimalField(
        max_digits=7, decimal_places=2, allow_null=True
    )
    cobertura_formalizacion = CoberturaFormalizacionSerializer()
    distribucion_proformas_estado = EstadoConteoSerializer(many=True)
    distribucion_pedidos_estado = EstadoConteoSerializer(many=True)
    comparaciones_periodo_anterior = ComparacionPeriodoComercialSerializer(allow_null=True)
    limitaciones = serializers.ListField(child=serializers.CharField())


class PuntoConteoComercialSerializer(serializers.Serializer):
    periodo = serializers.CharField()
    proformas_formalizadas = serializers.IntegerField()
    pedidos_generados = serializers.IntegerField()


class PuntoMonetarioComercialSerializer(serializers.Serializer):
    periodo = serializers.CharField()
    importe_pedidos_no_cancelados = serializers.DecimalField(max_digits=14, decimal_places=2)
    cobros_registrados = serializers.DecimalField(max_digits=14, decimal_places=2)


class SerieMonetariaComercialSerializer(serializers.Serializer):
    moneda = serializers.CharField()
    puntos = PuntoMonetarioComercialSerializer(many=True)


class EvolucionComercialSerializer(serializers.Serializer):
    granularidad = serializers.ChoiceField(choices=["diaria", "semanal", "mensual"])
    puntos_conteo = PuntoConteoComercialSerializer(many=True)
    series_monetarias = SerieMonetariaComercialSerializer(many=True)


class MontoMonedaVendedorSerializer(serializers.Serializer):
    moneda = serializers.CharField()
    importe_pedidos_no_cancelados = serializers.DecimalField(max_digits=14, decimal_places=2)
    cobros_validos = serializers.DecimalField(max_digits=14, decimal_places=2)
    saldo_pendiente = serializers.DecimalField(max_digits=14, decimal_places=2)


class ComparacionVendedorSerializer(serializers.Serializer):
    vendedor_id = serializers.IntegerField()
    vendedor_nombre = serializers.CharField()
    proformas_formalizadas = serializers.IntegerField()
    pedidos_generados = serializers.IntegerField()
    conversion_comercial = serializers.DecimalField(max_digits=7, decimal_places=2, allow_null=True)
    vencidas_no_concretadas = serializers.IntegerField()
    vencidas = serializers.IntegerField()
    no_concretadas = serializers.IntegerField()
    montos_por_moneda = MontoMonedaVendedorSerializer(many=True)


class ResumenFinancieroMonedaSerializer(serializers.Serializer):
    moneda = serializers.CharField()
    importe_pedidos_no_cancelados = serializers.DecimalField(max_digits=14, decimal_places=2)
    cobros_validos_periodo = serializers.DecimalField(max_digits=14, decimal_places=2)
    cobros_acumulados_cartera_vigente = serializers.DecimalField(max_digits=14, decimal_places=2)
    saldo_pendiente = serializers.DecimalField(max_digits=14, decimal_places=2)
    porcentaje_cobrado = serializers.DecimalField(max_digits=7, decimal_places=2, allow_null=True)


class CobrosPedidosCanceladosSerializer(serializers.Serializer):
    moneda = serializers.CharField()
    cantidad_recibos = serializers.IntegerField()
    importe = serializers.DecimalField(max_digits=14, decimal_places=2)


class ResumenFinancieroVendedorSerializer(serializers.Serializer):
    por_moneda = ResumenFinancieroMonedaSerializer(many=True)
    cobros_pedidos_cancelados = CobrosPedidosCanceladosSerializer(many=True)


class PedidoEntregadoSaldoSerializer(serializers.Serializer):
    pedido_id = serializers.IntegerField()
    proforma_id = serializers.IntegerField()
    proforma_numero = serializers.IntegerField()
    cliente_id = serializers.IntegerField(allow_null=True)
    cliente_nombre = serializers.CharField()
    moneda = serializers.CharField()
    total_pedido = serializers.DecimalField(max_digits=14, decimal_places=2)
    cobrado = serializers.DecimalField(max_digits=14, decimal_places=2)
    saldo_pendiente = serializers.DecimalField(max_digits=14, decimal_places=2)
    fecha_entrega_efectiva = serializers.DateField(allow_null=True)


class PaginacionPedidosEntregadosSaldoSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    results = PedidoEntregadoSaldoSerializer(many=True)


class ClienteMayorSaldoSerializer(serializers.Serializer):
    cliente_id = serializers.IntegerField(allow_null=True)
    cliente_nombre = serializers.CharField()
    moneda = serializers.CharField()
    cantidad_pedidos = serializers.IntegerField()
    saldo_pendiente = serializers.DecimalField(max_digits=14, decimal_places=2)


class ClientesMayorSaldoMonedaSerializer(serializers.Serializer):
    moneda = serializers.CharField()
    clientes = ClienteMayorSaldoSerializer(many=True)


class PuntoCobroSerializer(serializers.Serializer):
    periodo = serializers.CharField()
    cantidad_recibos = serializers.IntegerField()
    monto_cobrado = serializers.DecimalField(max_digits=14, decimal_places=2)


class EvolucionCobrosMonedaSerializer(serializers.Serializer):
    moneda = serializers.CharField()
    puntos = PuntoCobroSerializer(many=True)


class FinanzasAdminSerializer(serializers.Serializer):
    por_moneda = ResumenFinancieroMonedaSerializer(many=True)
    cobros_pedidos_cancelados = CobrosPedidosCanceladosSerializer(many=True)
    pedidos_entregados_con_saldo = PaginacionPedidosEntregadosSaldoSerializer()
    clientes_mayores_saldos_por_moneda = ClientesMayorSaldoMonedaSerializer(many=True)
    evolucion_cobros = EvolucionCobrosMonedaSerializer(many=True)


class ProduccionAdminSerializer(serializers.Serializer):
    ordenes_fabricacion_total = serializers.IntegerField()
    ordenes_fabricacion_por_estado = EstadoConteoSerializer(many=True)
    ordenes_tecnicas_total = serializers.IntegerField()
    ordenes_tecnicas_por_estado = EstadoConteoSerializer(many=True)
    fabricaciones_activas = serializers.IntegerField()
    entregas_proximas = serializers.IntegerField()
    entregas_retrasadas = serializers.IntegerField()
    entregas_efectivas = serializers.IntegerField()
    entregas_evaluables_plazo = serializers.IntegerField()
    entregas_en_plazo = serializers.IntegerField()
    cumplimiento_entregas_porcentaje = serializers.DecimalField(
        max_digits=7, decimal_places=2, allow_null=True
    )


class ResumenInventarioSerializer(serializers.Serializer):
    total_activos = serializers.IntegerField()
    con_stock = serializers.IntegerField()
    bajo_pedido = serializers.IntegerField()
    stock_bajo = serializers.IntegerField()
    agotados = serializers.IntegerField()
    sin_stock_minimo = serializers.IntegerField()


class InventarioCategoriaSerializer(serializers.Serializer):
    categoria_codigo = serializers.CharField()
    categoria_nombre = serializers.CharField()
    total_activos = serializers.IntegerField()
    con_stock = serializers.IntegerField()
    bajo_pedido = serializers.IntegerField()
    stock_bajo = serializers.IntegerField()
    agotados = serializers.IntegerField()
    sin_stock_minimo = serializers.IntegerField()


class ExistenciaUnidadSerializer(serializers.Serializer):
    unidad_codigo = serializers.CharField()
    unidad_nombre = serializers.CharField()
    cantidad_productos = serializers.IntegerField()
    stock_total = serializers.DecimalField(max_digits=14, decimal_places=4)


class MovimientoStockUnidadSerializer(serializers.Serializer):
    unidad_codigo = serializers.CharField()
    unidad_nombre = serializers.CharField()
    total_movimientos = serializers.IntegerField()
    entradas_conteo = serializers.IntegerField()
    entradas_cantidad = serializers.DecimalField(max_digits=14, decimal_places=4)
    salidas_conteo = serializers.IntegerField()
    salidas_cantidad_absoluta = serializers.DecimalField(max_digits=14, decimal_places=4)
    reversiones_conteo = serializers.IntegerField()
    reversiones_cantidad = serializers.DecimalField(max_digits=14, decimal_places=4)


class ProductoMasVendidoSerializer(serializers.Serializer):
    producto_id = serializers.IntegerField()
    sku = serializers.CharField(allow_null=True)
    nombre = serializers.CharField()
    categoria_codigo = serializers.CharField()
    categoria_nombre = serializers.CharField()
    unidad_codigo = serializers.CharField()
    unidad_nombre = serializers.CharField()
    moneda = serializers.CharField()
    cantidad_vendida = serializers.DecimalField(max_digits=14, decimal_places=4)
    importe_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    pedidos_count = serializers.IntegerField()


class PaginacionMasVendidosSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    results = ProductoMasVendidoSerializer(many=True)


class InventarioAdminSerializer(serializers.Serializer):
    resumen = ResumenInventarioSerializer()
    por_categoria = InventarioCategoriaSerializer(many=True)
    existencias_por_unidad = ExistenciaUnidadSerializer(many=True)
    movimientos_por_unidad = MovimientoStockUnidadSerializer(many=True)
    mas_vendidos = PaginacionMasVendidosSerializer()


class AlertaProformaVencerSerializer(serializers.Serializer):
    proforma_id = serializers.IntegerField()
    numero = serializers.IntegerField()
    cliente_nombre = serializers.CharField()
    vendedor_nombre = serializers.CharField()
    fecha_vencimiento = serializers.DateField()
    dias_restantes = serializers.IntegerField()
    moneda = serializers.CharField()
    total = serializers.DecimalField(max_digits=14, decimal_places=2)


class AlertaPedidoRetrasadoSerializer(serializers.Serializer):
    pedido_id = serializers.IntegerField()
    proforma_numero = serializers.IntegerField()
    cliente_nombre = serializers.CharField()
    vendedor_nombre = serializers.CharField()
    estado_codigo = serializers.CharField()
    fecha_entrega_prevista = serializers.DateField()
    dias_retraso = serializers.IntegerField()


class AlertaFabricacionRetrasadaSerializer(serializers.Serializer):
    orden_trabajo_id = serializers.IntegerField()
    numero_ot = serializers.IntegerField()
    cliente_nombre = serializers.CharField()
    estado_codigo = serializers.CharField()
    fecha_entrega_prevista = serializers.DateField()
    dias_retraso = serializers.IntegerField()


class AlertaSaldoEntregadoSerializer(serializers.Serializer):
    pedido_id = serializers.IntegerField()
    proforma_numero = serializers.IntegerField()
    cliente_nombre = serializers.CharField()
    moneda = serializers.CharField()
    saldo_pendiente = serializers.DecimalField(max_digits=14, decimal_places=2)
    fecha_entrega_efectiva = serializers.DateField(allow_null=True)


class AlertaProductoStockBajoSerializer(serializers.Serializer):
    producto_id = serializers.IntegerField()
    sku = serializers.CharField(allow_null=True)
    nombre = serializers.CharField()
    categoria_codigo = serializers.CharField()
    stock = serializers.DecimalField(max_digits=14, decimal_places=4)
    stock_minimo = serializers.DecimalField(max_digits=14, decimal_places=4, allow_null=True)
    unidad_codigo = serializers.CharField()
    estado_stock = serializers.CharField()


class SaldosEntregadosMonedaSerializer(serializers.Serializer):
    moneda = serializers.CharField()
    pedidos = AlertaSaldoEntregadoSerializer(many=True)


class TotalesAlertasAdminSerializer(serializers.Serializer):
    proformas_proximas_vencer = serializers.IntegerField()
    pedidos_retrasados = serializers.IntegerField()
    fabricaciones_retrasadas = serializers.IntegerField()
    saldos_pedidos_entregados = serializers.IntegerField()
    productos_stock_bajo = serializers.IntegerField()
    productos_sin_stock_minimo = serializers.IntegerField()


class AlertasPrioritariasAdminSerializer(serializers.Serializer):
    totales = TotalesAlertasAdminSerializer()
    proformas_proximas_vencer = AlertaProformaVencerSerializer(many=True)
    pedidos_retrasados = AlertaPedidoRetrasadoSerializer(many=True)
    fabricaciones_retrasadas = AlertaFabricacionRetrasadaSerializer(many=True)
    saldos_pedidos_entregados_por_moneda = SaldosEntregadosMonedaSerializer(many=True)
    productos_stock_bajo = AlertaProductoStockBajoSerializer(many=True)
    productos_sin_stock_minimo = AlertaProductoStockBajoSerializer(many=True)


class DashboardAdminResumenSerializer(serializers.Serializer):
    fecha_referencia = serializers.DateField()
    comercial = IndicadoresComercialesSerializer()
    finanzas = ResumenFinancieroVendedorSerializer()
    produccion = ProduccionAdminSerializer()
    inventario = ResumenInventarioSerializer()
    alertas = AlertasPrioritariasAdminSerializer()


class DashboardAdminComercialSerializer(serializers.Serializer):
    fecha_referencia = serializers.DateField()
    indicadores = IndicadoresComercialesSerializer()
    evolucion = EvolucionComercialSerializer()
    vendedores = ComparacionVendedorSerializer(many=True)


class ElementoAgendaComercialSerializer(serializers.Serializer):
    tipo_documento = serializers.ChoiceField(choices=["PROFORMA", "PEDIDO"])
    documento_id = serializers.IntegerField()
    proforma_id = serializers.IntegerField()
    pedido_id = serializers.IntegerField(allow_null=True)
    numero_documento = serializers.IntegerField()
    cliente_nombre = serializers.CharField()
    fecha = serializers.DateField()
    estado_codigo = serializers.CharField()
    estado_nombre = serializers.CharField()
    prioridad = serializers.ChoiceField(choices=["CRITICA", "ALTA", "MEDIA"])
    categoria_agenda = serializers.CharField()
    dias_diferencia = serializers.IntegerField(allow_null=True)
    moneda = serializers.CharField(required=False)
    saldo_pendiente = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)


class PaginacionAgendaComercialSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    results = ElementoAgendaComercialSerializer(many=True)


class ResumenConteosAgendaSerializer(serializers.Serializer):
    proformas_proximas_vencer = serializers.IntegerField()
    proformas_pendientes_revision = serializers.IntegerField()
    proformas_enviadas = serializers.IntegerField()
    pedidos_listos_entrega = serializers.IntegerField()
    pedidos_con_saldo_pendiente = serializers.IntegerField()
    entregas_proximas = serializers.IntegerField()
    entregas_retrasadas = serializers.IntegerField()


class AgendaComercialSerializer(serializers.Serializer):
    resumen_conteos = ResumenConteosAgendaSerializer()
    elementos = PaginacionAgendaComercialSerializer()


class ResumenDisponibilidadSerializer(serializers.Serializer):
    total_activos = serializers.IntegerField()
    con_stock_disponible = serializers.IntegerField()
    con_stock_bajo = serializers.IntegerField()
    con_stock_agotado = serializers.IntegerField()
    bajo_pedido = serializers.IntegerField()
    sin_stock_minimo = serializers.IntegerField()


class ProductoDisponibilidadSerializer(serializers.Serializer):
    producto_id = serializers.IntegerField()
    sku = serializers.CharField(allow_null=True)
    nombre = serializers.CharField()
    categoria_codigo = serializers.CharField()
    categoria_nombre = serializers.CharField()
    modalidad_abastecimiento = serializers.CharField()
    stock = serializers.DecimalField(max_digits=14, decimal_places=4)
    stock_minimo = serializers.DecimalField(max_digits=14, decimal_places=4, allow_null=True)
    unidad_codigo = serializers.CharField()
    unidad_nombre = serializers.CharField()
    estado_disponibilidad = serializers.CharField()
    imagen_principal = serializers.JSONField(allow_null=True, required=False)


class PaginacionDisponibilidadProductosSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    results = ProductoDisponibilidadSerializer(many=True)


class DisponibilidadCategoriaSerializer(serializers.Serializer):
    categoria_codigo = serializers.CharField()
    categoria_nombre = serializers.CharField()
    total_activos = serializers.IntegerField()
    con_stock_disponible = serializers.IntegerField()
    con_stock_bajo = serializers.IntegerField()
    con_stock_agotado = serializers.IntegerField()
    bajo_pedido = serializers.IntegerField()


class DisponibilidadComercialSerializer(serializers.Serializer):
    resumen = ResumenDisponibilidadSerializer()
    por_categoria = DisponibilidadCategoriaSerializer(many=True)
    productos = PaginacionDisponibilidadProductosSerializer()


class DashboardTiendaResumenSerializer(serializers.Serializer):
    fecha_referencia = serializers.DateField()
    vendedor_id = serializers.IntegerField()
    indicadores = IndicadoresComercialesSerializer()
    finanzas = ResumenFinancieroVendedorSerializer()
    evolucion = EvolucionComercialSerializer()


class DashboardTiendaSeguimientoSerializer(serializers.Serializer):
    fecha_referencia = serializers.DateField()
    vendedor_id = serializers.IntegerField()
    agenda = AgendaComercialSerializer()
    disponibilidad = DisponibilidadComercialSerializer()


class IndicadoresTallerSerializer(serializers.Serializer):
    pendientes = serializers.IntegerField()
    en_proceso = serializers.IntegerField()
    terminadas = serializers.IntegerField()
    canceladas = serializers.IntegerField()
    carga_activa_fabricacion = serializers.IntegerField()
    fabricaciones_iniciadas_periodo = serializers.IntegerField()
    fabricaciones_terminadas_periodo = serializers.IntegerField()
    tiempo_promedio_fabricacion_horas = serializers.FloatField(allow_null=True)
    tiempo_promedio_fabricacion_dias = serializers.FloatField(allow_null=True)
    ordenes_con_duracion_medible = serializers.IntegerField()
    antiguedad_promedio_activas_dias = serializers.FloatField(allow_null=True)
    antiguedad_maxima_activas_dias = serializers.IntegerField(allow_null=True)
    ordenes_con_antiguedad_medible = serializers.IntegerField()
    entregas_proximas = serializers.IntegerField()
    entregas_retrasadas = serializers.IntegerField()
    entregas_efectivas = serializers.IntegerField()
    entregas_evaluables_plazo = serializers.IntegerField()
    entregas_en_plazo = serializers.IntegerField()
    cumplimiento_entregas_porcentaje = serializers.DecimalField(
        max_digits=7, decimal_places=2, allow_null=True
    )


class MuebleSolicitadoTallerSerializer(serializers.Serializer):
    nombre = serializers.CharField()
    tipo_mueble = serializers.CharField(allow_null=True)
    cantidad = serializers.DecimalField(max_digits=14, decimal_places=4)


class ElementoColaPrioridadTallerSerializer(serializers.Serializer):
    orden_trabajo_id = serializers.IntegerField()
    numero_ot = serializers.IntegerField()
    cliente_nombre = serializers.CharField()
    vendedor_nombre = serializers.CharField()
    muebles_solicitados = MuebleSolicitadoTallerSerializer(many=True)
    estado_codigo = serializers.CharField()
    estado_nombre = serializers.CharField()
    pedido_estado_codigo = serializers.CharField()
    fecha_prevista = serializers.DateField(allow_null=True)
    dias_diferencia = serializers.IntegerField(allow_null=True)
    categoria_prioridad = serializers.CharField()


class ResumenColaPrioridadTallerSerializer(serializers.Serializer):
    entrega_vencida = serializers.IntegerField()
    entrega_proxima = serializers.IntegerField()
    pendiente_iniciar = serializers.IntegerField()
    terminada_pendiente_autorizacion = serializers.IntegerField()
    sin_fecha_entrega = serializers.IntegerField()


class PaginacionColaPrioridadTallerSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    resumen_conteos = ResumenColaPrioridadTallerSerializer()
    results = ElementoColaPrioridadTallerSerializer(many=True)


class DashboardTallerResumenSerializer(serializers.Serializer):
    fecha_referencia = serializers.DateField()
    indicadores = IndicadoresTallerSerializer()
    cola_prioridades = PaginacionColaPrioridadTallerSerializer()


class EventoCalendarioTallerSerializer(serializers.Serializer):
    orden_trabajo_id = serializers.IntegerField()
    numero_ot = serializers.IntegerField()
    tipo_evento = serializers.ChoiceField(
        choices=[
            "INICIO_FABRICACION",
            "FIN_FABRICACION",
            "ENTREGA_PREVISTA",
            "ENTREGA_EFECTIVA",
        ]
    )
    naturaleza = serializers.ChoiceField(choices=["EFECTIVA", "PLANIFICADA"])
    fecha = serializers.DateField()
    fecha_hora = serializers.DateTimeField(allow_null=True)
    cliente_nombre = serializers.CharField()
    estado_codigo = serializers.CharField()


class ResumenNaturalezaCalendarioTallerSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    planificados = serializers.IntegerField()
    efectivos = serializers.IntegerField()


class PaginacionCalendarioTallerSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    resumen_naturaleza = ResumenNaturalezaCalendarioTallerSerializer()
    results = EventoCalendarioTallerSerializer(many=True)


class PuntoEvolucionFabricacionSerializer(serializers.Serializer):
    periodo = serializers.CharField()
    iniciadas = serializers.IntegerField()
    terminadas = serializers.IntegerField()


class MuebleFabricadoTipoSerializer(serializers.Serializer):
    tipo_mueble_codigo = serializers.CharField()
    tipo_mueble_nombre = serializers.CharField()
    cantidad_fabricada = serializers.DecimalField(max_digits=14, decimal_places=4)
    ordenes_count = serializers.IntegerField()


class AnalisisFabricacionSerializer(serializers.Serializer):
    granularidad = serializers.ChoiceField(choices=["diaria", "semanal", "mensual"])
    evolucion_fabricaciones = PuntoEvolucionFabricacionSerializer(many=True)
    duracion_promedio_horas = serializers.FloatField(allow_null=True)
    duracion_promedio_dias = serializers.FloatField(allow_null=True)
    ordenes_con_duracion_medible = serializers.IntegerField()
    muebles_fabricados_por_tipo = MuebleFabricadoTipoSerializer(many=True)
    distribucion_ordenes_estado = EstadoConteoSerializer(many=True)


class DashboardTallerPlanificacionSerializer(serializers.Serializer):
    fecha_referencia = serializers.DateField()
    calendario_eventos = PaginacionCalendarioTallerSerializer()
    analisis_fabricacion = AnalisisFabricacionSerializer()
