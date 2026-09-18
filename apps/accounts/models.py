from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Actor autenticable de HOMEX, definido antes de migrar el dominio comercial."""
