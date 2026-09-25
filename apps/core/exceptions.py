from rest_framework.exceptions import ValidationError


class ConflictoComercial(ValidationError):
    status_code = 409
    default_code = "conflicto_comercial"
