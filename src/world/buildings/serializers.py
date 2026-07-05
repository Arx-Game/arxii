"""Serializers for the building-manager read API (#670 PR2).

Reads only — every mutation flows through the action-dispatch seam
(``POST /api/actions/characters/<id>/dispatch/``), so there are no write
serializers here. The manager payload is composed from plain dicts built
in the view (keeps per-request data off SharedMemoryModel instances).
"""

from __future__ import annotations

from rest_framework import serializers

from evennia_extensions.models import RoomSizeTier
from world.buildings.models import ArchitecturalStyle, BuildingKind, ProjectTemplate


class CharacterContextRequestSerializer(serializers.Serializer):
    """``?character_id=`` — the viewer's character (must be the account's own)."""

    character_id = serializers.IntegerField(required=True)


class ManagerTenancySerializer(serializers.Serializer):
    """An active tenancy row, as the building owner sees it."""

    id = serializers.IntegerField()
    tenant_persona_id = serializers.IntegerField()
    tenant_name = serializers.CharField()
    is_primary_home = serializers.BooleanField()
    ends_at = serializers.DateTimeField(allow_null=True)


class ManagerRoomSerializer(serializers.Serializer):
    """One room in the manager payload (id = the room's ObjectDB pk)."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    is_public = serializers.BooleanField()
    size_name = serializers.CharField(allow_null=True)
    size_units = serializers.IntegerField(allow_null=True)
    grid_x = serializers.IntegerField(allow_null=True)
    grid_y = serializers.IntegerField(allow_null=True)
    floor = serializers.IntegerField()
    is_entry = serializers.BooleanField()
    tenancies = ManagerTenancySerializer(many=True)


class ManagerExitSerializer(serializers.Serializer):
    """One directed exit between two rooms of the building."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    from_room_id = serializers.IntegerField()
    to_room_id = serializers.IntegerField()


class ManagerBuildingSerializer(serializers.Serializer):
    """Building header: identity, style, and the space budget meter."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    kind = serializers.CharField()
    style = serializers.CharField(allow_null=True)
    renovation_cost = serializers.IntegerField(allow_null=True)
    space_budget = serializers.IntegerField()
    space_used = serializers.IntegerField()
    space_remaining = serializers.IntegerField()
    entry_room_id = serializers.IntegerField(allow_null=True)
    floors = serializers.ListField(child=serializers.IntegerField())


class BuildingManagerSerializer(serializers.Serializer):
    """The full owner-facing manager payload."""

    building = ManagerBuildingSerializer()
    rooms = ManagerRoomSerializer(many=True)
    exits = ManagerExitSerializer(many=True)


class ForRoomResultSerializer(serializers.Serializer):
    """Cheap RoomPanel resolver: which building, and what the viewer may do."""

    building_id = serializers.IntegerField(allow_null=True)
    is_owner = serializers.BooleanField()
    is_tenant = serializers.BooleanField()
    is_primary_home_here = serializers.BooleanField()


class RoomSizeTierSerializer(serializers.ModelSerializer):
    """The shared room-size unit ladder."""

    class Meta:
        model = RoomSizeTier
        fields = ["id", "name", "units"]


class PolishIncrementSerializer(serializers.Serializer):
    """Per-category polish a decoration template grants on completion."""

    category = serializers.CharField(source="category.name")
    value = serializers.IntegerField()


class DecorationTemplateSerializer(serializers.ModelSerializer):
    """An INTERIOR_DESIGN ProjectTemplate row from the admin-authored catalog."""

    increments = PolishIncrementSerializer(source="prefetched_increments", many=True)
    tier_prerequisites = serializers.StringRelatedField(source="prefetched_tier_prereqs", many=True)

    class Meta:
        model = ProjectTemplate
        fields = [
            "id",
            "name",
            "description",
            "base_cost",
            "weekly_upkeep_cost",
            "increments",
            "tier_prerequisites",
        ]


class BuildingKindSerializer(serializers.ModelSerializer):
    """An authorable building category for the renovation picker (#1882).

    Open catalog — rows authored by staff. Each row carries non-exclusive
    descriptive flags the picker badges (a fortified witch-king manor is
    ``residential + fortified + occult + aerial``).
    """

    class Meta:
        model = BuildingKind
        fields = [
            "id",
            "name",
            "description",
            "is_residential",
            "is_commercial",
            "is_fortified",
            "is_occult",
            "is_maritime",
            "is_agrarian",
            "is_aerial",
            "is_subterranean",
            "is_secret",
        ]


class ArchitecturalStyleSerializer(serializers.ModelSerializer):
    """An authorable architectural style for the builder picker (#1882).

    The player-facing lore lives in the linked ``CodexSubject`` — knowing that
    subject is what gates throwback styles (``can_build_style``). The description
    is surfaced inline here so the picker needn't hit the Codex app.
    """

    description = serializers.CharField(source="codex_subject.description", allow_null=True)

    class Meta:
        model = ArchitecturalStyle
        fields = ["id", "name", "description", "is_default", "prestige_bonus", "cost_multiplier"]


class ExposureAxisSerializer(serializers.Serializer):
    """One axis of the owner build-HUD: pressure vs mitigation vs residual (#1514)."""

    key = serializers.CharField()
    pressure = serializers.IntegerField()
    mitigation = serializers.IntegerField()
    net = serializers.IntegerField()
    sheltered = serializers.BooleanField()


class PlacedFixtureSerializer(serializers.Serializer):
    """A comfort fixture placed in the room (removable from the HUD)."""

    id = serializers.IntegerField()
    kind = serializers.CharField()


class FixtureAffinitySerializer(serializers.Serializer):
    """One axis a fixture kind mitigates (negative value = mitigation)."""

    key = serializers.CharField()
    value = serializers.IntegerField()


class FixtureKindSerializer(serializers.Serializer):
    """A placeable fixture kind from the admin-authored catalog."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    amenity = serializers.IntegerField()
    affinities = FixtureAffinitySerializer(many=True)


class RoomComfortBreakdownSerializer(serializers.Serializer):
    """The owner build-HUD payload for one room (#1514)."""

    enclosure = serializers.CharField()
    level = serializers.IntegerField()
    points = serializers.IntegerField()
    amenity = serializers.IntegerField()
    axes = ExposureAxisSerializer(many=True)
    fixtures = PlacedFixtureSerializer(many=True)
    fixture_kinds = FixtureKindSerializer(many=True)
