from django.core.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.quotations.models import Quotation
from apps.quotations.serializers import QuotationSerializer
from apps.quotations.services import submit_quotation


class QuotationViewSet(viewsets.ModelViewSet):
    serializer_class = QuotationSerializer

    def get_queryset(self):
        return Quotation.objects.filter(seller=self.request.user).order_by("-id")

    def perform_create(self, serializer):
        serializer.save(seller=self.request.user, created_by=self.request.user)

    @action(detail=True, methods=("post",))
    def submit(self, request, pk=None):
        try:
            quotation = submit_quotation(int(pk), request.user.id)
        except ValidationError as error:
            return Response({"detail": error.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(quotation).data)
