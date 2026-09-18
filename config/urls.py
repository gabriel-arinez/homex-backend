from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.catalogo.api.views import (
    DescuentoProductoViewSet,
    ProductoPisoViewSet,
    ProductoSillaViewSet,
    ProductoViewSet,
)
from apps.clientes.api.views import ClienteViewSet
from apps.proformas.api.views import DetalleProformaViewSet, ProformaViewSet
from config.views import health

router = DefaultRouter()
router.register("clientes", ClienteViewSet, basename="cliente")
router.register("catalogo/productos", ProductoViewSet, basename="producto")
router.register("catalogo/sillas", ProductoSillaViewSet, basename="producto-silla")
router.register("catalogo/pisos", ProductoPisoViewSet, basename="producto-piso")
router.register("catalogo/descuentos", DescuentoProductoViewSet, basename="descuento-producto")
router.register("proformas", ProformaViewSet, basename="proforma")
router.register("proformas-detalle", DetalleProformaViewSet, basename="proforma-detalle")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", health, name="health"),
    path("api/v1/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/v1/", include(router.urls)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
