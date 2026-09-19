from rest_framework import serializers, viewsets

from apps.core.permissions import EsVendedor
from apps.ordenes_trabajo.models import OrdenTrabajo


class OrdenTrabajoSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrdenTrabajo
        fields = "__all__"
        read_only_fields = [field.name for field in OrdenTrabajo._meta.fields]


class OrdenTrabajoViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = OrdenTrabajo.objects.all()
    serializer_class = OrdenTrabajoSerializer
    permission_classes = [EsVendedor]

    def get_queryset(self):
        queryset = OrdenTrabajo.objects.select_related("pedido", "estado").order_by("-id")
        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset
        return queryset.filter(pedido__proforma__vendedor=self.request.user)
