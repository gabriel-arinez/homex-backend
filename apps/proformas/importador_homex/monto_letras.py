"""Conversión determinista de montos decimales a texto legal en Bolivianos."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_UNIDADES = (
    "",
    "uno",
    "dos",
    "tres",
    "cuatro",
    "cinco",
    "seis",
    "siete",
    "ocho",
    "nueve",
)

_ESPECIALES = (
    "diez",
    "once",
    "doce",
    "trece",
    "catorce",
    "quince",
    "dieciséis",
    "diecisiete",
    "dieciocho",
    "diecinueve",
)

_VEINTIS = (
    "veinte",
    "veintiuno",
    "veintidós",
    "veintitrés",
    "veinticuatro",
    "veinticinco",
    "veintiséis",
    "veintisiete",
    "veintiocho",
    "veintinueve",
)

_DECENAS = (
    "",
    "",
    "veinte",
    "treinta",
    "cuarenta",
    "cincuenta",
    "sesenta",
    "setenta",
    "ochenta",
    "noventa",
)

_CENTENAS = (
    "",
    "ciento",
    "doscientos",
    "trescientos",
    "cuatrocientos",
    "quinientos",
    "seiscientos",
    "setecientos",
    "ochocientos",
    "novecientos",
)


def _grupo_a_letras(n: int) -> str:
    if n == 0:
        return ""
    if n == 100:
        return "cien"
    partes: list[str] = []
    c = n // 100
    r = n % 100
    if c > 0:
        partes.append(_CENTENAS[c])
    if 10 <= r <= 19:
        partes.append(_ESPECIALES[r - 10])
    elif 20 <= r <= 29:
        partes.append(_VEINTIS[r - 20])
    else:
        d = r // 10
        u = r % 10
        if d > 0 and u > 0:
            partes.append(f"{_DECENAS[d]} y {_UNIDADES[u]}")
        elif d > 0:
            partes.append(_DECENAS[d])
        elif u > 0:
            partes.append(_UNIDADES[u])
    return " ".join(partes)


def _entero_a_letras(n: int) -> str:
    if n == 0:
        return "cero"
    millones = n // 1_000_000
    miles = (n % 1_000_000) // 1_000
    resto = n % 1_000

    partes: list[str] = []
    if millones > 0:
        if millones == 1:
            partes.append("un millón")
        else:
            partes.append(f"{_entero_a_letras(millones)} millones")
    if miles > 0:
        if miles == 1:
            partes.append("mil")
        else:
            texto_miles = _grupo_a_letras(miles)
            if texto_miles.endswith("uno"):
                texto_miles = texto_miles[:-1]
            partes.append(f"{texto_miles} mil")
    if resto > 0:
        partes.append(_grupo_a_letras(resto))
    return " ".join(partes)


def monto_a_letras_bob(monto: Decimal) -> str:
    """Convierte un Decimal positivo o cero a formato 'Xxx YY/100 Bolivianos'."""
    cuantizado = Decimal(monto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if cuantizado < 0:
        raise ValueError("El monto en letras no puede ser negativo.")
    entero = int(cuantizado)
    centavos = int((cuantizado - entero) * 100)
    texto = _entero_a_letras(entero).capitalize()
    return f"{texto} {centavos:02d}/100 Bolivianos"
