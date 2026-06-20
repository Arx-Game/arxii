from drf_spectacular.utils import extend_schema_field
from evennia.objects.models import ObjectDB
from rest_framework import serializers

from world.areas.positioning.serializers import (
    PersonaPositionSerializer,
    PositionAdjacencyItemSerializer,
    PositionSummarySerializer,
)
from world.scenes.constants import ScenePrivacyMode
from world.scenes.models import (
    Persona,
    Scene,
    SceneParticipation,
    SceneSummaryRevision,
)


class PersonaSerializer(serializers.ModelSerializer):
    roster_entry = serializers.SerializerMethodField()
    thumbnail_media_url = serializers.SerializerMethodField()

    class Meta:
        model = Persona
        fields = [
            "id",
            "character_sheet",
            "name",
            "is_fake_name",
            "persona_type",
            "description",
            "thumbnail_url",
            "thumbnail_media_url",
            "roster_entry",
        ]
        read_only_fields = ["roster_entry"]

    def get_thumbnail_media_url(self, obj: Persona) -> str | None:
        if obj.thumbnail_id is None:
            return None
        return obj.thumbnail.cloudinary_url

    def get_roster_entry(self, obj: Persona) -> dict[str, int | str] | None:
        try:
            entry = obj.character_sheet.roster_entry
        except AttributeError:
            entry = None
        if entry:
            return {"id": entry.id, "name": entry.character_sheet.character.db_key}
        return None


class SceneParticipantSerializer(serializers.ModelSerializer):
    """Simplified participant representation for scene lists"""

    roster_entry = serializers.SerializerMethodField()
    dramatic_moment_count = serializers.SerializerMethodField()

    class Meta:
        model = Persona
        fields = ["id", "name", "roster_entry", "dramatic_moment_count"]

    def get_roster_entry(self, obj):
        try:
            entry = obj.character_sheet.roster_entry
        except AttributeError:
            entry = None
        if entry:
            return {"id": entry.id, "name": entry.character_sheet.character.db_key}
        return None

    def get_dramatic_moment_count(self, obj) -> int:
        sheet = getattr(obj, "character_sheet", None)  # noqa: GETATTR_LITERAL - Persona.character_sheet FK; getattr used for None-safety across nullable FK
        if sheet is None:
            return 0
        count_map: dict[int, int] = self.context.get("dramatic_moment_counts", {})
        return count_map.get(sheet.pk, 0)


