from django.core.management.base import BaseCommand

from apps.capturas.outbox import publicar_pendientes


class Command(BaseCommand):
    help = "Publica trabajos pendientes del outbox de capturas en Celery/Redis."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        resultado = publicar_pendientes(limite=options["limit"])
        self.stdout.write(f"publicados={resultado['publicados']} errores={resultado['errores']}")
