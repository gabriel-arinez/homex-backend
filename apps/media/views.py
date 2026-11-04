"""Public media serving for local development and the integration runner."""

import posixpath

from django.conf import settings
from django.http import Http404
from django.views.static import serve


def media_publica(request, path):
    normalized = posixpath.normpath(path).lstrip("/")
    if normalized.split("/", 1)[0] in {".private", "proformas"}:
        raise Http404
    return serve(request, normalized, document_root=settings.MEDIA_ROOT)
