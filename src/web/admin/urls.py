"""Admin URL configuration."""

from django.urls import path

from web.admin import arx_admin_site
from web.admin.views import (
    export_data,
    import_data,
    is_model_excluded,
    is_model_pinned,
    toggle_export_exclusion,
    toggle_pin_model,
)

urlpatterns = [
    path("_pin/", toggle_pin_model, name="admin_toggle_pin"),
    path("_pinned/", is_model_pinned, name="admin_is_pinned"),
    path("_exclude/", toggle_export_exclusion, name="admin_toggle_exclude"),
    path("_excluded/", is_model_excluded, name="admin_is_excluded"),
    path("_export/", export_data, name="admin_export_data"),
    path("_import/", import_data, name="admin_import_data"),
    path("", arx_admin_site.urls),
]
