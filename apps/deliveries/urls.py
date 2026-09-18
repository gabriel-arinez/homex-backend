from rest_framework.routers import DefaultRouter

from apps.deliveries.views import DeliveryNoteViewSet

router = DefaultRouter()
router.register("delivery-notes", DeliveryNoteViewSet, basename="delivery-note")

urlpatterns = router.urls
