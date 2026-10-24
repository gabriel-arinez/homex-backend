"""Fixture TTS efímero para pruebas; no representa voz ni WER de vendedores."""

import argparse
import ctypes
import wave
from pathlib import Path

TEXTO = "Quiero un escritorio de oficina, con dos cajones. Total cien bolivianos."


def generar(destino: Path, texto: str):
    lib = ctypes.CDLL("libespeak-ng.so.1")
    chunks = []
    callback = ctypes.CFUNCTYPE(
        ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.c_void_p
    )

    @callback
    def collect(samples, count, events):
        if count:
            chunks.append(ctypes.string_at(samples, count * 2))
        return 0

    rate = lib.espeak_Initialize(2, 0, None, 0)
    if rate <= 0:
        raise RuntimeError("No se pudo inicializar eSpeak NG.")
    lib.espeak_SetSynthCallback(collect)
    if lib.espeak_SetVoiceByName(b"es") != 0:
        raise RuntimeError("No está disponible la voz sintética es.")
    lib.espeak_SetParameter(1, 135, 0)
    encoded = texto.encode("utf-8")
    if lib.espeak_Synth(encoded, len(encoded) + 1, 0, 1, 0, 1, None, None) != 0:
        raise RuntimeError("Falló la generación de audio sintético.")
    lib.espeak_Synchronize()
    with wave.open(str(destino), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\x00" * (rate * 2) + b"".join(chunks) + b"\x00" * (rate * 2 * 20))
    print(f"Fixture sintético efímero generado: {destino.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/homex-prf04-dictado.wav"))
    parser.add_argument("--texto", default=TEXTO)
    args = parser.parse_args()
    generar(args.output, args.texto)
