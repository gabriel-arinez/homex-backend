from django.urls import path

from apps.dashboard.api.views import (
    DashboardAdminComercialView,
    DashboardAdminFinanzasView,
    DashboardAdminInventarioView,
    DashboardAdminResumenView,
    DashboardTallerPlanificacionView,
    DashboardTallerResumenView,
    DashboardTiendaResumenView,
    DashboardTiendaSeguimientoView,
)

urlpatterns = [
    path("administrador/", DashboardAdminResumenView.as_view(), name="dashboard-admin-resumen"),
    path(
        "administrador/comercial/",
        DashboardAdminComercialView.as_view(),
        name="dashboard-admin-comercial",
    ),
    path(
        "administrador/finanzas/",
        DashboardAdminFinanzasView.as_view(),
        name="dashboard-admin-finanzas",
    ),
    path(
        "administrador/inventario/",
        DashboardAdminInventarioView.as_view(),
        name="dashboard-admin-inventario",
    ),
    path("tienda/", DashboardTiendaResumenView.as_view(), name="dashboard-tienda-resumen"),
    path(
        "tienda/seguimiento/",
        DashboardTiendaSeguimientoView.as_view(),
        name="dashboard-tienda-seguimiento",
    ),
    path("taller/", DashboardTallerResumenView.as_view(), name="dashboard-taller-resumen"),
    path(
        "taller/planificacion/",
        DashboardTallerPlanificacionView.as_view(),
        name="dashboard-taller-planificacion",
    ),
]
