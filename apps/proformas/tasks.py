from celery import shared_task

from apps.proformas.services import vencer_proformas


@shared_task(name="proformas.vencer")
def vencer_proformas_task():
    return vencer_proformas()
