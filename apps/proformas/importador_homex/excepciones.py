"""Excepciones explícitas del importador integral HOMEX."""


class ErrorImportacionHomex(ValueError):
    """Error de validación o ejecución durante la importación HOMEX."""


class ErrorIntegridadPaquete(ErrorImportacionHomex):
    """Error de seguridad ZIP, esquema o verificación SHA-256."""


class ErrorConflictoImportacion(ErrorImportacionHomex):
    """Conflicto de idempotencia o estado incompatible en base de datos."""