class SceneListSerializer(serializers.ModelSerializer):
    """Simplified scene representation for lists"""

    participants = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    location_id = serializers.PrimaryKeyRelatedField(
        queryset=ObjectDB.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
        source="location",
    )
    is_owner = serializers.SerializerMethodField()
    viewer_can_gm = serializers.SerializerMethodField()

    class Meta:
        model = Scene
        fields = [
            "id",
            "name",
            "description",
            "date_started",
            "location",
            "location_id",
            "participants",
            "is_owner",
            "viewer_can_gm",
        ]

    def get_location(self, obj):
        if obj.location:
            return {"id": obj.location.id, "name": obj.location.db_key}
        return None

    def get_participants(self, obj: Scene) -> list[dict]:
        personas = self._collect_personas(obj, only_real_names=True)
        # Build a {character_sheet_id: count} map from the prefetched tags
        # (cached_scene_drama_tags set by SceneViewSet.get_queryset) to avoid N+1.
        # Falls back to an empty map if the attr is absent (e.g. direct
        # serializer instantiation in tests that don't use the viewset).
        cached_tags = getattr(obj, "cached_scene_drama_tags", None)  # noqa: GETATTR_LITERAL - Prefetch(to_attr=...) sets this
        if cached_tags is not None:
            count_map: dict[int, int] = {}
            for tag in cached_tags:
                count_map[tag.character_sheet_id] = count_map.get(tag.character_sheet_id, 0) + 1
        else:
            count_map = {}
        return SceneParticipantSerializer(
            personas,
            many=True,
            context={"scene": obj, "dramatic_moment_counts": count_map},
        ).data

    @staticmethod
    def _collect_personas(obj: Scene, *, only_real_names: bool) -> list[Persona]:
        """Dedup personas reachable via the scene's interactions.

        Reads from the ``cached_interactions`` attribute populated by
        SceneViewSet's prefetch. Falls back to a fresh query if the serializer
        is used outside the viewset (e.g., direct instantiation in tests).
        """
        cached = getattr(obj, "cached_interactions", None)  # noqa: GETATTR_LITERAL - Prefetch(to_attr=...) sets this
        if cached is None:
            cached = list(
                obj.interactions.select_related(
                    "persona__character_sheet__character",
                    "persona__character_sheet__roster_entry",
                    "persona__thumbnail",
                )
            )
        seen: dict[int, Persona] = {}
        for interaction in cached:
            persona = interaction.persona
            if persona is None or persona.pk in seen:
                continue
            if only_real_names and persona.is_fake_name:
                continue
            seen[persona.pk] = persona
        return list(seen.values())

    def get_is_owner(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.is_owner(request.user)
        return False

    def get_viewer_can_gm(self, obj: Scene) -> bool:
        request = self.context.get("request")
        if not (request and request.user and request.user.is_authenticated):
            return False
        user = request.user
        return bool(user.is_staff or obj.is_gm(user) or obj.is_owner(user))


class SceneDetailSerializer(SceneListSerializer):
    """Full scene representation with personas"""

    personas = serializers.SerializerMethodField()
    positions = serializers.SerializerMethodField()
    position_adjacency = serializers.SerializerMethodField()
    persona_positions = serializers.SerializerMethodField()

    class Meta(SceneListSerializer.Meta):
        model = Scene
        fields = [
            *SceneListSerializer.Meta.fields,
            "date_finished",
            "is_active",
            "privacy_mode",
            "personas",
            "positions",
            "position_adjacency",
            "persona_positions",
        ]
        extra_kwargs = {"name": {"required": False}}

    def get_personas(self, obj: Scene) -> list[dict]:
        personas = self._collect_personas(obj, only_real_names=False)
        return PersonaSerializer(personas, many=True).data

    def get_participants(self, obj):
        return super().get_participants(obj)

    @extend_schema_field(PositionSummarySerializer(many=True))
    def get_positions(self, obj: Scene) -> list[dict]:
        """Return all positions in the scene's room as [{id, name}].

        Returns an empty list when the scene has no location.
        """
        if obj.location is None:
            return []
        from world.areas.positioning.models import Position  # noqa: PLC0415

        positions = Position.objects.filter(room=obj.location)
        return PositionSummarySerializer(positions, many=True).data  # type: ignore[return-value]

    @extend_schema_field(PositionAdjacencyItemSerializer(many=True))
    def get_position_adjacency(self, obj: Scene) -> list[dict]:
        """Return ADJACENT-reach position adjacency for the scene's room.

        Each entry is ``{position_id: int, adjacent_position_ids: [int]}``.
        Returns an empty list when the scene has no location.
        """
        if obj.location is None:
            return []
        from world.areas.positioning.services import room_position_adjacency  # noqa: PLC0415

        entries = room_position_adjacency(obj.location)
        return PositionAdjacencyItemSerializer(entries, many=True).data  # type: ignore[return-value]

    @extend_schema_field(PersonaPositionSerializer(many=True))
    def get_persona_positions(self, obj: Scene) -> list[dict]:
        """Return [{persona_id, position: {id, name} | null}] for each persona in the scene.

        Resolves position via persona.character_sheet.character → position_of(character).
        Returns an empty list when the scene has no location.
        """
        if obj.location is None:
            return []
        from world.areas.positioning.services import position_of  # noqa: PLC0415

        personas = self._collect_personas(obj, only_real_names=False)
        result = []
        for persona in personas:
            position = None
            if persona.character_sheet is not None:
                character = persona.character_sheet.character
                if character is not None:
                    pos = position_of(character)
                    if pos is not None:
                        position = PositionSummarySerializer(pos).data
            result.append({"persona_id": persona.pk, "position": position})
        return result


class ScenesSpotlightSerializer(serializers.Serializer):
    """
    Serializer for the spotlight endpoint that matches frontend expectations
    """

    in_progress = SceneListSerializer(many=True, source="active_scenes")
    recent = SceneListSerializer(many=True, source="recent_scenes")


class SceneSummaryRevisionSerializer(serializers.ModelSerializer):
    persona_name = serializers.CharField(source="persona.name", read_only=True)

    class Meta:
        model = SceneSummaryRevision
        fields = ["id", "scene", "persona", "persona_name", "content", "action", "timestamp"]
        read_only_fields = ["timestamp"]

    def validate(self, attrs: dict) -> dict:
        scene = attrs.get("scene")
        persona = attrs.get("persona")

        if scene and scene.privacy_mode != ScenePrivacyMode.EPHEMERAL:
            raise serializers.ValidationError(
                {"scene": "Summary revisions can only be submitted for ephemeral scenes."}
            )

        if persona:
            request = self.context.get("request")
            if request and request.user.is_authenticated:
                # Check the requesting user owns the character behind this persona
                roster_entry = getattr(persona.character_sheet, "roster_entry", None)  # noqa: GETATTR_LITERAL
                if roster_entry is None:
                    raise serializers.ValidationError(
                        {"persona": "Persona's character has no roster entry."}
                    )
                from world.roster.models import RosterTenure  # noqa: PLC0415

                owns_character = RosterTenure.objects.filter(
                    roster_entry=roster_entry,
                    player_data__account=request.user,
                    end_date__isnull=True,
                ).exists()
                if not owns_character:
                    raise serializers.ValidationError(
                        {"persona": "You can only submit revisions as your own persona."}
                    )

        if scene and persona:
            # Check that persona's character's account is a scene participant
            from world.roster.models import RosterTenure  # noqa: PLC0415

            roster_entry = getattr(persona.character_sheet.character, "roster_entry", None)  # noqa: GETATTR_LITERAL
            if roster_entry:
                active_tenure = (
                    RosterTenure.objects.filter(
                        roster_entry=roster_entry,
                        end_date__isnull=True,
                    )
                    .select_related("player_data")
                    .first()
                )
                if active_tenure:
                    is_participant = SceneParticipation.objects.filter(
                        scene=scene,
                        account=active_tenure.player_data.account,
                    ).exists()
                    if not is_participant:
                        raise serializers.ValidationError(
                            {"persona": "Persona must belong to a participant of this scene."}
                        )

        return attrs


class SetActivePersonaRequestSerializer(serializers.Serializer):
    """POST body for the #981 set-active-persona endpoint."""

    persona_id = serializers.IntegerField(min_value=1)


class ActivePersonaResultSerializer(serializers.Serializer):
    """Result of the #981 set-active-persona endpoint — the now-worn face id."""

    active_persona_id = serializers.IntegerField(read_only=True)
