from rest_framework import serializers

from world.narrative.constants import GemitReach
from world.narrative.models import Gemit, NarrativeMessage, NarrativeMessageDelivery, UserStoryMute


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


# ---------------------------------------------------------------------------
# Task 7.1: Story-scoped OOC sender input serializer
# ---------------------------------------------------------------------------


class SendStoryOOCInputSerializer(serializers.Serializer):
    """Input for POST /api/stories/{id}/send-ooc/."""

    body = serializers.CharField(
        min_length=1,
        help_text="IC/OOC notice body. Must be at least one character.",
    )
    ooc_note = serializers.CharField(
        required=False,
        default="",
        allow_blank=True,
        help_text="Optional internal OOC note visible only to staff and GMs.",
    )


# ---------------------------------------------------------------------------
# Task 7.2: Gemit serializers
# ---------------------------------------------------------------------------


class GemitSerializer(serializers.ModelSerializer):
    """Full Gemit representation for list and create responses."""

    class Meta:
        model = Gemit
        fields = [
            "id",
            "body",
            "reach",
            "reach_societies",
            "reach_organizations",
            "sender_account",
            "related_era",
            "related_story",
            "sent_at",
        ]
        read_only_fields = ["id", "sender_account", "sent_at"]


class GemitCreateSerializer(serializers.ModelSerializer):
    """Input serializer for staff POST /api/narrative/gemits/ (#1450).

    ``reach`` defaults to game-wide. For SPECIFIED reach, name any combination of targets in
    ``reach_societies`` and/or ``reach_organizations`` (at least one; the two are not exclusive).
    """

    body = serializers.CharField(
        min_length=1,
        trim_whitespace=True,
        help_text="Broadcast text. Must be at least one non-whitespace character.",
    )

    class Meta:
        model = Gemit
        fields = [
            "body",
            "reach",
            "reach_societies",
            "reach_organizations",
            "related_era",
            "related_story",
        ]

    def validate(self, attrs: dict) -> dict:
        reach = attrs.get("reach", GemitReach.GAME_WIDE)
        societies = attrs.get("reach_societies") or []
        organizations = attrs.get("reach_organizations") or []
        if reach == GemitReach.SPECIFIED and not (societies or organizations):
            raise serializers.ValidationError(
                {"reach_societies": "Specify at least one society or organization."}
            )
        if reach == GemitReach.GAME_WIDE and (societies or organizations):
            msg = "A game-wide gemit takes no society or organization targets."
            raise serializers.ValidationError(msg)
        return attrs


# ---------------------------------------------------------------------------
# Task 7.3: UserStoryMute serializers
# ---------------------------------------------------------------------------


class UserStoryMuteSerializer(serializers.ModelSerializer):
    """Full UserStoryMute representation."""

    class Meta:
        model = UserStoryMute
        fields = ["id", "story", "muted_at"]
        read_only_fields = ["id", "muted_at"]


class UserStoryMuteCreateSerializer(serializers.ModelSerializer):
    """Input serializer for POST /api/narrative/story-mutes/."""

    class Meta:
        model = UserStoryMute
        fields = ["story"]

    def validate(self, attrs: dict) -> dict:
        """Reject if this account already has a mute for this story."""
        request = self.context["request"]
        story = attrs["story"]
        if UserStoryMute.objects.filter(account=request.user, story=story).exists():
            msg = "You have already muted this story."
            raise serializers.ValidationError({"story": msg})
        return attrs
