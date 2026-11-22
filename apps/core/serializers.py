from rest_framework import serializers


class UsuarioResumenSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)


def resumen_usuario(user) -> dict | None:
    if user is None:
        return None
    return {
        "id": user.id,
        "username": user.get_username(),
        "display_name": user.get_full_name().strip() or user.get_username(),
    }
