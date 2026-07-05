"""Admin registrations for buildings lookup tables (#670, #1469).

Only the tuning lookups are registered — Buildings themselves are
game-state mutated through services, not hand-edited.
"""

from typing import ClassVar

from django.contrib import admin

from world.buildings.models import (
    ArchitecturalStyle,
    BuildingSizeTier,
    MaterialLoreEffect,
    StyleAffinity,
)


@admin.register(BuildingSizeTier)
class BuildingSizeTierAdmin(admin.ModelAdmin):
    list_display: ClassVar[list[str]] = ["tier", "name", "space_budget"]
    ordering: ClassVar[list[str]] = ["tier"]


class StyleAffinityInline(admin.TabularInline):
    model = StyleAffinity
    extra = 0


@admin.register(ArchitecturalStyle)
class ArchitecturalStyleAdmin(admin.ModelAdmin):
    """The style catalog (#1469) — names, tiers, and placeholder magnitudes are content."""

    list_display: ClassVar[list[str]] = [
        "name",
        "is_default",
        "is_active",
        "prestige_bonus",
        "cost_multiplier",
        "codex_subject",
    ]
    list_filter: ClassVar[list[str]] = ["is_default", "is_active"]
    search_fields: ClassVar[list[str]] = ["name"]
    inlines: ClassVar[list[type[admin.TabularInline]]] = [StyleAffinityInline]


@admin.register(MaterialLoreEffect)
class MaterialLoreEffectAdmin(admin.ModelAdmin):
    """The material-lore catalog — content authored here, not in code (#695)."""

    list_display: ClassVar[list[str]] = [
        "template",
        "target_stat",
        "units_per_tier",
        "magnitude_per_tier",
        "max_tiers",
    ]
    list_filter: ClassVar[list[str]] = ["target_stat"]
    search_fields: ClassVar[list[str]] = ["template__name", "target_stat"]
    autocomplete_fields: ClassVar[list[str]] = ["template"]
