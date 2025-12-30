"""Serializers for the web API."""

from allauth.account.models import EmailAddress
from evennia.accounts.models import AccountDB
from rest_framework import serializers


class AccountPlayerSerializer(serializers.ModelSerializer):
    """Serialize account and player display information."""

    display_name = serializers.CharField(
        source="player_data.display_name",
        read_only=True,
    )
    email_verified = serializers.SerializerMethodField()
    can_create_characters = serializers.SerializerMethodField()
    is_staff = serializers.BooleanField(read_only=True)
    avatar_url = serializers.SerializerMethodField()

    def get_email_verified(self, obj):
        """Check if user's primary email is verified."""
        try:
            email_address = EmailAddress.objects.get(user=obj, primary=True)
            return email_address.verified
        except EmailAddress.DoesNotExist:
            return False

    def get_can_create_characters(self, obj):
        """Check if user can create new characters."""
        return obj.player_data.can_apply_for_characters()

    def get_avatar_url(self, obj):
        """Get player's avatar URL if available."""
        return obj.player_data.avatar_url

    class Meta:
        model = AccountDB
        fields = [
            "id",
            "username",
            "display_name",
            "last_login",
            "email",
            "email_verified",
            "can_create_characters",
            "is_staff",
            "avatar_url",
        ]
