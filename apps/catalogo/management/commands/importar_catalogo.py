from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.catalogo.importador import ErrorCatalogo, cargar_archivo_catalogo, importar_catalogo


class Command(BaseCommand):
    help = "Importa un catálogo comercial HOMEX JSON schema_version=1."

    def add_arguments(self, parser):
        parser.add_argument("archivo")
        parser.add_argument("--actor-id", type=int, required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opciones):
        try:
            actor = User.objects.get(pk=opciones["actor_id"])
            resultado = importar_catalogo(
                datos=cargar_archivo_catalogo(opciones["archivo"]),
                actor=actor,
                dry_run=opciones["dry_run"],
            )
        except (User.DoesNotExist, ErrorCatalogo) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(str(resultado)))
