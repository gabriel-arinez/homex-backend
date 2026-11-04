"""Diagnóstico y reparación explícita de los estados indispensables de proformas.

No altera datos en modo consulta. La reparación de estados se solicita mediante
--reparar y es idempotente: no sustituye catálogos ni cambia estados de proformas.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalogo.models import ConceptoCatalogo, ValorCatalogo


ESTADOS_REQUERIDOS = {
    "BORRADOR": "Borrador",
    "EN_REVISION": "En revisión",
    "NO_CONCRETADA": "No concretada",
    "APROBADA": "Aprobada",
}
ESTADOS_REPARABLES = {"EN_REVISION", "NO_CONCRETADA"}


class Command(BaseCommand):
    help = "Audita los estados de proformas. --reparar restaura sólo los estados operativos faltantes o inactivos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reparar",
            action="store_true",
            help="Crea o reactiva EN_REVISION y NO_CONCRETADA si falta alguno (requiere migraciones al día).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        reparar = options["reparar"]
        concepto = ConceptoCatalogo.objects.select_for_update().filter(
            codigo="ESTADO_PROFORMA"
        ).first()
        if concepto is None:
            raise CommandError(
                "No existe el concepto ESTADO_PROFORMA. Comprueba las migraciones del catálogo antes de reparar."
            )
        if not concepto.activo:
            raise CommandError(
                "El concepto ESTADO_PROFORMA está inactivo. Requiere investigación, no se reactivará automáticamente."
            )

        errores = []
        for codigo, nombre in ESTADOS_REQUERIDOS.items():
            estado = ValorCatalogo.objects.select_for_update().filter(
                concepto=concepto, codigo=codigo
            ).first()
            if estado is not None and estado.activo:
                self.stdout.write(f"OK ESTADO_PROFORMA.{codigo}")
                continue
            situacion = "INACTIVO" if estado else "AUSENTE"
            if reparar and codigo in ESTADOS_REPARABLES:
                if estado is None:
                    ValorCatalogo.objects.create(
                        concepto=concepto, codigo=codigo, nombre=nombre, activo=True
                    )
                else:
                    estado.activo = True
                    estado.save(update_fields=["activo"])
                self.stdout.write(self.style.SUCCESS(f"REPARADO ESTADO_PROFORMA.{codigo} ({situacion})"))
            else:
                errores.append(codigo)
                self.stdout.write(self.style.ERROR(f"{situacion} ESTADO_PROFORMA.{codigo}"))

        if errores:
            raise CommandError(
                "Faltan estados operativos activos: "
                + ", ".join(errores)
                + (". Ejecuta --reparar tras verificar el entorno."
                   if not reparar
                   else ". La reparación no modifica estados históricos o estructurales.")
            )
        self.stdout.write(self.style.SUCCESS("Catálogo de estados de proforma verificado."))
