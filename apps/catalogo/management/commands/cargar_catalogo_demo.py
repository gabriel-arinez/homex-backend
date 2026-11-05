"""Carga optativa de 15 productos DEMO sin afectar catálogos reales."""

import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.catalogo.importador import ErrorCatalogo, cargar_archivo_catalogo, importar_catalogo
from apps.catalogo.models import ConceptoCatalogo, ValorCatalogo

FIXTURE = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "catalogo_demo_15.json"


class Command(BaseCommand):
    help = "Valida 15 artículos ficticios o los carga sólo en entornos locales autorizados."

    def add_arguments(self, parser):
        parser.add_argument("--actor-id", type=int, required=True)
        parser.add_argument("--apply", action="store_true", help="Confirma la carga en desarrollo.")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["apply"] and (not settings.DEBUG or os.getenv("HOMEX_ALLOW_DEMO_DATA") != "1"):
            raise CommandError(
                "Carga bloqueada. Sólo se permite con DEBUG=true y HOMEX_ALLOW_DEMO_DATA=1."
            )
        try:
            actor = User.objects.get(pk=options["actor_id"])
            marca = ConceptoCatalogo.objects.get(codigo="MARCA", activo=True)
            value, _ = ValorCatalogo.objects.get_or_create(
                concepto=marca,
                codigo="DEMO_MARCA",
                defaults={
                    "nombre": "Marca demostración HOMEX",
                    "activo": True,
                    "created_by": actor,
                    "updated_by": actor,
                },
            )
            if not value.activo:
                raise CommandError("DEMO_MARCA está inactiva. No se modificó.")
            results = importar_catalogo(
                datos=cargar_archivo_catalogo(FIXTURE),
                actor=actor,
                dry_run=not options["apply"],
            )
        except (User.DoesNotExist, ConceptoCatalogo.DoesNotExist, ErrorCatalogo) as exc:
            raise CommandError(str(exc)) from exc

        if not options["apply"]:
            transaction.set_rollback(True)
            self.stdout.write(
                self.style.SUCCESS(
                    f"SIMULACIÓN: {results.creados} nuevos, "
                    f"{results.existentes} ya presentes. Sin cambios."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"CARGA DEMO: {results.creados} nuevos, {results.existentes} existentes; "
                    f"{results.movimientos_stock} movimientos de stock."
                )
            )
