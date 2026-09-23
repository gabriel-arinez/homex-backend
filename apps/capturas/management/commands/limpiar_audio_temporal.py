from django.core.management.base import BaseCommand

from apps.capturas.tasks import limpiar_audio_temporal_task


class Command(BaseCommand):
    help = "Elimina temporales de audio huérfanos vencidos."

    def handle(self, *args, **options):
        self.stdout.write(f"eliminados={limpiar_audio_temporal_task.run()}")
