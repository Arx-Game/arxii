from django.core.exceptions import ObjectDoesNotExist
from evennia.accounts.models import AccountDB
from rest_framework import serializers

from world.scenes.models import Persona, Scene, SceneMessage


class PersonaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Persona
        fields = [
            "id",
            "scene",
            "account",
            "name",
            "description",
            "thumbnail_url",
            "character",
        ]


class SceneMessageSerializer(serializers.ModelSerializer):
    persona = PersonaSerializer(read_only=True)
    persona_id = serializers.IntegerField(write_only=True)
    receivers = PersonaSerializer(many=True, read_only=True)
    supplemental_data = serializers.JSONField(
        source="supplemental_data.data", read_only=True, allow_null=True
    )

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
        ]
        read_only_fields = ["sequence_number", "timestamp"]

    def create(self, validated_data):
        persona_id = validated_data.pop("persona_id", None)
        if persona_id:
            persona = Persona.objects.select_related("scene").get(id=persona_id)
            validated_data["persona"] = persona
            validated_data["scene"] = persona.scene
        return super().create(validated_data)


class SceneParticipantSerializer(serializers.ModelSerializer):
    """
    Simplified participant representation for scene lists
    """

    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = AccountDB
        fields = ["id", "username", "avatar_url"]

    def get_avatar_url(self, obj):
        try:
            return obj.player_data.avatar_url
        except ObjectDoesNotExist:
            return None


class SceneListSerializer(serializers.ModelSerializer):
    """
    Simplified scene representation for lists (like spotlight)
    """

    participants = SceneParticipantSerializer(many=True, read_only=True)

    class Meta:
        model = Scene
        fields = ["id", "name", "participants"]


class SceneDetailSerializer(serializers.ModelSerializer):
    """
    Full scene representation with messages and personas
    """

    messages = SceneMessageSerializer(many=True, read_only=True)
    personas = PersonaSerializer(many=True, read_only=True)
    participants = SceneParticipantSerializer(many=True, read_only=True)

    class Meta:
        model = Scene
        fields = [
            "id",
            "name",
            "description",
            "location",
            "date_started",
            "date_finished",
            "is_active",
            "is_public",
            "participants",
            "personas",
            "messages",
        ]


class ScenesSpotlightSerializer(serializers.Serializer):
    """
    Serializer for the spotlight endpoint that matches frontend expectations
    """

    in_progress = SceneListSerializer(many=True, source="active_scenes")
    recent = SceneListSerializer(many=True, source="recent_scenes")
