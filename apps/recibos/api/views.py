from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import EsVendedor
from apps.recibos.models import Recibo
from apps.recibos.services import anular_recibo


class ReciboSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recibo
        fields = "__all__"
        read_only_fields = (
            "numero",
            "total",
            "a_cuenta",
            "saldo",
            "estado",
            "fecha",
            "created_by",
            "updated_by",
        )


class ReciboViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Recibo.objects.all()
    serializer_class = ReciboSerializer
    permission_classes = [EsVendedor]

    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        return Response(
            self.get_serializer(
                anular_recibo(recibo_id=self.get_object().id, actor=request.user)
            ).data
        )
