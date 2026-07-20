from rest_framework import serializers

from world.areas.models import Area


class WhereEntrySerializer(serializers.Serializer):
    """A `where` row: a present character + its Evennia-colour-coded room path (#1463)."""

    persona_name = serializers.CharField(read_only=True)
    room_path = serializers.CharField(read_only=True)
    room_id = serializers.IntegerField(read_only=True)


class WhoEntrySerializer(serializers.Serializer):
    """A `who` row: a present character's active-persona name + coarse idle (#1463)."""

    name = serializers.CharField(read_only=True)
    idle = serializers.CharField(read_only=True, allow_blank=True)


class AreaBreadcrumbSerializer(serializers.Serializer):
    """Lightweight serializer for area ancestry breadcrumbs."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    level = serializers.SerializerMethodField()

    def get_level(self, obj: Area) -> str:
        return obj.get_level_display()


class AreaListSerializer(serializers.ModelSerializer):
    level_display = serializers.CharField(source="get_level_display", read_only=True)
    children_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Area
        fields = ["id", "name", "level", "level_display", "children_count", "grid_x", "grid_y"]
        read_only_fields = fields


class AreaRoomSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    name = serializers.CharField(source="objectdb.db_key")
    area_name = serializers.CharField(source="area.name", default="")


class WorldBuilderAreaSerializer(serializers.ModelSerializer):
    """Area-tree node for the staff world-builder canvas (#2449).

    Unlike ``AreaListSerializer`` (player-facing area browser), this exposes
    ``slug``/``origin``/``parent`` — staff-only bookkeeping fields the canvas
    needs to render the AUTHORED/STORY/PLAYER distinction and the fixture-key
    promotion flow.
    """

    level_display = serializers.CharField(source="get_level_display", read_only=True)
    children_count = serializers.IntegerField(read_only=True)
    parent = serializers.IntegerField(source="parent_id", read_only=True, allow_null=True)

    class Meta:
        model = Area
        fields = [
            "id",
            "name",
            "slug",
            "level",
            "level_display",
            "origin",
            "parent",
            "children_count",
            "grid_x",
            "grid_y",
        ]
        read_only_fields = fields


class WorldBuilderRoomClueSerializer(serializers.Serializer):
    """One RoomClue placement, nested in a WorldBuilderRoom payload (#2451)."""

    id = serializers.IntegerField()
    clue_name = serializers.CharField()
    clue_slug = serializers.CharField()
    detect_difficulty = serializers.IntegerField()
    fixture_key = serializers.CharField(allow_null=True)


class WorldBuilderClueTriggerSerializer(serializers.Serializer):
    """One ClueTrigger placement, nested in a WorldBuilderRoom payload (#2451)."""

    id = serializers.IntegerField()
    clue_name = serializers.CharField()
    clue_slug = serializers.CharField()
    fixture_key = serializers.CharField(allow_null=True)


class WorldBuilderPortalAnchorSerializer(serializers.Serializer):
    """One active PortalAnchor, nested in a WorldBuilderRoom payload (#2451)."""

    id = serializers.IntegerField()
    kind_name = serializers.CharField()
    name = serializers.CharField()
    fixture_key = serializers.CharField(allow_null=True)


class WorldBuilderRoomSerializer(serializers.Serializer):
    """One RoomProfile in the staff area-manager payload (#2449).

    Unlike the owner-facing ``buildings.ManagerRoomSerializer``, this has no
    ownership gate (staff-only read) and includes private rooms plus
    staff-only bookkeeping (``fixture_key``, ``origin``, ``occupant_count``).
    """

    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    is_public = serializers.BooleanField()
    is_social_hub = serializers.BooleanField()
    is_outdoor = serializers.BooleanField()
    enclosure = serializers.CharField()
    size_name = serializers.CharField(allow_null=True)
    grid_x = serializers.IntegerField(allow_null=True)
    grid_y = serializers.IntegerField(allow_null=True)
    floor = serializers.IntegerField()
    fixture_key = serializers.CharField(allow_null=True)
    origin = serializers.CharField()
    occupant_count = serializers.IntegerField()
    clues = WorldBuilderRoomClueSerializer(many=True)
    clue_triggers = WorldBuilderClueTriggerSerializer(many=True)
    portal_anchors = WorldBuilderPortalAnchorSerializer(many=True)


class WorldBuilderExitSerializer(serializers.Serializer):
    """One directed exit in the staff area-manager payload (#2449).

    ``to_area_id`` is null when the destination has no RoomProfile (or no
    destination at all) — a cross-area exit is otherwise a normal row here,
    the canvas renders the far end as an edge-of-view marker.
    """

    id = serializers.IntegerField()
    name = serializers.CharField()
    from_room_id = serializers.IntegerField()
    to_room_id = serializers.IntegerField(allow_null=True)
    to_room_name = serializers.CharField(allow_null=True)
    to_area_id = serializers.IntegerField(allow_null=True)


class WorldBuilderAreaManagerSerializer(serializers.Serializer):
    """The full staff-only area-manager payload: area header + rooms + exits."""

    area = WorldBuilderAreaSerializer()
    rooms = WorldBuilderRoomSerializer(many=True)
    exits = WorldBuilderExitSerializer(many=True)
