from rest_framework import serializers

from apps.payments.models import Receipt


class ReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Receipt
        fields = (
            "id",
            "number",
            "order",
            "full_name",
            "amount_in_words",
            "concept",
            "payment_type",
            "check_number",
            "bank",
            "total",
            "current_payment",
            "on_account",
            "balance",
            "status",
            "date",
        )
        read_only_fields = ("number", "total", "on_account", "balance", "status", "date")
