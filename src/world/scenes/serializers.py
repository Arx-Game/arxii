from evennia.objects.models import ObjectDB
from rest_framework import serializers

from world.scenes.constants import ScenePrivacyMode
from world.scenes.models import (
    Persona,
    Scene,
    SceneParticipation,
    SceneSummaryRevision,
)


class PersonaSerializer(serializers.ModelSerializer):
    roster_entry = serializers.SerializerMethodField()

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
            "character",
            "roster_entry",
        ]
        read_only_fields = ["roster_entry"]

    def get_roster_entry(self, obj: Persona) -> dict[str, int | str] | None:
        try:
            entry = obj.character_sheet.character.roster_entry
        except AttributeError:
            entry = None
        if entry:
            return {"id": entry.id, "name": entry.character_sheet.character.db_key}
        return None

    def create(self, validated_data: dict) -> Persona:
        # During the character_identity -> character_sheet transition, the
        # Persona model still requires character_identity (NOT NULL). Fill it
        # in from the character's identity so API callers don't need to know
        # about the legacy field.
        if "character_identity" not in validated_data:  # noqa: STRING_LITERAL — transitional shim, removed with Task 15
            from world.character_sheets.identity_services import (  # noqa: PLC0415
                ensure_character_identity,
            )

            character = validated_data.get("character") or (
                validated_data["character_sheet"].character  # noqa: STRING_LITERAL — transitional shim, removed with Task 15
                if "character_sheet" in validated_data  # noqa: STRING_LITERAL — transitional shim, removed with Task 15
                else None
            )
            if character is not None:
                validated_data["character_identity"] = ensure_character_identity(character)  # noqa: STRING_LITERAL — transitional shim, removed with Task 15
        return super().create(validated_data)


class SceneParticipantSerializer(serializers.ModelSerializer):
    """Simplified participant representation for scene lists"""

    roster_entry = serializers.SerializerMethodField()

    class Meta:
        model = Persona
        fields = ["id", "name", "roster_entry"]

    def get_roster_entry(self, obj):
        try:
            entry = obj.character_sheet.character.roster_entry
        except AttributeError:
            entry = None
        if entry:
            return {"id": entry.id, "name": entry.character_sheet.character.db_key}
        return None


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
        ]

    def get_location(self, obj):
        if obj.location:
            return {"id": obj.location.id, "name": obj.location.db_key}
        return None

    def get_participants(self, obj: Scene) -> list[dict]:
        personas = (
            Persona.objects.filter(
                interactions_written__scene=obj,
                is_fake_name=False,
            )
            .distinct()
            .select_related("character_sheet__character__roster_entry")
        )
        return SceneParticipantSerializer(personas, many=True).data

    def get_is_owner(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.is_owner(request.user)
        return False


class SceneDetailSerializer(SceneListSerializer):
    """Full scene representation with personas"""

    personas = serializers.SerializerMethodField()

    class Meta(SceneListSerializer.Meta):
        model = Scene
        fields = [
            *SceneListSerializer.Meta.fields,
            "date_finished",
            "is_active",
            "privacy_mode",
            "personas",
        ]
        extra_kwargs = {"name": {"required": False}}

    def get_personas(self, obj: Scene) -> list[dict]:
        personas = (
            Persona.objects.filter(
                interactions_written__scene=obj,
            )
            .distinct()
            .select_related(
                "character_sheet",
                "character_sheet__character__roster_entry",
            )
        )
        return PersonaSerializer(personas, many=True).data

    def get_participants(self, obj):
        return super().get_participants(obj)


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
                roster_entry = getattr(persona.character_sheet.character, "roster_entry", None)  # noqa: GETATTR_LITERAL — OneToOne reverse may not exist
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

            roster_entry = getattr(persona.character_sheet.character, "roster_entry", None)  # noqa: GETATTR_LITERAL — OneToOne reverse may not exist
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
