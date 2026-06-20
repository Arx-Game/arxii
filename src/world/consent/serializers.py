"""Serializers for the consent API."""

from rest_framework import serializers

from world.consent.models import (
    SocialConsentCategory,
    SocialConsentCategoryRule,
    SocialConsentPreference,
    SocialConsentWhitelist,
)


class SocialConsentCategorySerializer(serializers.ModelSerializer):
    """Read-only serializer for social consent categories."""

    action_templates = serializers.SerializerMethodField()

    class Meta:
        model = SocialConsentCategory
        fields = ("id", "key", "name", "description", "display_order", "action_templates")
        read_only_fields = ("id", "key", "name", "description", "display_order", "action_templates")

    def get_action_templates(self, obj: SocialConsentCategory) -> list[str]:
        """Return the names of action templates tagged with this category."""
        return list(obj.action_templates.values_list("name", flat=True))


class SocialConsentPreferenceSerializer(serializers.ModelSerializer):
    """Serializer for per-tenure social consent preferences."""

    class Meta:
        model = SocialConsentPreference
        fields = ("id", "tenure", "allow_social_actions")
        read_only_fields = ("id",)

    def validate(self, attrs: dict) -> dict:
        """Ensure the referenced tenure belongs to the requesting player.

        On create, ``tenure`` is required and must belong to the requesting player.
        On update (instance already set), the existing tenure is used and not
        re-validated (tenure is effectively immutable after creation).
        """
        request = self.context.get("request")
        is_create = self.instance is None
        if request is not None and hasattr(request.user, "player_data"):
            tenure = attrs.get("tenure")
            if is_create and tenure is None:
                raise serializers.ValidationError(
                    {"tenure": "tenure is required when creating a preference."}
                )
            if tenure is not None:
                player_data = request.user.player_data
                if tenure.player_data_id != player_data.pk:
                    raise serializers.ValidationError(
                        {"tenure": "You may only manage preferences for your own tenures."}
                    )
        return attrs


class SocialConsentCategoryRuleSerializer(serializers.ModelSerializer):
    """Serializer for per-category consent rules."""

    class Meta:
        model = SocialConsentCategoryRule
        fields = ("id", "preference", "category", "mode")
        read_only_fields = ("id",)

    def validate(self, attrs: dict) -> dict:
        """Ensure the referenced preference belongs to the requesting player."""
        request = self.context.get("request")
        if request is not None and hasattr(request.user, "player_data"):
            preference = attrs.get("preference")
            if preference is not None:
                player_data = request.user.player_data
                if preference.tenure.player_data_id != player_data.pk:
                    raise serializers.ValidationError(
                        {"preference": "You may only manage rules for your own preferences."}
                    )
        return attrs


class SocialConsentWhitelistSerializer(serializers.ModelSerializer):
    """Serializer for consent whitelist entries."""

    allowed_tenure_name = serializers.CharField(
        source="allowed_tenure.display_name", read_only=True
    )

    class Meta:
        model = SocialConsentWhitelist
        fields = (
            "id",
            "owner_tenure",
            "allowed_tenure",
            "allowed_tenure_name",
            "category",
            "added_at",
        )
        read_only_fields = ("id", "allowed_tenure_name", "added_at")

    def validate(self, attrs: dict) -> dict:
        """Ensure the owner_tenure belongs to the requesting player."""
        request = self.context.get("request")
        if request is not None and hasattr(request.user, "player_data"):
            owner_tenure = attrs.get("owner_tenure")
            if owner_tenure is not None:
                player_data = request.user.player_data
                if owner_tenure.player_data_id != player_data.pk:
                    raise serializers.ValidationError(
                        {
                            "owner_tenure": (
                                "You may only manage whitelist entries for your own tenures."
                            )
                        }
                    )
        return attrs


class SocialConsentPreferenceDefaultSerializer(serializers.Serializer):
    """Read-only serializer for the synthesized for-tenure default response."""

    tenure = serializers.IntegerField()
    allow_social_actions = serializers.BooleanField()
