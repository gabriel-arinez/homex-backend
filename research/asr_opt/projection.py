"""Matriz ASR -> NLP congelado -> PRF04_2; solo lectura en PostgreSQL exclusivo."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from time import perf_counter


def clean(value):
    if isinstance(value, dict):
        return {
            k: clean(v)
            for k, v in value.items()
            if not (k == "text" and value.get("normalized_value") is not None)
            and k
            not in {
                "evidence_ids",
                "candidate_id",
                "start",
                "end",
                "original_text",
                "uid",
                "conjunto_uid",
                "descripcion_original",
                "text_original",
                "latency_nlp_ms",
            }
        }
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def differences(left, right, prefix=""):
    if left == right:
        return []
    if isinstance(left, dict) and isinstance(right, dict):
        return [
            d
            for key in sorted(left.keys() | right.keys())
            for d in differences(left.get(key), right.get(key), prefix + "/" + key)
        ]
    return [
        {
            "field": prefix,
            "baseline": left,
            "candidate": right,
            "acoustic_correctness": "PENDIENTE_GOLD",
        }
    ]


def project_reports(paths: list[Path], expected_database: str) -> dict:
    import django

    django.setup()
    from importlib.metadata import version

    from django.conf import settings
    from django.db import connection, transaction

    from apps.capturas.nlp.adapter import AdaptadorNLP
    from apps.capturas.proyeccion_prf03 import proyectar
    from apps.catalogo.models import MetadatoAtributoMueble, ValorCatalogo

    db = settings.DATABASES["default"]
    if (
        not expected_database.startswith("asr_opt_")
        or db["NAME"] != expected_database
        or db["HOST"] != "127.0.0.1"
        or str(db["PORT"]) != "55487"
    ):
        raise ValueError("Se requiere PostgreSQL propio ASR-OPT en puerto 55487")
    if version("homex-nlp") != "0.1.18":
        raise ValueError("NLP congelado no corresponde")
    engine = AdaptadorNLP()
    reports = []
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
        catalog = list(
            ValorCatalogo.objects.filter(activo=True).values(
                "id", "concepto__codigo", "codigo", "nombre"
            )
        )
        metadata = list(MetadatoAtributoMueble.objects.values())
        for path in paths:
            report = json.loads(path.read_text())
            rows = []
            for row in report.get("records", []):
                started = perf_counter()
                raw = engine.extraer(
                    solicitud_id="asr-opt-" + row["audio_id"],
                    texto=row["transcription"],
                    moneda="BOB",
                ).resultado_original
                nlp_s = perf_counter() - started
                started = perf_counter()
                try:
                    projection, error = proyectar(raw), None
                except Exception as exc:
                    projection, error = None, type(exc).__name__
                item = raw.get("item_proposal") or {}
                fields = {
                    "status": raw["status"],
                    "product": item.get("name"),
                    "quantity": item.get("quantity"),
                    "price": item.get("price"),
                    "components": item.get("components"),
                    "measures": item.get("dimensions"),
                    "thicknesses": item.get("thicknesses"),
                    "colors": [item.get("primary_color"), item.get("secondary_color")],
                    "accessories": item.get("accessories"),
                    "unresolved": [
                        c
                        for c in raw["candidates"]
                        if c["candidate_id"] in (item.get("unresolved") or [])
                    ],
                    "groups_scopes": [
                        c for c in raw["candidates"] if c["label"] in {"CONJUNTO", "COMPONENTE"}
                    ],
                    "warnings": raw["warnings"],
                    "projection": projection,
                    "projection_error": error,
                    "materials_units_scopes": [
                        c
                        for c in raw["candidates"]
                        if c["label"] in {"MATERIAL", "UNIDAD_MEDIDA", "CANTIDAD_INTERNA", "COLOR"}
                    ],
                    "negation_tokens_only_not_scope": re.findall(
                        r"\b(?:sin|no|ni)\b", row["transcription"].casefold()
                    ),
                }
                rows.append(
                    {
                        "audio_id": row["audio_id"],
                        "source_audio_sha256": row.get("source_audio_sha256", row["audio_sha256"]),
                        "nlp": raw,
                        "projection": projection,
                        "fields": clean(fields),
                        "nlp_s": nlp_s,
                        "projection_s": perf_counter() - started,
                        "error_attribution": (
                            "Sin gold no se atribuye error acústico; revisar texto, "
                            "decisión NLP y catálogo por separado"
                        ),
                    }
                )
            reports.append({"source": str(path), "rows": rows})
    baseline = {r["audio_id"]: r for r in reports[0]["rows"]}
    for report in reports:
        for row in report["rows"]:
            original = baseline[row["audio_id"]]
            if row["source_audio_sha256"] != original["source_audio_sha256"]:
                raise ValueError("No corresponde al audio original pareado")
            row["differences_from_small_original"] = differences(original["fields"], row["fields"])
    return {
        "nlp": "0.1.18",
        "rules": "prf04-rules-final",
        "mode": "RULES_ONLY",
        "projection_version": "PRF04_2",
        "db_read_only": True,
        "catalog": catalog,
        "metadata": metadata,
        "accuracy_gate": "PENDIENTE_GOLD",
        "reports": reports,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
    if args.output.exists():
        raise FileExistsError("No sobrescribir matrices")
    args.output.write_text(
        json.dumps(
            project_reports(args.reports, args.expected_database),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
