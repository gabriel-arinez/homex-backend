from rest_framework.routers import DefaultRouter

from apps.payments.views import ReceiptViewSet

router = DefaultRouter()
router.register("receipts", ReceiptViewSet, basename="receipt")

urlpatterns = router.urls
