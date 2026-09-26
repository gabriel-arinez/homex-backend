from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts.api.views import IdentidadActualView
from apps.capturas.api.views import CapturaViewSet
from apps.catalogo.api.views import (
    CatalogoOpcionesViewSet,
    DescuentoProductoViewSet,
    ProductoPisoViewSet,
    ProductoSillaViewSet,
    ProductoViewSet,
)
from apps.clientes.api.views import ClienteViewSet
from apps.movimientos_stock.api.views import MovimientoStockViewSet
from apps.notas_entrega.api.views import NotaEntregaViewSet
from apps.ordenes_trabajo.api.views import OrdenTrabajoViewSet
from apps.pedidos.api.views import PedidoViewSet
from apps.proformas.api.views import DetalleProformaViewSet, ProformaViewSet
from apps.recibos.api.views import ReciboViewSet
from config.views import health

router = DefaultRouter()
router.register("clientes", ClienteViewSet, basename="cliente")
router.register("capturas", CapturaViewSet, basename="captura")
router.register("catalogo/opciones", CatalogoOpcionesViewSet, basename="catalogo-opcion")
router.register("catalogo/productos", ProductoViewSet, basename="producto")
router.register("catalogo/sillas", ProductoSillaViewSet, basename="producto-silla")
router.register("catalogo/pisos", ProductoPisoViewSet, basename="producto-piso")
router.register("catalogo/descuentos", DescuentoProductoViewSet, basename="descuento-producto")
router.register("proformas", ProformaViewSet, basename="proforma")
router.register("pedidos", PedidoViewSet, basename="pedido")
router.register("recibos", ReciboViewSet, basename="recibo")
router.register("notas-entrega", NotaEntregaViewSet, basename="nota-entrega")
router.register("movimientos-stock", MovimientoStockViewSet, basename="movimiento-stock")
router.register("ordenes-trabajo", OrdenTrabajoViewSet, basename="orden-trabajo")
router.register("proformas-detalle", DetalleProformaViewSet, basename="proforma-detalle")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", health, name="health"),
    path("api/v1/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/v1/auth/me/", IdentidadActualView.as_view(), name="auth-me"),
    path("api/v1/", include(router.urls)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
