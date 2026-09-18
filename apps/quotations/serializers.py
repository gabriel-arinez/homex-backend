from rest_framework import serializers

from apps.quotations.models import Quotation


class QuotationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Quotation
        fields = (
            "id",
            "number",
            "customer",
            "seller",
            "status",
            "currency",
            "title",
            "date",
            "subtotal",
            "discount_total",
            "total",
        )
        read_only_fields = ("number", "seller", "subtotal", "discount_total", "total")
