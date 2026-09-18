from rest_framework.routers import DefaultRouter

from apps.proformas.views import ProformaViewSet

router = DefaultRouter()
router.register("proformas", ProformaViewSet, basename="proforma")
urlpatterns = router.urls
