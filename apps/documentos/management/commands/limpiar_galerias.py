from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.documentos.models import GaleriaBorrador


class Command(BaseCommand):
    help = "Elimina galerías no vinculadas e inactivas (por defecto, 30 días)."

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=30)

    def handle(self, *args, **options):
        with transaction.atomic():
            qs = GaleriaBorrador.objects.select_for_update().filter(
                detalle__isnull=True,
                actualizado__lt=timezone.now() - timedelta(days=options["dias"]),
            )
            ids = list(qs.values_list("pk", flat=True))
            cantidad = len(ids)
            GaleriaBorrador.objects.filter(pk__in=ids).delete()
        self.stdout.write(f"Galerías abandonadas eliminadas: {cantidad}")
