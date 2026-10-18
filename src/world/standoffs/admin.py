"""Django admin for standoffs: approaches, terms, config and cause glosses.

A creature's drives, cause and faction rules are authored on the Standoff Profile
Builder (``web/admin/standoff_profile``, #4354), not here.
"""

from django.contrib import admin

from world.standoffs.models import (
    StandoffApproach,
    StandoffCauseGloss,
    StandoffConfig,
    StandoffReactionLine,
    StandoffTerms,
)
from world.standoffs.services.describe import config_preview


class StandoffReactionLineInline(admin.StackedInline):
    """Reaction lines edited on the approach or terms page (stacked: they carry prose)."""

    model = StandoffReactionLine
    extra = 0
    autocomplete_fields = ("creature_template",)


class ApproachReactionLineInline(StandoffReactionLineInline):
    fk_name = "approach"


class TermsReactionLineInline(StandoffReactionLineInline):
    fk_name = "terms"


@admin.register(StandoffApproach)
class StandoffApproachAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "check_type",
        "capability",
        "is_verbal",
        "damages_morale",
        "display_order",
    )
    list_filter = ("is_verbal",)
    search_fields = ("name",)
    autocomplete_fields = ("check_type", "capability", "sway_target")
    filter_horizontal = ("archetypes",)
    inlines = (ApproachReactionLineInline,)


@admin.register(StandoffTerms)
class StandoffTermsAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "effect",
        "critical_effect",
        "required_drive",
        "difficulty_shift_bands",
        "display_order",
    )
    list_filter = ("effect",)
    search_fields = ("name",)
    autocomplete_fields = ("required_drive",)
    filter_horizontal = ("archetypes",)
    inlines = (TermsReactionLineInline,)


@admin.register(StandoffConfig)
class StandoffConfigAdmin(admin.ModelAdmin):
    """The singleton standoff tuning row (pk=1), with a preview of the cause numbers."""

    list_display = ("__str__", "read_check_type", "terms_check_type")
    change_form_template = "admin/standoffs/standoffconfig/change_form.html"
    fieldsets = (
        (
            "Checks and holds",
            {"fields": ("read_check_type", "terms_check_type", "pass_condition", "turn_condition")},
        ),
        ("Causes", {"fields": ("hunger_margin_step", "territory_patience", "botch_force_bands")}),
        (
            "Force",
            {
                "fields": (
                    "over_level_percent_per_tier",
                    "falter_force_percent",
                    "break_force_percent",
                    "band_force_percent",
                )
            },
        ),
        (
            "Terms and regard",
            {
                "fields": (
                    "terms_ease_faltering",
                    "terms_ease_broken",
                    "regard_per_band",
                    "regard_max_bands",
                )
            },
        ),
    )
    autocomplete_fields = (
        "read_check_type",
        "terms_check_type",
        "pass_condition",
        "turn_condition",
    )

    def render_change_form(  # noqa: PLR0913 - Django's own signature
        self, request, context, add=False, change=False, form_url="", obj=None
    ):
        """Inject the preview rail: what the Hunger step and Territory patience do (#4415)."""
        context["config_preview"] = config_preview(obj or StandoffConfig())
        return super().render_change_form(
            request, context, add=add, change=change, form_url=form_url, obj=obj
        )

    def has_add_permission(self, request: object) -> bool:  # noqa: ARG002
        """Prevent adding a second row; this is a pk=1 singleton."""
        return not StandoffConfig.objects.exists()

    def has_delete_permission(
        self,
        request: object,  # noqa: ARG002
        obj: object = None,  # noqa: ARG002
    ) -> bool:
        """The singleton cannot be deleted."""
        return False


@admin.register(StandoffCauseGloss)
class StandoffCauseGlossAdmin(admin.ModelAdmin):
    """One player-facing line per cause, shown under it once a read reveals it."""

    list_display = ("cause", "text")
