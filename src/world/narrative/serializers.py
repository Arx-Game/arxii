from rest_framework import serializers

from world.narrative.models import NarrativeMessage, NarrativeMessageDelivery


class NarrativeMessageSerializer(serializers.ModelSerializer):
    """Player-facing message representation. Excludes ooc_note."""

    class Meta:
        model = NarrativeMessage
        fields = [
            "id",
            "body",
            "category",
            "sender_account",
            "related_story",
            "related_beat_completion",
            "related_episode_resolution",
            "sent_at",
        ]
        read_only_fields = fields


class NarrativeMessageWithOOCSerializer(NarrativeMessageSerializer):
    """Staff/GM-facing message representation that includes ooc_note."""

    class Meta(NarrativeMessageSerializer.Meta):
        fields = [*NarrativeMessageSerializer.Meta.fields, "ooc_note"]
        read_only_fields = fields


class NarrativeMessageDeliverySerializer(serializers.ModelSerializer):
    message = NarrativeMessageSerializer(read_only=True)

    class Meta:
        model = NarrativeMessageDelivery
        fields = ["id", "message", "delivered_at", "acknowledged_at"]
        read_only_fields = fields
