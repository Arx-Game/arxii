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

    def get_email_verified(self, obj):
        """Check if user's primary email is verified."""
        try:
            email_address = EmailAddress.objects.get(user=obj, primary=True)
            return email_address.verified
        except EmailAddress.DoesNotExist:
            return False

    class Meta:
        model = AccountDB
        fields = [
            "id",
            "username",
            "display_name",
            "last_login",
            "email",
            "email_verified",
        ]
