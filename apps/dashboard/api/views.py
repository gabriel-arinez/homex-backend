from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.dashboard.api.serializers import (
    DashboardAdminComercialSerializer,
    DashboardAdminResumenSerializer,
    DashboardTallerPlanificacionSerializer,
    DashboardTallerResumenSerializer,
    DashboardTiendaResumenSerializer,
    DashboardTiendaSeguimientoSerializer,
    FinanzasAdminSerializer,
    InventarioAdminSerializer,
)
from apps.dashboard.filters import parse_dashboard_filters
from apps.dashboard.permissions import (
    EsAdministradorComercial,
    EsEncargadoTienda,
    EsJefeTaller,
)
from apps.dashboard.services import (
    fecha_referencia_analitica,
    obtener_agenda_comercial,
    obtener_alertas_prioritarias_admin,
    obtener_cola_prioridades_taller,
    obtener_comparacion_vendedores,
    obtener_dashboard_taller,
    obtener_disponibilidad_comercial,
    obtener_evolucion_comercial,
    obtener_finanzas_admin,
    obtener_indicadores_comerciales,
    obtener_inventario_admin,
    obtener_planificacion_taller,
    obtener_resumen_financiero_vendedor,
    obtener_resumen_produccion_admin,
)

PARAM_FECHA_DESDE = OpenApiParameter("fecha_desde", OpenApiTypes.DATE, OpenApiParameter.QUERY)
PARAM_FECHA_HASTA = OpenApiParameter("fecha_hasta", OpenApiTypes.DATE, OpenApiParameter.QUERY)
PARAM_GRANULARIDAD = OpenApiParameter(
    "granularidad",
    OpenApiTypes.STR,
    OpenApiParameter.QUERY,
    enum=["diaria", "semanal", "mensual"],
)
PARAM_VENDEDOR = OpenApiParameter("vendedor", OpenApiTypes.INT, OpenApiParameter.QUERY)
PARAM_MONEDA = OpenApiParameter("moneda", OpenApiTypes.STR, OpenApiParameter.QUERY)
PARAM_CATEGORIA = OpenApiParameter("categoria", OpenApiTypes.STR, OpenApiParameter.QUERY)
PARAM_ESTADO_COMERCIAL = OpenApiParameter(
    "estado_comercial", OpenApiTypes.STR, OpenApiParameter.QUERY
)
PARAM_ESTADO_FABRICACION = OpenApiParameter(
    "estado_fabricacion", OpenApiTypes.STR, OpenApiParameter.QUERY
)
PARAM_TIPO_MUEBLE = OpenApiParameter("tipo_mueble", OpenApiTypes.STR, OpenApiParameter.QUERY)
PARAM_ENTREGA_DESDE = OpenApiParameter("entrega_desde", OpenApiTypes.DATE, OpenApiParameter.QUERY)
PARAM_ENTREGA_HASTA = OpenApiParameter("entrega_hasta", OpenApiTypes.DATE, OpenApiParameter.QUERY)
PARAM_PAGE = OpenApiParameter("page", OpenApiTypes.INT, OpenApiParameter.QUERY)
PARAM_PAGE_SIZE = OpenApiParameter("page_size", OpenApiTypes.INT, OpenApiParameter.QUERY)


class DashboardAdminResumenView(APIView):
    permission_classes = [EsAdministradorComercial]

    @extend_schema(
        tags=["dashboard"],
        parameters=[
            PARAM_FECHA_DESDE,
            PARAM_FECHA_HASTA,
            PARAM_VENDEDOR,
            PARAM_MONEDA,
            PARAM_CATEGORIA,
            PARAM_ESTADO_COMERCIAL,
            PARAM_ESTADO_FABRICACION,
            PARAM_ENTREGA_DESDE,
            PARAM_ENTREGA_HASTA,
            PARAM_PAGE_SIZE,
        ],
        responses={200: DashboardAdminResumenSerializer},
    )
    def get(self, request):
        filtros = parse_dashboard_filters(request, scope="admin")
        inv = obtener_inventario_admin(filtros)
        payload = {
            "fecha_referencia": fecha_referencia_analitica().isoformat(),
            "comercial": obtener_indicadores_comerciales(filtros),
            "finanzas": obtener_resumen_financiero_vendedor(
                filtros, vendedor_id=filtros.vendedor_id
            ),
            "produccion": obtener_resumen_produccion_admin(filtros),
            "inventario": inv["resumen"],
            "alertas": obtener_alertas_prioritarias_admin(filtros),
        }
        return Response(payload)


class DashboardAdminComercialView(APIView):
    permission_classes = [EsAdministradorComercial]

    @extend_schema(
        tags=["dashboard"],
        parameters=[
            PARAM_FECHA_DESDE,
            PARAM_FECHA_HASTA,
            PARAM_GRANULARIDAD,
            PARAM_VENDEDOR,
            PARAM_MONEDA,
            PARAM_ESTADO_COMERCIAL,
        ],
        responses={200: DashboardAdminComercialSerializer},
    )
    def get(self, request):
        filtros = parse_dashboard_filters(request, scope="admin")
        payload = {
            "fecha_referencia": fecha_referencia_analitica().isoformat(),
            "indicadores": obtener_indicadores_comerciales(filtros),
            "evolucion": obtener_evolucion_comercial(filtros),
            "vendedores": obtener_comparacion_vendedores(filtros),
        }
        return Response(payload)


