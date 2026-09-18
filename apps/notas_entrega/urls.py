from rest_framework.routers import DefaultRouter

from apps.notas_entrega.views import NotaEntregaViewSet

router = DefaultRouter()
router.register("notas-entrega", NotaEntregaViewSet, basename="nota-entrega")

urlpatterns = router.urls
