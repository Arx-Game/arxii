from django.contrib import admin

from world.areas.models import Area
from world.areas.positioning.models import (
    BlueprintEdge,
    BlueprintPosition,
    BlueprintPositionShelter,
    PositionBlueprint,
    RampartElementProfile,
    RampartElementResistance,
)


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ["name", "level", "parent", "realm", "grid_x", "grid_y"]
    list_filter = ["level", "realm"]
    search_fields = ["name"]
    autocomplete_fields = ["parent", "realm", "exile_destination"]


# ---------------------------------------------------------------------------
# #3831 - positioning-graph blueprints and Rampart element catalog
# ---------------------------------------------------------------------------


class BlueprintPositionInline(admin.TabularInline):
    """#3831 - the position nodes belonging to a blueprint."""

    model = BlueprintPosition
    extra = 1


class BlueprintEdgeInline(admin.TabularInline):
    """#3831 - the adjacency edges between a blueprint's position nodes."""

    model = BlueprintEdge
    fk_name = "blueprint"
    extra = 1
    autocomplete_fields = ["position_a", "position_b", "gating_challenge_template"]


@admin.register(PositionBlueprint)
class PositionBlueprintAdmin(admin.ModelAdmin):
    """#3831 - a reusable position/edge template GMs apply to any room."""

    list_display = ["name"]
    search_fields = ["name", "description"]
    inlines = [BlueprintPositionInline, BlueprintEdgeInline]


@admin.register(BlueprintPosition)
class BlueprintPositionAdmin(admin.ModelAdmin):
    """#3831 - a position-node template belonging to a PositionBlueprint."""

    list_display = ["name", "blueprint", "kind"]
    list_filter = ["kind"]
    search_fields = ["name", "blueprint__name"]
    list_select_related = ["blueprint"]
    autocomplete_fields = ["blueprint"]


@admin.register(BlueprintEdge)
class BlueprintEdgeAdmin(admin.ModelAdmin):
    """#3831 - an adjacency edge template between two BlueprintPositions."""

    list_display = ["blueprint", "position_a", "position_b", "is_passable"]
    list_filter = ["is_passable"]
    search_fields = ["blueprint__name"]
    list_select_related = ["blueprint", "position_a", "position_b"]
    autocomplete_fields = ["blueprint", "position_a", "position_b", "gating_challenge_template"]


@admin.register(BlueprintPositionShelter)
class BlueprintPositionShelterAdmin(admin.ModelAdmin):
    """#3831 - a template shelter cloned into a PositionShelter on instantiation."""

    list_display = ["blueprint_position", "damage_type", "value", "applies_to_attacks"]
    list_filter = ["applies_to_attacks"]
    search_fields = ["blueprint_position__name"]
    list_select_related = ["blueprint_position", "damage_type"]
    autocomplete_fields = ["blueprint_position", "damage_type"]


class RampartElementResistanceInline(admin.TabularInline):
    """#3831 - per-damage-type resist/vulnerability rows for a Rampart element."""

    model = RampartElementResistance
    fk_name = "profile"
    extra = 1
    autocomplete_fields = ["damage_type"]


@admin.register(RampartElementProfile)
class RampartElementProfileAdmin(admin.ModelAdmin):
    """#3831 - a reusable Rampart element (Stone/Wind/Fire/Thorn/...) catalog row."""

    list_display = ["name", "signature_behavior", "signature_value"]
    list_filter = ["signature_behavior"]
    search_fields = ["name", "description"]
    autocomplete_fields = ["signature_damage_type", "signature_condition"]
    inlines = [RampartElementResistanceInline]


@admin.register(RampartElementResistance)
class RampartElementResistanceAdmin(admin.ModelAdmin):
    """#3831 - a per-damage-type resist/vulnerability row for a Rampart element."""

    list_display = ["profile", "damage_type", "value"]
    search_fields = ["profile__name"]
    list_select_related = ["profile", "damage_type"]
    autocomplete_fields = ["profile", "damage_type"]
