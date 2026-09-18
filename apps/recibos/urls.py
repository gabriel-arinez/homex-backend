from rest_framework.routers import DefaultRouter

from apps.recibos.views import ReciboViewSet

router = DefaultRouter()
router.register("recibos", ReciboViewSet, basename="recibo")

urlpatterns = router.urls
