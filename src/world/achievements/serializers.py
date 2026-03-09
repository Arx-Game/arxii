"""DRF serializers for achievements system."""

from rest_framework import serializers

from world.achievements.models import (
    Achievement,
    AchievementReward,
    CharacterAchievement,
    Discovery,
    StatTracker,
)


class AchievementRewardSerializer(serializers.ModelSerializer):
    """Serializer for achievement rewards."""

    reward_type = serializers.CharField(source="reward.reward_type", read_only=True)
    reward_key = serializers.CharField(source="reward.key", read_only=True)
    reward_name = serializers.CharField(source="reward.name", read_only=True)

    class Meta:
        model = AchievementReward
        fields = ["id", "reward_type", "reward_key", "reward_name", "reward_value"]
        read_only_fields = fields


class DiscoverySerializer(serializers.ModelSerializer):
    """Serializer for discovery records."""

    discoverer_names = serializers.SerializerMethodField()

    class Meta:
        model = Discovery
        fields = ["discovered_at", "discoverer_names"]
        read_only_fields = fields

    def get_discoverer_names(self, obj: Discovery) -> list[str]:
        """Return display names of characters who discovered this achievement."""
        return list(
            obj.discoverers.select_related(
                "character_sheet", "character_sheet__character"
            ).values_list("character_sheet__character__db_key", flat=True)
        )


class AchievementSerializer(serializers.ModelSerializer):
    """Full serializer for achievement detail view."""

    rewards = AchievementRewardSerializer(many=True, read_only=True)
    discovery = DiscoverySerializer(read_only=True, allow_null=True)

    class Meta:
        model = Achievement
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "icon",
            "notification_level",
            "discovery",
            "rewards",
        ]
        read_only_fields = fields


class AchievementListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for achievement list view."""

    class Meta:
        model = Achievement
        fields = ["id", "name", "slug", "icon", "notification_level"]
        read_only_fields = fields


class CharacterAchievementSerializer(serializers.ModelSerializer):
    """Serializer for character achievement records."""

    achievement = AchievementSerializer(read_only=True)
    is_discoverer = serializers.SerializerMethodField()

    class Meta:
        model = CharacterAchievement
        fields = ["id", "achievement", "earned_at", "is_discoverer"]
        read_only_fields = fields

    def get_is_discoverer(self, obj: CharacterAchievement) -> bool:
        """Return True if the character was a discoverer of this achievement."""
        return obj.discovery_id is not None


class StatTrackerSerializer(serializers.ModelSerializer):
    """Serializer for stat tracker records."""

    stat_key = serializers.CharField(source="stat.key", read_only=True)
    stat_name = serializers.CharField(source="stat.name", read_only=True)

    class Meta:
        model = StatTracker
        fields = ["stat_key", "stat_name", "value", "updated_at"]
        read_only_fields = fields
