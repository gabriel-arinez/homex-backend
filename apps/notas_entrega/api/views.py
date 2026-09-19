from rest_framework import serializers, viewsets

from apps.core.permissions import EsVendedor
from apps.notas_entrega.models import NotaEntrega


class NotaEntregaSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotaEntrega
        fields = "__all__"
        read_only_fields = tuple(field.name for field in NotaEntrega._meta.fields)


class NotaEntregaViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NotaEntrega.objects.all()
    serializer_class = NotaEntregaSerializer
    permission_classes = [EsVendedor]
