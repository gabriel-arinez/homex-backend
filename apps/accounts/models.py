from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Actor propio, creado antes de cualquier migración comercial."""
