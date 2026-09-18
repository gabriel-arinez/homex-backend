from django.db.models.signals import post_migrate
from django.dispatch import receiver

from apps.accounts.roles import ensure_roles


@receiver(post_migrate)
def create_operational_roles(**kwargs) -> None:
    ensure_roles()
