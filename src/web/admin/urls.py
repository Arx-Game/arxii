"""Admin URL configuration."""

from django.urls import path

from web.admin import arx_admin_site
from web.admin.content_export_views import content_export_preview, content_export_run
from web.admin.content_load_views import content_load_confirm, content_load_run
from web.admin.content_push_views import content_push_preview, content_push_run
from web.admin.game_setup_views import game_setup
from web.admin.seed_views import seed_confirm, seed_run
from web.admin.sphinx_views import sphinx_audit
from web.admin.tuning.ops_views import (
    ops_dashboard,
    ops_economy_fragment,
    ops_progression_fragment,
    ops_reports_fragment,
    ops_story_fragment,
    ops_tech_fragment,
)
from web.admin.tuning.views import (
    tuning_checks_fragment,
    tuning_conditions_fragment,
    tuning_consequences_fragment,
    tuning_dashboard,
    tuning_simulation_fragment,
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
    path("_content_load/", content_load_confirm, name="admin_content_load"),
    path("_content_load_run/", content_load_run, name="admin_content_load_run"),
    path(
        "_content_export/",
        content_export_preview,
        name="admin_content_export",
    ),
    path(
        "_content_export_run/",
        content_export_run,
        name="admin_content_export_run",
    ),
    path(
        "_content_push/",
        content_push_preview,
        name="admin_content_push",
    ),
    path(
        "_content_push_run/",
        content_push_run,
        name="admin_content_push_run",
    ),
    path("_game_setup/", game_setup, name="admin_game_setup"),
    path("_sphinx/", sphinx_audit, name="admin_sphinx_audit"),
    path("_tuning/", tuning_dashboard, name="admin_tuning"),
    path("_tuning/checks/", tuning_checks_fragment, name="admin_tuning_checks"),
    path("_tuning/consequences/", tuning_consequences_fragment, name="admin_tuning_consequences"),
    path("_tuning/conditions/", tuning_conditions_fragment, name="admin_tuning_conditions"),
    path("_tuning/simulation/", tuning_simulation_fragment, name="admin_tuning_simulation"),
    path("_ops/", ops_dashboard, name="admin_ops"),
    path("_ops/progression/", ops_progression_fragment, name="admin_ops_progression"),
    path("_ops/economy/", ops_economy_fragment, name="admin_ops_economy"),
    path("_ops/story/", ops_story_fragment, name="admin_ops_story"),
    path("_ops/reports/", ops_reports_fragment, name="admin_ops_reports"),
    path("_ops/tech/", ops_tech_fragment, name="admin_ops_tech"),
    path("", arx_admin_site.urls),
]
