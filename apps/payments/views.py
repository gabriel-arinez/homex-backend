from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

from apps.accounts.permissions import IsSalesOrAdministration
from apps.payments.models import Receipt
from apps.payments.serializers import ReceiptSerializer
from apps.payments.services import issue_receipt, void_receipt


class ReceiptViewSet(viewsets.ModelViewSet):
    http_method_names = ("get", "post", "head", "options")
    permission_classes = (IsSalesOrAdministration,)
    queryset = Receipt.objects.all()
    serializer_class = ReceiptSerializer

    def get_queryset(self):
        return Receipt.objects.filter(order__quotation__seller=self.request.user).select_related(
            "order", "payment_type"
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            data = serializer.validated_data
            receipt = issue_receipt(
                order_id=data["order"].pk,
                actor_id=request.user.pk,
                full_name=data["full_name"],
                amount_in_words=data["amount_in_words"],
                concept=data["concept"],
                payment_type_id=data["payment_type"].pk,
                current_payment=data["current_payment"],
                check_number=data.get("check_number", ""),
                bank=data.get("bank", ""),
            )
        except DjangoValidationError as error:
            raise ValidationError(error.messages) from error
        return Response(self.get_serializer(receipt).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        receipt = self.get_object()
        try:
            receipt = void_receipt(receipt_id=receipt.pk, actor_id=request.user.pk)
        except DjangoValidationError as error:
            raise ValidationError(error.messages) from error
        return Response(self.get_serializer(receipt).data)
