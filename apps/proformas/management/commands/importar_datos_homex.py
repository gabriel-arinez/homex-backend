"""Comando de administración integral para validar, importar y auditar paquetes HOMEX."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.accounts.models import User
from apps.proformas.importador_homex.auditoria import auditar_escenario
from apps.proformas.importador_homex.ejecutor_escenario import ejecutar_escenario
from apps.proformas.importador_homex.excepciones import (
    ErrorConciliacionImportacion,
    ErrorImportacionHomex,
)
from apps.proformas.importador_homex.seguridad_zip import PaqueteMaestroHomex
from apps.proformas.importador_homex.validacion import (
    parsear_fecha,
    validar_paquete_documental,
    validar_paquete_escenario,
)


class Command(BaseCommand):
    help = (
        "Valida, normaliza, importa y audita paquetes maestros HOMEX "
        "en perfiles 'documental' o 'escenario'. No destructivo por defecto."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "paquete",
            help="Ruta al archivo ZIP maestro o directorio descomprimido.",
        )
        parser.add_argument(
            "--perfil",
            required=True,
            choices=["documental", "escenario"],
            help="Perfil estricto de procesamiento: documental o escenario.",
        )
        grupo_modo = parser.add_mutually_exclusive_group()
        grupo_modo.add_argument(
            "--dry-run",
            action="store_true",
            help="Simula la ejecución y revierte al finalizar (comportamiento predeterminado).",
        )
        grupo_modo.add_argument(
            "--autorizar-importacion",
            action="store_true",
            help="Autoriza persistir cambios en la base de datos.",
        )
        parser.add_argument(
            "--fecha-corte",
            default=None,
            help="Fecha de corte ISO YYYY-MM-DD (por defecto la fecha local actual).",
        )
        parser.add_argument(
            "--simular-reloj-virtual",
            action="store_true",
            help="Habilita el reloj comercial virtual para eventos posteriores a la fecha actual.",
        )
        parser.add_argument(
            "--actor-username",
            default=None,
            help="Username del actor administrativo para catálogos técnicos.",
        )
        parser.add_argument(
            "--actor-id",
            type=int,
            default=None,
            help="ID del actor administrativo para catálogos técnicos.",
        )
        parser.add_argument(
            "--reporte-json",
            default=None,
            help="Ruta opcional para guardar el reporte estructurado en JSON.",
        )
        parser.add_argument(
            "--auditar",
            action="store_true",
            help="Ejecuta únicamente la auditoría posterior sobre la base actual.",
        )
        parser.add_argument(
            "--permitir-base-aislada",
            default=None,
            help="Nombre exacto de una base aislada autorizada para importación persistente.",
        )

    def _validar_entorno_autorizado(self, *, permitir_base_aislada: str | None) -> None:
        modulo_settings = os.environ.get("DJANGO_SETTINGS_MODULE", "")
        if (
            modulo_settings.endswith(".production")
            or modulo_settings == "config.settings.production"
        ):
            raise CommandError(
                "Bloqueado: no se permite importación persistente en config.settings.production."
            )
        db_name = str(settings.DATABASES.get("default", {}).get("NAME") or "")
        bases_bloqueadas = {
            "",
            "postgres",
            "homex",
            "homex_prod",
            "homex_production",
            "homex_dev",
            "homex_local",
        }
        if db_name in bases_bloqueadas:
            raise CommandError(
                f"Bloqueado: la base '{db_name}' no está autorizada para importación persistente."
            )
        es_base_test = db_name.startswith(("test_", "homex_test", "homex_eval_", "homex_aislada"))
        es_base_permitida = db_name in {"homex_evaluacion", "homex_test", "homex_eval_aislada"}
        es_aislada_explicita = (
            permitir_base_aislada is not None and db_name == permitir_base_aislada
        )
        if not (es_base_test or es_base_permitida or es_aislada_explicita):
            raise CommandError(
                f"Bloqueado: la base '{db_name}' requiere autorización explícita como base "
                "aislada (--permitir-base-aislada) y no puede ser producción/desarrollo."
            )

    def _resolver_actor(self, *, actor_id: int | None, actor_username: str | None) -> User:
        if actor_id is not None:
            try:
                return User.objects.get(pk=actor_id, is_active=True)
            except User.DoesNotExist as exc:
                raise CommandError(f"No existe usuario activo con id={actor_id}.") from exc
        if actor_username:
            try:
                return User.objects.get(username=actor_username, is_active=True)
            except User.DoesNotExist as exc:
                raise CommandError(
                    f"No existe usuario activo con username={actor_username}."
                ) from exc
        actor = (
            User.objects.filter(username="ana.huallpara", is_active=True).first()
            or User.objects.filter(is_staff=True, is_active=True).order_by("id").first()
            or User.objects.filter(is_active=True).order_by("id").first()
        )
        if actor is None:
            raise CommandError("No existe ningún usuario activo en la base de datos.")
        return actor

    def _escribir_reporte(self, ruta: str | None, reporte: dict) -> None:
        if not ruta:
            return
        destino = Path(ruta)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            json.dumps(reporte, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def handle(self, *args, **opciones):
        perfil: str = opciones["perfil"]
        dry_run = not opciones["autorizar_importacion"]
        fecha_corte: date = (
            parsear_fecha(opciones["fecha_corte"], "--fecha-corte")
            if opciones["fecha_corte"]
            else timezone.localdate()
        )

        try:
            if not dry_run and not opciones["auditar"]:
                self._validar_entorno_autorizado(
                    permitir_base_aislada=opciones["permitir_base_aislada"]
                )
            paquete = PaqueteMaestroHomex.desde_ruta(opciones["paquete"])

            if perfil == "documental":
                res = validar_paquete_documental(paquete)
                modo_doc = (
                    "AUDITORIA"
                    if opciones["auditar"]
                    else ("DRY_RUN" if dry_run else "PERSISTENTE")
                )
                reporte = {
                    "perfil": "documental",
                    "modo": modo_doc,
                    "fecha_corte": fecha_corte.isoformat(),
                    "manifiestos": res.resumen_manifiestos,
                    "incidencias": {
                        "total": res.total_incidencias,
                        "por_estado": res.incidencias_por_estado,
                        "pendientes_excluidas": len(res.incidencias_pendientes),
                        "detalle_pendientes": res.incidencias_pendientes,
                    },
                    "imagenes": {
                        "verificadas_sha256": res.imagenes_verificadas,
                        "pendientes_asignacion": len(res.imagenes_pendientes),
                        "archivos_pendientes": res.imagenes_pendientes,
                    },
                    "resumen_entidades": {
                        "productos_candidatos": res.productos_candidatos,
                        "clientes_candidatos": res.clientes_candidatos,
                        "proformas_grupos": res.proformas_grupos,
                        "proformas_operativas_autorizadas": res.proformas_autorizadas,
                        "notas_documentales": res.notas_documentales,
                        "notas_operativas_autorizadas": res.notas_autorizadas,
                    },
                    "operaciones_importadas": 0,
                    "nota": (
                        "Perfil documental: 0 operaciones importadas automáticamente; "
                        f"{len(res.incidencias_pendientes)} incidencias pendientes "
                        "excluidas y reportadas."
                    ),
                }
                self._escribir_reporte(opciones["reporte_json"], reporte)
                self.stdout.write(json.dumps(reporte, indent=2, ensure_ascii=False))
                return

            validacion = validar_paquete_escenario(paquete)

            if opciones["auditar"]:
                auditoria = auditar_escenario(validacion, fecha_corte=fecha_corte)
                reporte = {
                    "perfil": "escenario",
                    "modo": "AUDITORIA",
                    "manifiestos": validacion.resumen_manifiestos,
                    "auditoria": auditoria,
                }
                self._escribir_reporte(opciones["reporte_json"], reporte)
                self.stdout.write(json.dumps(reporte, indent=2, ensure_ascii=False))
                if not auditoria["conforme"]:
                    raise CommandError(f"Auditoría con discrepancias: {auditoria['discrepancias']}")
                return

            actor_admin = self._resolver_actor(
                actor_id=opciones["actor_id"],
                actor_username=opciones["actor_username"],
            )
            try:
                resultado = ejecutar_escenario(
                    validacion,
                    actor_admin=actor_admin,
                    fecha_corte=fecha_corte,
                    simular_reloj_virtual=opciones["simular_reloj_virtual"],
                    dry_run=dry_run,
                    paquete=paquete,
                )
            except ErrorConciliacionImportacion as exc:
                if exc.reporte is not None:
                    rep_err = {
                        "perfil": "escenario",
                        "manifiestos": validacion.resumen_manifiestos,
                        **exc.reporte,
                    }
                    self._escribir_reporte(opciones["reporte_json"], rep_err)
                raise
            reporte = {
                "perfil": "escenario",
                "manifiestos": validacion.resumen_manifiestos,
                **resultado,
            }
            self._escribir_reporte(opciones["reporte_json"], reporte)
            self.stdout.write(json.dumps(reporte, indent=2, ensure_ascii=False))
        except (ErrorImportacionHomex, APIException) as exc:
            raise CommandError(str(exc)) from exc
