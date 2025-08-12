from django.db.models import Count
from rest_framework import serializers

from world.scenes.models import Persona, Scene, SceneMessage, SceneMessageReaction


class PersonaSerializer(serializers.ModelSerializer):
    roster_entry = serializers.SerializerMethodField()

    class Meta:
        model = Persona
        fields = [
            "id",
            "participation",
            "name",
            "is_fake_name",
            "description",
            "thumbnail_url",
            "character",
            "roster_entry",
        ]
        read_only_fields = ["roster_entry"]

    def get_roster_entry(self, obj):
        entry = getattr(obj.character, "roster_entry", None)
        if entry:
            return {"id": entry.id, "name": entry.character.db_key}
        return None

    def create(self, validated_data):
        return super().create(validated_data)


class SceneMessageSerializer(serializers.ModelSerializer):
    persona = PersonaSerializer(read_only=True)
    persona_id = serializers.IntegerField(write_only=True)
    receivers = PersonaSerializer(many=True, read_only=True)
    supplemental_data = serializers.JSONField(
        source="supplemental_data.data", read_only=True, allow_null=True
    )
    reactions = serializers.SerializerMethodField()

    class Meta:
        model = SceneMessage
        fields = [
            "id",
            "persona",
            "persona_id",
            "content",
            "context",
            "mode",
            "receivers",
            "supplemental_data",
            "timestamp",
            "sequence_number",
            "reactions",
        ]
        read_only_fields = ["sequence_number", "timestamp"]

    def get_reactions(self, obj):
        request = self.context.get("request")
        reactions = obj.reactions.values("emoji").annotate(count=Count("id"))
        user_reacted = set()
        if request and request.user.is_authenticated:
            user_reacted = set(
                obj.reactions.filter(account=request.user).values_list(
                    "emoji", flat=True
                )
            )
        return [
            {
                "emoji": r["emoji"],
                "count": r["count"],
                "reacted": r["emoji"] in user_reacted,
            }
            for r in reactions
        ]

    def create(self, validated_data):
        persona_id = validated_data.pop("persona_id", None)
        if persona_id:
            persona = Persona.objects.select_related("participation__scene").get(
                id=persona_id
            )
            validated_data["persona"] = persona
            validated_data["scene"] = persona.participation.scene
        return super().create(validated_data)


class SceneMessageReactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SceneMessageReaction
        fields = ["id", "message", "emoji"]

    def create(self, validated_data):
        validated_data["account"] = self.context["request"].user
        return super().create(validated_data)


class SceneParticipantSerializer(serializers.ModelSerializer):
    """Simplified participant representation for scene lists"""

    roster_entry = serializers.SerializerMethodField()

    class Meta:
        model = Persona
        fields = ["id", "name", "roster_entry"]

    def get_roster_entry(self, obj):
        entry = getattr(obj.character, "roster_entry", None)
        if entry:
            return {"id": entry.id, "name": entry.character.db_key}
        return None


class SceneListSerializer(serializers.ModelSerializer):
    """Simplified scene representation for lists"""

    participants = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()

    class Meta:
        model = Scene
        fields = [
            "id",
            "name",
            "description",
            "date_started",
            "location",
            "participants",
        ]

    def get_location(self, obj):
        if obj.location:
            return {"id": obj.location.id, "name": obj.location.db_key}
        return None

    def get_participants(self, obj):
        personas = Persona.objects.filter(
            participation__scene=obj, is_fake_name=False, participation__is_gm=False
        ).select_related("character__roster_entry")
        return SceneParticipantSerializer(personas, many=True).data


class SceneDetailSerializer(SceneListSerializer):
    """Full scene representation with messages and personas"""

    messages = SceneMessageSerializer(many=True, read_only=True)
    personas = serializers.SerializerMethodField()
    highlight_message = serializers.SerializerMethodField()

    class Meta(SceneListSerializer.Meta):
        model = Scene
        fields = SceneListSerializer.Meta.fields + [
            "date_finished",
            "is_active",
            "is_public",
            "personas",
            "messages",
            "highlight_message",
        ]

    def get_personas(self, obj):
        personas = Persona.objects.filter(participation__scene=obj).select_related(
            "participation", "character__roster_entry"
        )
        return PersonaSerializer(personas, many=True).data

    def get_participants(self, obj):
        return super().get_participants(obj)

    def get_highlight_message(self, obj):
        message = (
            obj.messages.annotate(num_reactions=Count("reactions"))
            .order_by("-num_reactions", "sequence_number")
            .first()
        )
        if message:
            return SceneMessageSerializer(message, context=self.context).data
        return None


class ScenesSpotlightSerializer(serializers.Serializer):
    """
    Serializer for the spotlight endpoint that matches frontend expectations
    """

    in_progress = SceneListSerializer(many=True, source="active_scenes")
    recent = SceneListSerializer(many=True, source="recent_scenes")
