"""Reproducible synthetic catalog fixtures, not human speech accuracy evidence."""

import argparse
from pathlib import Path

from generar_audio_sintetico_prf04 import generar

SAMPLES = {
    "silla": (
        "Silla ergonómica de malla. Color negro. Apoyo lumbar regulable. "
        "Asiento de espuma de alta densidad. Precio unitario mil quinientos bolivianos."
    ),
    "piso": (
        "Piso flotante Ganesha. Espesor ocho milímetros. Material HDF. "
        "Precio unitario ciento veinticinco bolivianos."
    ),
    "otro": (
        "Zócalo de alto tráfico de ochenta por quince milímetros. Unidad barra. "
        "Precio unitario cincuenta bolivianos."
    ),
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, text in SAMPLES.items():
        generar(args.output_dir / f"{name}.wav", text)
