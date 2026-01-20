"""
Serializers for progression API endpoints.
"""

from rest_framework import serializers

from world.progression.models import (
    ExperiencePointsData,
    KudosClaimCategory,
    KudosPointsData,
    KudosSourceCategory,
    KudosTransaction,
    XPTransaction,
)


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
    awarded_by_name = serializers.CharField(
        source="awarded_by.username",
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
            "awarded_by_name",
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
