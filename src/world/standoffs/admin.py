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
    """The singleton standoff tuning row (pk=1)."""

    list_display = ("__str__", "read_check_type", "terms_check_type")
    autocomplete_fields = (
        "read_check_type",
        "terms_check_type",
        "pass_condition",
        "turn_condition",
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
