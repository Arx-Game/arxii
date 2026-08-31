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
    # Phase C metadata (#3269) — name-resolved reads for the edit-area dialog.
    realm = serializers.SerializerMethodField()
    climate = serializers.SerializerMethodField()
    dominant_society = serializers.SerializerMethodField()
    effective_climate = serializers.SerializerMethodField()

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
            "realm",
            "climate",
            "dominant_society",
            "effective_climate",
            "description",
            "color",
            "permit_eligibility",
        ]
        read_only_fields = fields

    def get_realm(self, obj: Area) -> str | None:
        return obj.realm.name if obj.realm_id else None

    def get_climate(self, obj: Area) -> str | None:
        return obj.climate.name if obj.climate_id else None

    def get_dominant_society(self, obj: Area) -> str | None:
        return obj.dominant_society.name if obj.dominant_society_id else None

    def get_effective_climate(self, obj: Area) -> str | None:
        """The inherited climate + its source, e.g. "Temperate (from Arx Region)"."""
        node = obj
        while node is not None:
            if node.climate_id is not None:
                suffix = "" if node.pk == obj.pk else f" (from {node.name})"
                return f"{node.climate.name}{suffix}"
            node = node.parent
        return None


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


class WorldBuilderRoomHitSerializer(serializers.Serializer):
    """One cross-area room-search hit (#3269): the where-did-I-put-it seam."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    area_id = serializers.IntegerField(allow_null=True)
    area_name = serializers.CharField(allow_null=True)
    floor = serializers.IntegerField()
    fixture_key = serializers.CharField(allow_null=True)


class WorldBuilderRoomStatSerializer(serializers.Serializer):
    """One ambient-stat row in the staff room payload (#3269)."""

    key = serializers.CharField()
    label = serializers.CharField()
    default = serializers.IntegerField()
    effective = serializers.IntegerField()
    authored = serializers.IntegerField(allow_null=True)
    pinned = serializers.IntegerField(allow_null=True)


class WorldBuilderPlaceSerializer(serializers.Serializer):
    """One conversational sub-location in the staff room payload (#3269)."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)


class WorldBuilderRoomFeatureSerializer(serializers.Serializer):
    """The room's active feature, if any (#3269)."""

    kind = serializers.CharField()
    level = serializers.IntegerField()


class WorldBuilderAmbientCountsSerializer(serializers.Serializer):
    """Entry-line/linger-emit counts for the Atmosphere section (#3269)."""

    lines = serializers.IntegerField()
    emits = serializers.IntegerField()


class WorldBuilderTravelHubSerializer(serializers.Serializer):
    """Travel-hub flag payload (#3269) — routes/methods are content-owned."""

    name = serializers.CharField()
    travel_modes = serializers.ListField(child=serializers.CharField())
    is_transit_stop = serializers.BooleanField()


class WorldBuilderExitDetailSerializer(serializers.Serializer):
    """One outgoing exit with its profile detail (#3269 room-detail endpoint)."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    to_room_id = serializers.IntegerField(allow_null=True)
    kind = serializers.CharField()
    is_open = serializers.BooleanField()
    aliases = serializers.ListField(child=serializers.CharField())


class WorldBuilderComfortAxisSerializer(serializers.Serializer):
    key = serializers.CharField()
    pressure = serializers.IntegerField()
    mitigation = serializers.IntegerField()
    net = serializers.IntegerField()
    sheltered = serializers.BooleanField()


class WorldBuilderComfortSerializer(serializers.Serializer):
    level = serializers.IntegerField()
    points = serializers.IntegerField()
    amenity = serializers.IntegerField()
    axes = WorldBuilderComfortAxisSerializer(many=True)


class WorldBuilderAmbientLineSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    arriver_body = serializers.CharField(allow_blank=True)
    bystander_body = serializers.CharField(allow_blank=True)


class WorldBuilderAmbientEmitSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    key = serializers.CharField(allow_blank=True)
    text = serializers.CharField()
    gate_stat_key = serializers.CharField(allow_blank=True)
    gate_min = serializers.IntegerField(allow_null=True)
    gate_max = serializers.IntegerField(allow_null=True)


class WorldBuilderIdNameSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class WorldBuilderCatalogsSerializer(serializers.Serializer):
    """Panel pick-lists (#3269)."""

    realms = serializers.ListField(child=serializers.CharField())
    climates = serializers.ListField(child=serializers.CharField())
    societies = serializers.ListField(child=serializers.CharField())
    permit_options = serializers.ListField(child=serializers.CharField())
    feature_kinds = serializers.ListField(child=serializers.CharField())
    npc_roles = serializers.ListField(child=serializers.CharField())
    blueprints = serializers.ListField(child=serializers.CharField())
    size_tiers = serializers.ListField(child=serializers.CharField())
    starting_areas = WorldBuilderIdNameSerializer(many=True)
    beginnings = WorldBuilderIdNameSerializer(many=True)


class WorldBuilderBreadcrumbSerializer(serializers.Serializer):
    """One ancestor link in the area hierarchy chain (#3283)."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    level_display = serializers.CharField()


class WorldBuilderRoomDescVariantSerializer(serializers.Serializer):
    """One authored season/phase description variant (#3291)."""

    id = serializers.IntegerField()
    season = serializers.CharField(allow_null=True)
    phase = serializers.CharField(allow_null=True)
    description = serializers.CharField()


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
    exported_at = serializers.DateTimeField(allow_null=True)
    # #3477 — null means unpublished/WIP: not enterable, exits hidden from
    # non-story-runners, until staff_publish_room stamps it.
    published_at = serializers.DateTimeField(allow_null=True)
    needs_prose = serializers.BooleanField()
    stats = WorldBuilderRoomStatSerializer(many=True)
    area_id = serializers.IntegerField(allow_null=True)
    size_units = serializers.IntegerField(allow_null=True)
    default_blueprint = serializers.CharField(allow_null=True)
    places = WorldBuilderPlaceSerializer(many=True)
    feature = WorldBuilderRoomFeatureSerializer(allow_null=True)
    functionaries = serializers.ListField(child=serializers.CharField())
    ambient_counts = WorldBuilderAmbientCountsSerializer()
    travel_hub = WorldBuilderTravelHubSerializer(allow_null=True)
    starting_bindings = serializers.ListField(child=serializers.CharField())
    occupant_count = serializers.IntegerField()
    clues = WorldBuilderRoomClueSerializer(many=True)
    clue_triggers = WorldBuilderClueTriggerSerializer(many=True)
    portal_anchors = WorldBuilderPortalAnchorSerializer(many=True)
    desc_variants = WorldBuilderRoomDescVariantSerializer(many=True)


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


class WorldBuilderRoomDetailSerializer(serializers.Serializer):
    """Selection-time room detail (#3269): exit profiles + comfort breakdown."""

    id = serializers.IntegerField()
    room = WorldBuilderRoomSerializer()
    catalogs = WorldBuilderCatalogsSerializer()
    breadcrumb = WorldBuilderBreadcrumbSerializer(many=True)
    exits = WorldBuilderExitDetailSerializer(many=True)
    comfort = WorldBuilderComfortSerializer()
    ambient_lines = WorldBuilderAmbientLineSerializer(many=True)
    ambient_emits = WorldBuilderAmbientEmitSerializer(many=True)


class WorldBuilderAreaManagerSerializer(serializers.Serializer):
    """The full staff-only area-manager payload: area header + rooms + exits."""

    area = WorldBuilderAreaSerializer()
    catalogs = WorldBuilderCatalogsSerializer()
    breadcrumb = WorldBuilderBreadcrumbSerializer(many=True)
    rooms = WorldBuilderRoomSerializer(many=True)
    exits = WorldBuilderExitSerializer(many=True)
