from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

from apps.deliveries.models import DeliveryNote
from apps.deliveries.serializers import DeliveryNoteSerializer
from apps.deliveries.services import issue_delivery_note


class DeliveryNoteViewSet(viewsets.ModelViewSet):
    http_method_names = ("get", "post", "head", "options")
    serializer_class = DeliveryNoteSerializer

    def get_queryset(self):
        return DeliveryNote.objects.filter(seller=self.request.user).select_related(
            "order", "seller"
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            note = issue_delivery_note(
                order_id=serializer.validated_data["order"].pk,
                seller_id=request.user.pk,
                actor_id=request.user.pk,
            )
        except DjangoValidationError as error:
            raise ValidationError(error.messages) from error
        return Response(self.get_serializer(note).data, status=status.HTTP_201_CREATED)
