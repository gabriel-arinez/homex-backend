from django.http import HttpResponse


def respuesta_documento_html(*, contenido: str, nombre: str) -> HttpResponse:
    respuesta = HttpResponse(
        contenido,
        content_type="text/html; charset=utf-8",
    )
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}.html"'
    return respuesta


def respuesta_documento_pdf(*, contenido: bytes, nombre: str) -> HttpResponse:
    respuesta = HttpResponse(contenido, content_type="application/pdf")
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}.pdf"'
    respuesta["X-Content-Type-Options"] = "nosniff"
    respuesta["Cache-Control"] = "private, no-store, max-age=0"
    respuesta["Vary"] = "Authorization, Cookie"
    return respuesta
