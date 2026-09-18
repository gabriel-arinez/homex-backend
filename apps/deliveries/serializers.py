from rest_framework import serializers

from apps.deliveries.models import DeliveryNote


class DeliveryNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryNote
        fields = ("id", "order", "seller", "number", "date")
        read_only_fields = ("seller", "number", "date")
