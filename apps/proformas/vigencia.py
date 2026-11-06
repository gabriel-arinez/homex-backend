from datetime import date, timedelta


def fecha_limite(fecha_creacion: date, dias: int | None) -> date | None:
    """El día calculado es el último día completo de validez."""
    if dias is None:
        return None
    if dias < 1:
        raise ValueError("La validez debe ser de al menos un día.")
    return fecha_creacion + timedelta(days=dias)


def esta_vencida(fecha_creacion: date, dias: int | None, hoy: date) -> bool:
    limite = fecha_limite(fecha_creacion, dias)
    return limite is not None and hoy > limite