class DashboardAdminFinanzasView(APIView):
    permission_classes = [EsAdministradorComercial]

    @extend_schema(
        tags=["dashboard"],
        parameters=[
            PARAM_FECHA_DESDE,
            PARAM_FECHA_HASTA,
            PARAM_GRANULARIDAD,
            PARAM_VENDEDOR,
            PARAM_MONEDA,
            PARAM_PAGE,
            PARAM_PAGE_SIZE,
        ],
        responses={200: FinanzasAdminSerializer},
    )
    def get(self, request):
        filtros = parse_dashboard_filters(request, scope="admin")
        return Response(obtener_finanzas_admin(filtros))


class DashboardAdminInventarioView(APIView):
    permission_classes = [EsAdministradorComercial]

    @extend_schema(
        tags=["dashboard"],
        parameters=[
            PARAM_FECHA_DESDE,
            PARAM_FECHA_HASTA,
            PARAM_CATEGORIA,
            PARAM_MONEDA,
            PARAM_PAGE,
            PARAM_PAGE_SIZE,
        ],
        responses={200: InventarioAdminSerializer},
    )
    def get(self, request):
        filtros = parse_dashboard_filters(request, scope="admin")
        return Response(obtener_inventario_admin(filtros))


class DashboardTiendaResumenView(APIView):
    permission_classes = [EsEncargadoTienda]

    @extend_schema(
        tags=["dashboard"],
        parameters=[
            PARAM_FECHA_DESDE,
            PARAM_FECHA_HASTA,
            PARAM_GRANULARIDAD,
            PARAM_MONEDA,
            PARAM_ESTADO_COMERCIAL,
        ],
        responses={200: DashboardTiendaResumenSerializer},
    )
    def get(self, request):
        filtros = parse_dashboard_filters(request, scope="tienda")
        uid = request.user.id
        payload = {
            "fecha_referencia": fecha_referencia_analitica().isoformat(),
            "vendedor_id": uid,
            "indicadores": obtener_indicadores_comerciales(filtros, vendedor_id=uid),
            "finanzas": obtener_resumen_financiero_vendedor(filtros, vendedor_id=uid),
            "evolucion": obtener_evolucion_comercial(filtros, vendedor_id=uid),
        }
        return Response(payload)


class DashboardTiendaSeguimientoView(APIView):
    permission_classes = [EsEncargadoTienda]

    @extend_schema(
        tags=["dashboard"],
        parameters=[
            PARAM_MONEDA,
            PARAM_CATEGORIA,
            PARAM_PAGE,
            PARAM_PAGE_SIZE,
        ],
        responses={200: DashboardTiendaSeguimientoSerializer},
    )
    def get(self, request):
        filtros = parse_dashboard_filters(request, scope="tienda")
        uid = request.user.id
        payload = {
            "fecha_referencia": fecha_referencia_analitica().isoformat(),
            "vendedor_id": uid,
            "agenda": obtener_agenda_comercial(filtros, vendedor_id=uid),
            "disponibilidad": obtener_disponibilidad_comercial(filtros),
        }
        return Response(payload)


class DashboardTallerResumenView(APIView):
    permission_classes = [EsJefeTaller]

    @extend_schema(
        tags=["dashboard"],
        parameters=[
            PARAM_FECHA_DESDE,
            PARAM_FECHA_HASTA,
            PARAM_ESTADO_FABRICACION,
            PARAM_TIPO_MUEBLE,
            PARAM_ENTREGA_DESDE,
            PARAM_ENTREGA_HASTA,
            PARAM_PAGE,
            PARAM_PAGE_SIZE,
        ],
        responses={200: DashboardTallerResumenSerializer},
    )
    def get(self, request):
        filtros = parse_dashboard_filters(request, scope="taller")
        payload = {
            "fecha_referencia": fecha_referencia_analitica().isoformat(),
            "indicadores": obtener_dashboard_taller(filtros),
            "cola_prioridades": obtener_cola_prioridades_taller(filtros),
        }
        return Response(payload)


class DashboardTallerPlanificacionView(APIView):
    permission_classes = [EsJefeTaller]

    @extend_schema(
        tags=["dashboard"],
        parameters=[
            PARAM_FECHA_DESDE,
            PARAM_FECHA_HASTA,
            PARAM_GRANULARIDAD,
            PARAM_ESTADO_FABRICACION,
            PARAM_TIPO_MUEBLE,
            PARAM_ENTREGA_DESDE,
            PARAM_ENTREGA_HASTA,
            PARAM_PAGE,
            PARAM_PAGE_SIZE,
        ],
        responses={200: DashboardTallerPlanificacionSerializer},
    )
    def get(self, request):
        filtros = parse_dashboard_filters(request, scope="taller")
        payload = {
            "fecha_referencia": fecha_referencia_analitica().isoformat(),
            **obtener_planificacion_taller(filtros),
        }
        return Response(payload)
