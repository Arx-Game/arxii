"""Admin URL configuration."""

from django.urls import path

from web.admin import arx_admin_site
from web.admin.game_setup_views import game_setup
from web.admin.seed_views import seed_confirm, seed_run
from web.admin.tuning.views import (
    _conditions_fragment,
    _consequences_fragment,
    _simulation_fragment,
    tuning_checks_fragment,
    tuning_dashboard,
)
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
    path("_seed/", seed_confirm, name="admin_seed"),
    path("_seed_run/", seed_run, name="admin_seed_run"),
    path("_game_setup/", game_setup, name="admin_game_setup"),
    path("_tuning/", tuning_dashboard, name="admin_tuning"),
    path("_tuning/checks/", tuning_checks_fragment, name="admin_tuning_checks"),
    path("_tuning/consequences/", _consequences_fragment, name="admin_tuning_consequences"),
    path("_tuning/conditions/", _conditions_fragment, name="admin_tuning_conditions"),
    path("_tuning/simulation/", _simulation_fragment, name="admin_tuning_simulation"),
    path("", arx_admin_site.urls),
]
