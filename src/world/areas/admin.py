from django.contrib import admin
from django.db.models import Prefetch, QuerySet
from django.http import HttpRequest
from django.utils.html import format_html, format_html_join

from world.admin_utils import OneRowPerFormSet
from world.areas.models import Area, AreaElevationRequirement
from world.areas.positioning.models import (
    BlueprintEdge,
    BlueprintFeature,
    BlueprintPosition,
    BlueprintPositionShelter,
    FeatureType,
    MapTerrain,
    PositionBlueprint,
    PositionFeature,
    RampartElementProfile,
    RampartElementResistance,
)
from world.areas.worldmap.models import RegionMap, RegionMapUpload
from world.mechanics.models import ChallengeTemplateConsequence, ChallengeTemplateProperty
from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ["name", "level", "parent", "realm", "is_capital", "grid_x", "grid_y"]
    list_filter = ["level", "realm", "is_capital"]
    search_fields = ["name"]
    autocomplete_fields = ["parent", "realm", "exile_destination"]


@admin.register(AreaElevationRequirement)
class AreaElevationRequirementAdmin(admin.ModelAdmin):
    list_display = ["to_level", "min_held_buildings", "min_order_stat", "cost_coppers"]
    list_filter = ["to_level"]


# ---------------------------------------------------------------------------
# #3831 - positioning-graph blueprints and Rampart element catalog
# ---------------------------------------------------------------------------


@admin.register(MapTerrain)
class MapTerrainAdmin(admin.ModelAdmin):
    list_display = ["name", "art"]
    search_fields = ["name"]
    autocomplete_fields = ["art"]


class BlueprintPositionInline(admin.TabularInline):
    """#3831 - the position nodes belonging to a blueprint."""

    model = BlueprintPosition
    formset = OneRowPerFormSet
    extra = 1
    autocomplete_fields = ["terrain"]


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
    readonly_fields = ["features_table"]

    @admin.display(description="Features")
    def features_table(self, obj: PositionBlueprint) -> str:
        """Every feature the blueprint's places carry, read-only (edited on each place)."""
        if obj.pk is None:
            return "-"
        rows = BlueprintFeature.objects.filter(blueprint_position__blueprint=obj).select_related(
            "feature_type", "blueprint_position"
        )
        if not rows:
            return "No features yet."
        body = format_html_join(
            "",
            "<tr><td>{}</td><td>{}</td><td>{}</td></tr>",
            (
                (
                    row.feature_type.name,
                    row.blueprint_position.name,
                    "-" if row.square_x is None else f"{row.square_x}, {row.square_y}",
                )
                for row in rows
            ),
        )
        return format_html(
            "<table><thead><tr><th>Feature type</th><th>Where</th><th>Square</th></tr></thead>"
            "<tbody>{}</tbody></table>",
            body,
        )


@admin.register(FeatureType)
class FeatureTypeAdmin(admin.ModelAdmin):
    """#4675 - a feature staff attach to any place; its template is what a stunt rolls."""

    list_display = [
        "name",
        "reach",
        "challenge_template",
        "properties",
        "difficulty",
        "on_a_miss",
        "art",
    ]
    list_filter = ["reach"]
    search_fields = ["name"]
    list_select_related = ["challenge_template", "art"]
    autocomplete_fields = ["art", "challenge_template"]

    def get_queryset(self, request: HttpRequest) -> QuerySet[FeatureType]:
        return (
            super()
            .get_queryset(request)
            .prefetch_related(
                # Read through .all() on the cached rows; no per-instance attribute is wanted.
                Prefetch(  # noqa: PREFETCH_STRING
                    "challenge_template__challenge_template_properties",
                    queryset=ChallengeTemplateProperty.objects.select_related("property"),
                ),
                Prefetch(  # noqa: PREFETCH_STRING
                    "challenge_template__challenge_consequences",
                    queryset=ChallengeTemplateConsequence.objects.select_related(
                        "consequence__outcome_tier"
                    ),
                ),
            )
        )

    @admin.display(description="Properties")
    def properties(self, obj: FeatureType) -> str:
        links = obj.challenge_template.challenge_template_properties.all()
        return ", ".join(link.property.name for link in links)

    @admin.display(description="Difficulty")
    def difficulty(self, obj: FeatureType) -> str:
        """The band whose value sits nearest the template's severity."""
        severity = obj.challenge_template.severity
        band = min(DIFFICULTY_VALUES, key=lambda b: abs(DIFFICULTY_VALUES[b] - severity))
        return DifficultyChoice(band).label

    @admin.display(description="On a miss")
    def on_a_miss(self, obj: FeatureType) -> str:
        links = obj.challenge_template.challenge_consequences.all()
        return ", ".join(
            link.consequence.label
            for link in links
            if link.consequence.outcome_tier.success_level < 1
        )


class BlueprintFeatureInline(admin.TabularInline):
    """#4675 - the features a blueprint place carries."""

    model = BlueprintFeature
    extra = 1
    autocomplete_fields = ["feature_type"]
    fields = ["feature_type", "square_x", "square_y"]


@admin.register(PositionFeature)
class PositionFeatureAdmin(admin.ModelAdmin):
    """#4675 - features standing in live places, for staff fixes."""

    list_display = ["feature_type", "position", "square_x", "square_y"]
    list_filter = ["feature_type"]
    search_fields = ["feature_type__name", "position__name"]
    list_select_related = ["feature_type", "position"]
    autocomplete_fields = ["feature_type"]
    raw_id_fields = ["position"]


@admin.register(BlueprintPosition)
class BlueprintPositionAdmin(admin.ModelAdmin):
    """#3831 - a position-node template belonging to a PositionBlueprint."""

    list_display = ["name", "blueprint", "kind", "is_roofed", "screens_ranged"]
    list_filter = ["kind", "is_roofed", "screens_ranged"]
    search_fields = ["name", "blueprint__name"]
    list_select_related = ["blueprint"]
    autocomplete_fields = ["blueprint"]
    inlines = [BlueprintFeatureInline]


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
    formset = OneRowPerFormSet
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


# ---------------------------------------------------------------------------
# #4242 - the world map: region maps and their kept uploads (pips are not
# browsed here; the Atlas's region-map view is their surface)
# ---------------------------------------------------------------------------


class RegionMapUploadInline(admin.TabularInline):
    model = RegionMapUpload
    extra = 0
    can_delete = False
    fields = [
        "file_name",
        "byte_size",
        "generator_version",
        "source_width_px",
        "source_height_px",
        "uploaded_by",
        "uploaded_at",
        "rasterized_at",
    ]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool:  # noqa: ARG002
        return False


@admin.register(RegionMap)
class RegionMapAdmin(admin.ModelAdmin):
    list_display = ["name", "area", "anchor_x", "anchor_y", "width_cells", "height_cells"]
    search_fields = ["name"]
    autocomplete_fields = ["area", "created_by"]
    readonly_fields = ["height_cells", "created_at"]
    inlines = [RegionMapUploadInline]
