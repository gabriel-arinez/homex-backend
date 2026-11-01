"""Complemento numérico conservador; nunca cambia el normalizador histórico."""

from __future__ import annotations

import re
from decimal import Decimal

from research.asr_opt.evaluation import normalize

VERSION = "es-context-numeric-v2"
SMALL = dict(
    zip(
        (
            "cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece "
            "catorce quince dieciséis diecisiete dieciocho diecinueve veinte veintiuno "
            "veintidós veintitrés veinticuatro veinticinco veintiséis veintisiete "
            "veintiocho veintinueve "
        ).split(),
        range(30),
    )
)
SMALL.update(un=1, una=1)
TENS = dict(
    zip("treinta cuarenta cincuenta sesenta setenta ochenta noventa".split(), range(30, 100, 10))
)
HUNDREDS = dict(
    zip(
        (
            "cien ciento doscientos trescientos cuatrocientos quinientos seiscientos "
            "setecientos ochocientos novecientos "
        ).split(),
        [100, 100, 200, 300, 400, 500, 600, 700, 800, 900],
    )
)
CONTEXT = set(
    (
        "metro metros centímetro centímetros milímetro milímetros m cm mm boliviano "
        "bolivianos bob porcentaje unidades unidad pieza piezas cajón cajones puerta "
        "puertas repisa repisas tomacorrientes ruedas personas plazas mesas mesa "
        "escritorio escritorios velador veladores gavetero gaveteros cajonera "
        "cajoneras papeleros archivador archivadores división divisiones lados patas "
        "% ‰ "
    ).split()
)
WORDS = set(SMALL) | set(TENS) | set(HUNDREDS) | {"mil", "y", "punto", "coma"}


def integer(words):
    if not words:
        return None
    if words.count("mil") > 1:
        return None
    if "mil" in words:
        i = words.index("mil")
        a = integer(words[:i]) if i else 1
        b = integer(words[i + 1 :]) if words[i + 1 :] else 0
        return (
            a * 1000 + b if a is not None and 0 < a < 1000 and b is not None and b < 1000 else None
        )
    if len(words) == 1:
        return SMALL.get(words[0], TENS.get(words[0], HUNDREDS.get(words[0])))
    if words[0] in HUNDREDS and words[0] != "cien":
        b = integer(words[1:])
        return HUNDREDS[words[0]] + b if b is not None and 0 < b < 100 else None
    if (
        len(words) == 3
        and words[0] in TENS
        and words[1] == "y"
        and words[2] in SMALL
        and 0 < SMALL[words[2]] < 10
    ):
        return TENS[words[0]] + SMALL[words[2]]
    return None


def canonical(value):
    number = Decimal(str(value))
    return format(number.normalize(), "f") if number else "0"


def expression(words):
    for separator in ("punto", "coma"):
        if separator in words:
            if words.count(separator) != 1:
                return None
            i = words.index(separator)
            a, tail = integer(words[:i]), words[i + 1 :]
            if a is None or not tail:
                return None
            if all(w in SMALL and SMALL[w] < 10 for w in tail):
                fraction = "".join(str(SMALL[w]) for w in tail)
            else:
                b = integer(tail)
                if b is None or not 0 <= b < 100:
                    return None
                fraction = str(b)
            return canonical(str(a) + "." + fraction)
    value = integer(words)
    return canonical(value) if value is not None else None


def numeric_normalize(text, monetary_convention=None):
    """Contexto léxico explícito; sin conversión de unidades ni supresión de alcance."""
    if monetary_convention not in (None, "es-BO", "en-US"):
        raise ValueError("Convención no soportada")
    tokens = normalize(text).split()
    output, events = [], []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        # Porcentajes se separan uniformemente conservando su operador.
        if re.fullmatch(r"[+−-]?\d+(?:[.,]\d+)?[%‰]", token):
            tokens[i : i + 1] = [token[:-1], token[-1]]
            token = tokens[i]
        if token == "menos" and (i == 0 or tokens[i - 1] in {"importe", "temperatura"}):
            end = i + 1
            while end < len(tokens) and tokens[end] in WORDS:
                end += 1
            value = expression(tokens[i + 1 : end])
            if value is not None and end < len(tokens) and tokens[end] in CONTEXT:
                output.append("-" + value)
                events.append(
                    {
                        "start_token": i,
                        "end_token": end,
                        "status": "SIGNO_EXPLICITO",
                        "value": "-" + value,
                    }
                )
                i = end
                continue
        j = i
        while j < len(tokens) and tokens[j] in WORDS:
            j += 1
        # 'y' entre dimensiones nunca se consume como parte de un número.
        while j > i and tokens[j - 1] == "y":
            j -= 1
        context = j < len(tokens) and tokens[j] in CONTEXT
        if j > i:
            value = expression(tokens[i:j])
            if value is not None and context:
                output.append(value)
                events.append(
                    {
                        "start_token": i,
                        "end_token": j,
                        "source": tokens[i:j],
                        "value": value,
                        "status": "EQUIVALENCIA_CONTEXTUAL",
                    }
                )
                i = j
                continue
            if value is None or j - i > 1:
                events.append(
                    {
                        "start_token": i,
                        "end_token": j,
                        "source": tokens[i:j],
                        "status": "AMBIGUO" if value is None else "SIN_CONTEXTO",
                    }
                )
        # Dígitos + mil son una expresión inequívoca con contexto posterior.
        if (
            re.fullmatch(r"\d+", token)
            and i + 2 < len(tokens)
            and tokens[i + 1] == "mil"
            and tokens[i + 2] in CONTEXT
        ):
            output.append(canonical(Decimal(token) * 1000))
            i += 2
            continue
        if (
            re.fullmatch(r"[+−-]?(?:\d+[.,]?\d*|[.,]\d+)", token)
            and i + 1 < len(tokens)
            and tokens[i + 1] in CONTEXT
        ):
            raw = token.replace("−", "-")
            grouped = re.fullmatch(r"[+-]?\d{1,3}[.,]\d{3}", raw)
            if grouped:
                money = tokens[i + 1] in {"boliviano", "bolivianos", "bob"}
                sep = "." if monetary_convention == "es-BO" else ","
                if money and monetary_convention and sep in raw:
                    raw = raw.replace(sep, "")
                else:
                    events.append({"start_token": i, "source": [token], "status": "AMBIGUO"})
                    output.append(token)
                    i += 1
                    continue
            output.append(("+" if raw.startswith("+") else "") + canonical(raw.replace(",", ".")))
        else:
            output.append(token)
        i += 1
    return {
        "text": " ".join(output),
        "events": events,
        "version": VERSION,
        "monetary_convention": monetary_convention,
    }
