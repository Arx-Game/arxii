"""Serializers for worship surfaces (#2355).

``WorshippedBeingRefSerializer`` is the public reference shape (id, name,
tradition name) — safe anywhere; it never exposes pools or avatar links.
"""

from rest_framework import serializers

from world.character_sheets.models import CharacterSheet
from world.clues.models import Clue
from world.stories.models import Episode
from world.worship.models import Miracle, Pledge, Prayer, Vision, WorshippedBeing, WorshipRite
from world.worship.types import InvocationDifficulty


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


class InvocationEaseSerializer(serializers.Serializer):
    """One labelled ease on the invocation check (#4333)."""

    label = serializers.CharField()
    points = serializers.IntegerField()


class InvocationDifficultySerializer(serializers.Serializer):
    """How hard an invocation check is for the acting character, and why (#4333)."""

    base_points = serializers.IntegerField()
    base_band = serializers.CharField()
    base_band_label = serializers.SerializerMethodField()
    eases = InvocationEaseSerializer(many=True)
    points = serializers.IntegerField()
    band = serializers.CharField()
    band_label = serializers.SerializerMethodField()

    def get_base_band_label(self, obj: InvocationDifficulty) -> str:
        from world.scenes.action_constants import DifficultyChoice  # noqa: PLC0415

        return DifficultyChoice(obj.base_band).label

    def get_band_label(self, obj: InvocationDifficulty) -> str:
        from world.scenes.action_constants import DifficultyChoice  # noqa: PLC0415

        return DifficultyChoice(obj.band).label


class InvocationOptionSerializer(serializers.Serializer):
    """One being the acting character could call on (#4333). ``refusal`` is the
    player-facing reason it cannot be invoked now, or ""."""

    being_id = serializers.IntegerField(source="being.pk")
    being_name = serializers.CharField(source="being.name")
    favor = serializers.IntegerField()
    can_invoke = serializers.BooleanField()
    refusal = serializers.CharField()
    uses_left = serializers.IntegerField()
    uses_per_week = serializers.IntegerField()
    difficulty = InvocationDifficultySerializer(allow_null=True)


class InvocationBonusRowSerializer(serializers.Serializer):
    """The bonus one outcome tier gives the next check (#4333)."""

    outcome_name = serializers.CharField()
    success_level = serializers.IntegerField()
    bonus = serializers.IntegerField()


class InvocationOptionsSerializer(serializers.Serializer):
    """The Call on favor picker's data: the beings and the bonus by result."""

    beings = InvocationOptionSerializer(many=True)
    bonuses = InvocationBonusRowSerializer(many=True)


class PledgeSerializer(serializers.ModelSerializer):
    """A pledge type a being offers (#4333 slice 2): the staff-authored text and terms."""

    being_name = serializers.CharField(source="being.name", read_only=True)
    closing_rite_name = serializers.CharField(source="closing_rite.name", read_only=True)

    class Meta:
        model = Pledge
        fields = [
            "id",
            "being",
            "being_name",
            "name",
            "description",
            "favor_target",
            "span_weeks",
            "closing_rite_name",
        ]
        read_only_fields = fields


class EarningRateSerializer(serializers.Serializer):
    base = serializers.IntegerField()
    chosen_bonus = serializers.IntegerField()
    modifiers = serializers.IntegerField()
    total = serializers.IntegerField()


class ServiceTermLineSerializer(serializers.Serializer):
    label = serializers.CharField()
    amount = serializers.CharField()


class ServiceTermsSerializer(serializers.Serializer):
    """What earns favor with one being for the acting character (system-generated)."""

    being_id = serializers.IntegerField(source="being.pk")
    being_name = serializers.CharField(source="being.name")
    rate = EarningRateSerializer()
    lines = ServiceTermLineSerializer(many=True)
    weekly_deed_cap = serializers.IntegerField()


class PledgeCreditLineSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    source = serializers.CharField()
    label = serializers.CharField()
    calculation = serializers.CharField()
    credited = serializers.IntegerField()
    counts_toward_progress = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class PledgeCardSerializer(serializers.Serializer):
    """One character's pledge as its card shows it (#4333 slice 2). Read by the
    character's own player and by staff only."""

    id = serializers.IntegerField(source="details.pk")
    character_sheet = serializers.IntegerField(source="details.character_sheet_id")
    pledge = PledgeSerializer(source="details.pledge")
    state = serializers.CharField()
    progress = serializers.IntegerField()
    target = serializers.IntegerField()
    time_limit = serializers.DateTimeField()
    close_attempts = serializers.IntegerField()
    retry_available = serializers.BooleanField()
    favor = serializers.IntegerField()
    credits = PledgeCreditLineSerializer(many=True)
    terms = ServiceTermsSerializer()


class HolySiteSerializer(serializers.Serializer):
    """A being holy in the room the acting character stands in (#4333 slice 2)."""

    being_id = serializers.IntegerField()
    being_name = serializers.CharField()
    site = serializers.CharField()
