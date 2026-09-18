from django.contrib import admin

from apps.catalog.models import CatalogConcept, CatalogValue

admin.site.register((CatalogConcept, CatalogValue))
