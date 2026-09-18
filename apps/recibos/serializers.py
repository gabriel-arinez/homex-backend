from rest_framework import serializers

from apps.recibos.models import Recibo


class ReciboSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recibo
        fields = (
            "id",
            "numero",
            "pedido",
            "nombre_completo",
            "monto_literal",
            "concepto",
            "tipo_pago",
            "numero_cheque",
            "banco",
            "total",
            "pago_actual",
            "a_cuenta",
            "saldo",
            "estado",
            "fecha",
        )
        read_only_fields = ("numero", "total", "a_cuenta", "saldo", "estado", "fecha")
