"""Django admin for standoffs: creature drives and regard rules, approaches, terms, config."""

from django.contrib import admin

from world.standoffs.models import (
    CreatureDrive,
    RegardRule,
    StandoffApproach,
    StandoffConfig,
    StandoffTerms,
)


class CreatureDriveInline(admin.TabularInline):
    """Drives edited on the creature template page."""

    model = CreatureDrive
    extra = 0
    autocomplete_fields = ("property",)


class RegardRuleInline(admin.StackedInline):
    """Regard rules edited on the creature template page (stacked: they carry prose)."""

    model = RegardRule
    extra = 0
    autocomplete_fields = ("drive", "deed_archetype")


@admin.register(StandoffApproach)
class StandoffApproachAdmin(admin.ModelAdmin):
    list_display = ("name", "check_type", "capability", "damages_morale", "display_order")
    search_fields = ("name",)
    autocomplete_fields = ("check_type", "capability", "sway_target")
    filter_horizontal = ("archetypes",)


@admin.register(StandoffTerms)
class StandoffTermsAdmin(admin.ModelAdmin):
    list_display = ("name", "effect", "required_drive", "difficulty_shift_bands", "display_order")
    list_filter = ("effect",)
    search_fields = ("name",)
    autocomplete_fields = ("required_drive",)
    filter_horizontal = ("archetypes",)


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
