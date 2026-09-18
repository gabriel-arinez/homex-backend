from rest_framework.routers import DefaultRouter

from apps.quotations.views import QuotationViewSet

router = DefaultRouter()
router.register("quotations", QuotationViewSet, basename="quotation")
urlpatterns = router.urls
