from rest_framework import serializers


class IdentidadActualSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    capabilities = serializers.ListField(
        child=serializers.CharField(),
        read_only=True,
    )
