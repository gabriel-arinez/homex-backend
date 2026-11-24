"""Excepciones explícitas del importador integral HOMEX."""


class ErrorImportacionHomex(ValueError):
    """Error de validación o ejecución durante la importación HOMEX."""


class ErrorIntegridadPaquete(ErrorImportacionHomex):
    """Error de seguridad ZIP, esquema o verificación SHA-256."""


class ErrorConflictoImportacion(ErrorImportacionHomex):
    """Conflicto de idempotencia o estado incompatible en base de datos."""


class ErrorConciliacionImportacion(ErrorImportacionHomex):
    """Discrepancia en auditoría/conciliación final tras ejecutar la importación."""

    def __init__(self, mensaje: str, *, reporte: dict | None = None) -> None:
        super().__init__(mensaje)
        self.reporte = reporte
