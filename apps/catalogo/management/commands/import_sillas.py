from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.catalogo.servicios import importar_sillas


class Command(BaseCommand):
    help = "Importa fichas comerciales confirmadas de sillas, con soporte de --dry-run."

    def add_arguments(self, parser):
        parser.add_argument(
            "--input", required=True, help="Ruta al arreglo JSON de fichas comerciales."
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Valida y reporta sin persistir cambios."
        )

    def handle(self, *args, **options):
        input_path = Path(options["input"])
        if not input_path.is_file():
            raise CommandError(f"No existe el archivo: {input_path}")
        report = importar_sillas(input_path=input_path, dry_run=options["dry_run"])
        for error in report.errors:
            self.stderr.write(self.style.ERROR(error))
        self.stdout.write(
            f"creados={report.created} omitidos={report.skipped} errores={len(report.errors)}"
        )
        if report.errors:
            raise CommandError("La importación no se aplicó")
        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING("Validación completada; no se persistieron cambios.")
            )
        else:
            self.stdout.write(self.style.SUCCESS("Importación completada."))
