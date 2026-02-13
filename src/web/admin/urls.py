"""Admin URL configuration."""

from django.urls import path

from web.admin import arx_admin_site
from web.admin.views import (
    export_data,
    export_preview,
    import_execute,
    import_upload,
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
    path("_export_preview/", export_preview, name="admin_export_preview"),
    path("_import_upload/", import_upload, name="admin_import_upload"),
    path("_import_execute/", import_execute, name="admin_import_execute"),
    path("", arx_admin_site.urls),
]
