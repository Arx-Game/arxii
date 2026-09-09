"""
Serializers for progression API endpoints.
"""

from rest_framework import serializers

from world.classes.models import Path
from world.classes.serializers import PathListSerializer
from world.journals.models import JournalEntry
from world.progression.constants import NominationTargetType
from world.progression.models import (
    ExperiencePointsData,
    KudosClaimCategory,
    KudosPointsData,
    KudosSourceCategory,
    KudosTransaction,
    Nomination,
    PathIntent,
    RandomSceneTarget,
    XPTransaction,
)
from world.scenes.models import Interaction


class KudosSourceCategorySerializer(serializers.ModelSerializer):
    """Serializer for kudos source categories."""

    class Meta:
        model = KudosSourceCategory
        fields = ["id", "name", "display_name", "description", "default_amount"]


class KudosClaimCategorySerializer(serializers.ModelSerializer):
    """Serializer for kudos claim categories."""

    class Meta:
        model = KudosClaimCategory
        fields = [
            "id",
            "name",
            "display_name",
            "description",
            "kudos_cost",
            "reward_amount",
        ]


class KudosTransactionSerializer(serializers.ModelSerializer):
    """Serializer for kudos transactions."""

    source_category_name = serializers.CharField(
        source="source_category.display_name",
        read_only=True,
        allow_null=True,
    )
    claim_category_name = serializers.CharField(
        source="claim_category.display_name",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = KudosTransaction
        fields = [
            "id",
            "amount",
            "source_category_name",
            "claim_category_name",
            "description",
            "transaction_date",
        ]


class KudosPointsDataSerializer(serializers.ModelSerializer):
    """Serializer for account kudos balance."""

    current_available = serializers.IntegerField(read_only=True)

    class Meta:
        model = KudosPointsData
        fields = ["total_earned", "total_claimed", "current_available"]


class XPTransactionSerializer(serializers.ModelSerializer):
    """Serializer for XP transactions."""

    reason_display = serializers.CharField(
        source="get_reason_display",
        read_only=True,
    )
    character_name = serializers.CharField(
        source="character.key",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = XPTransaction
        fields = [
            "id",
            "amount",
            "reason_display",
            "description",
            "character_name",
            "transaction_date",
        ]


class XPPointsDataSerializer(serializers.ModelSerializer):
    """Serializer for account XP balance."""

    current_available = serializers.IntegerField(read_only=True)

    class Meta:
        model = ExperiencePointsData
        fields = ["total_earned", "total_spent", "current_available"]


class AccountProgressionSerializer(serializers.Serializer):
    """Combined serializer for all account progression data."""

    xp = XPPointsDataSerializer(allow_null=True)
    kudos = KudosPointsDataSerializer(allow_null=True)
    xp_transactions = XPTransactionSerializer(many=True)
    kudos_transactions = KudosTransactionSerializer(many=True)
    claim_categories = KudosClaimCategorySerializer(many=True)


# --- Nomination serializers (#3738) ---


class NominateSerializer(serializers.Serializer):
    """Input serializer for nominating the writer of a piece."""

    target_type = serializers.ChoiceField(choices=NominationTargetType.choices)
    target_id = serializers.IntegerField()


class NominationSerializer(serializers.ModelSerializer):
    """One of the requesting account's own nominations this week.

    The only read anyone gets of a nomination: the nominator's own list, so
    they know whom they have already nominated. A nominee never sees a row.
    """

    nominee_name = serializers.CharField(source="nominee.character.db_key", read_only=True)
    target_name = serializers.SerializerMethodField()

    class Meta:
        model = Nomination
        fields = ["id", "target_type", "target_id", "nominee_name", "target_name", "created_at"]

    def get_target_name(self, obj: Nomination) -> str:
        """A short label for the cited piece."""
        snippet_length = 50
        try:
            return self._resolve_target_name(obj, snippet_length)
        except (Interaction.DoesNotExist, JournalEntry.DoesNotExist):
            return "Deleted content"

    @staticmethod
    def _resolve_target_name(obj: Nomination, snippet_length: int) -> str:
        if obj.target_type == NominationTargetType.INTERACTION:
            interaction = Interaction.objects.get(pk=obj.target_id)
            snippet = interaction.content[:snippet_length]
            if len(interaction.content) > snippet_length:
                return f"{snippet}..."
            return snippet
        if obj.target_type == NominationTargetType.JOURNAL:
            entry = JournalEntry.objects.get(pk=obj.target_id)
            return entry.title or "Untitled journal"
        return "Unknown target"


# --- Random Scene serializers ---


class RandomSceneTargetSerializer(serializers.ModelSerializer):
    """Read serializer for RandomSceneTarget instances."""

    target_persona_name = serializers.CharField(
        source="target_persona.name",
        read_only=True,
    )

    class Meta:
        model = RandomSceneTarget
        fields = [
            "id",
            "target_persona",
            "target_persona_name",
            "slot_number",
            "claimed",
            "claimed_at",
            "first_time",
            "rerolled",
        ]


# --- PathOptions serializer ---


class PathOptionsSerializer(serializers.Serializer):
    """Read serializer for GET /path-options/: current path + selectable children."""

    current_path = PathListSerializer(allow_null=True)
    options = PathListSerializer(many=True)


# --- PathIntent serializers ---


class PathIntentSerializer(serializers.ModelSerializer):
    """Read serializer for PathIntent."""

    intended_path = PathListSerializer(read_only=True)

    class Meta:
        model = PathIntent
        fields = ["id", "intended_path", "declared_at"]


class PathIntentDeclareSerializer(serializers.Serializer):
    """Input serializer for PUT /path-intent/."""

    path_id = serializers.IntegerField()

    def validate(self, attrs: dict) -> dict:
        """Resolve ``path_id`` and return the Path in ``validated_data["path"]``.

        The resolved row rides DRF's own channel rather than being stashed on the
        serializer for the view to read back off ``self`` (ADR-0260), which also
        retires the "Call is_valid() first" guard: validated_data cannot be read
        before validation runs.
        """
        try:
            path = Path.objects.get(pk=attrs["path_id"], is_active=True)
        except Path.DoesNotExist as exc:
            msg = "Path does not exist or is not active."
            raise serializers.ValidationError({"path_id": msg}) from exc
        return attrs | {"path": path}


# --- SelectPath (late-selection recovery) serializers (#2121) --------------


class InitialPathOptionsSerializer(serializers.Serializer):
    """Read serializer for GET /select-path/: current path (usually null) + PROSPECT options."""

    current_path = PathListSerializer(allow_null=True)
    options = PathListSerializer(many=True)


class SelectPathSerializer(serializers.Serializer):
    """Input serializer for POST /select-path/.

    Only the 5 CG-selectable PROSPECT paths are valid — this recovery surface
    mirrors the initial CG choice, not a jump to an advanced stage.
    """

    path_id = serializers.IntegerField()

    def validate(self, attrs: dict) -> dict:
        """Resolve ``path_id`` and return the Path in ``validated_data["path"]``.

        Same contract as PathIntentDeclareSerializer above: the row travels in
        validated_data, never on the serializer instance (ADR-0260).
        """
        from world.classes.models import PathStage  # noqa: PLC0415

        try:
            path = Path.objects.get(pk=attrs["path_id"], is_active=True, stage=PathStage.PROSPECT)
        except Path.DoesNotExist as exc:
            msg = "Path does not exist, is not active, or is not a starting (Prospect) path."
            raise serializers.ValidationError({"path_id": msg}) from exc
        return attrs | {"path": path}
