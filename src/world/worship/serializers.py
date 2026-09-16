"""Serializers for worship surfaces (#2355).

``WorshippedBeingRefSerializer`` is the public reference shape (id, name,
tradition name) — safe anywhere; it never exposes pools or avatar links.
"""

from rest_framework import serializers

from world.character_sheets.models import CharacterSheet
from world.clues.models import Clue
from world.stories.models import Episode
from world.worship.models import Miracle, Prayer, Vision, WorshippedBeing, WorshipRite


class WorshippedBeingRefSerializer(serializers.ModelSerializer):
    tradition_name = serializers.CharField(source="tradition.name", read_only=True)

    class Meta:
        model = WorshippedBeing
        fields = ["id", "name", "tradition_name"]


class MiracleSerializer(serializers.ModelSerializer):
    """Staff-facing miracle catalog serializer (#2360)."""

    being_name = serializers.CharField(source="being.name", read_only=True)

    class Meta:
        model = Miracle
        fields = [
            "id",
            "name",
            "description",
            "being_name",
            "resonance_pool_cost",
            "intervention_trigger",
            "favor_threshold",
            "narrative_text",
            "is_active",
            "sort_order",
        ]
        read_only_fields = fields


class WorshipRiteSerializer(serializers.ModelSerializer):
    """A being's rite as the client shows it (#3777): flavor plus the tier."""

    being_name = serializers.CharField(source="being.name", read_only=True)
    kind_name = serializers.CharField(source="kind.name", read_only=True)
    tier = serializers.IntegerField(source="kind.tier", read_only=True)
    check_type_name = serializers.CharField(source="check_type.name", read_only=True)
    resonance_name = serializers.CharField(source="resonance.resonance.name", read_only=True)

    class Meta:
        model = WorshipRite
        fields = [
            "id",
            "being",
            "being_name",
            "name",
            "description",
            "kind_name",
            "tier",
            "check_type_name",
            "resonance_name",
        ]
        read_only_fields = fields


class PrayerSerializer(serializers.ModelSerializer):
    """A character's prayer as its owner (or staff) reads it back (#3779)."""

    being_name = serializers.CharField(source="being.name", read_only=True)
    answered = serializers.SerializerMethodField()

    class Meta:
        model = Prayer
        fields = [
            "id",
            "character_sheet",
            "being",
            "being_name",
            "text",
            "devotion_granted",
            "dire_straits",
            "answered",
            "prayed_at",
        ]
        read_only_fields = fields

    def get_answered(self, obj: Prayer) -> bool:
        return obj.intervention_id is not None or obj.visions.exists()


class VisionSerializer(serializers.ModelSerializer):
    """A vision as its recipient reads it (#3779): the being only when revealed or to staff."""

    being_name = serializers.SerializerMethodField()
    clue_slug = serializers.SerializerMethodField()
    episode_title = serializers.SerializerMethodField()

    class Meta:
        model = Vision
        fields = [
            "id",
            "recipient",
            "being_name",
            "body",
            "reveal_source",
            "prayer",
            "clue",
            "clue_slug",
            "episode",
            "episode_title",
            "sent_at",
        ]
        read_only_fields = fields

    def _staff(self) -> bool:
        request = self.context.get("request")
        return bool(request is not None and request.user.is_staff)

    def get_being_name(self, obj: Vision) -> str | None:
        if obj.reveal_source or self._staff():
            return obj.being.name
        return None

    def get_clue_slug(self, obj: Vision) -> str | None:
        return obj.clue.slug if obj.clue_id is not None else None

    def get_episode_title(self, obj: Vision) -> str | None:
        return obj.episode.title if obj.episode_id is not None else None


class VisionCreateSerializer(serializers.Serializer):
    """What a GM supplies to send a vision (#3779); the service does the rest."""

    recipient = serializers.PrimaryKeyRelatedField(queryset=CharacterSheet.objects.all())
    being = serializers.PrimaryKeyRelatedField(
        queryset=WorshippedBeing.objects.filter(is_active=True)
    )
    body = serializers.CharField()
    reveal_source = serializers.BooleanField(default=False)
    prayer = serializers.PrimaryKeyRelatedField(
        queryset=Prayer.objects.all(), required=False, allow_null=True
    )
    clue = serializers.PrimaryKeyRelatedField(
        queryset=Clue.objects.all(), required=False, allow_null=True
    )
    episode = serializers.PrimaryKeyRelatedField(
        queryset=Episode.objects.all(), required=False, allow_null=True
    )
