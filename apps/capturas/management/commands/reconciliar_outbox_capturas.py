from django.core.management.base import BaseCommand

from apps.capturas.outbox import reconciliar_publicados


class Command(BaseCommand):
    help = "Devuelve al outbox trabajos publicados que siguen sin cierre después del umbral."

    def handle(self, *args, **options):
        self.stdout.write(f"reconciliados={reconciliar_publicados()}")
