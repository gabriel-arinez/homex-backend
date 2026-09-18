from django.contrib import admin

from apps.catalogo.models import ConceptoCatalogo, ValorCatalogo

admin.site.register((ConceptoCatalogo, ValorCatalogo))
