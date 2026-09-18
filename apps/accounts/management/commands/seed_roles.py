from django.core.management.base import BaseCommand

from apps.accounts.roles import ROLE_NAMES, ensure_roles


class Command(BaseCommand):
    help = "Crea los roles operativos estructurales de HOMEX si aún no existen."

    def handle(self, *args, **options):
        ensure_roles()
        self.stdout.write(self.style.SUCCESS(", ".join(ROLE_NAMES)))
