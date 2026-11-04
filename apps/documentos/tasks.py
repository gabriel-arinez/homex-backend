from celery import shared_task
from django.core.management import call_command


@shared_task(name="documentos.limpiar_galerias")
def limpiar_galerias_abandonadas():
    call_command("limpiar_galerias")
