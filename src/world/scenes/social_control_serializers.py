"""Serializers for the Block / Mute player-control API (#1278)."""

from __future__ import annotations

from rest_framework import serializers

from world.scenes.interaction_permissions import get_account_personas
from world.scenes.models import Block, Mute, Persona

_NOT_YOUR_PERSONA = "You can only block as one of your own personas."


class BlockCreateSerializer(serializers.Serializer):
    """Create a block: the player's own face, the target face, and a required reason."""

    blocker_persona = serializers.PrimaryKeyRelatedField(queryset=Persona.objects.all())
    blocked_persona = serializers.PrimaryKeyRelatedField(queryset=Persona.objects.all())
    reason = serializers.CharField(max_length=200, allow_blank=False, trim_whitespace=True)

    def validate_blocker_persona(self, value: Persona) -> Persona:
        if value.pk not in set(get_account_personas(self.context["request"])):
            raise serializers.ValidationError(_NOT_YOUR_PERSONA)
        return value


class BlockSerializer(serializers.ModelSerializer):
    """A block the requesting player owns."""

    blocked_persona_name = serializers.CharField(source="blocked_persona.name", read_only=True)

    class Meta:
        model = Block
        fields = [
            "id",
            "blocker_persona",
            "blocked_persona",
            "blocked_persona_name",
            "account_level",
            "reason",
            "created_at",
            "pending_removal_at",
        ]
        read_only_fields = fields


class MuteCreateSerializer(serializers.Serializer):
    """Create/update a mute with IC/OOC scope."""

    muted_persona = serializers.PrimaryKeyRelatedField(queryset=Persona.objects.all())
    mute_ic = serializers.BooleanField(default=True)
    mute_ooc = serializers.BooleanField(default=True)


class MuteSerializer(serializers.ModelSerializer):
    """A mute the requesting player owns."""

    muted_persona_name = serializers.CharField(source="muted_persona.name", read_only=True)

    class Meta:
        model = Mute
        fields = ["id", "muted_persona", "muted_persona_name", "mute_ic", "mute_ooc", "created_at"]
        read_only_fields = fields
