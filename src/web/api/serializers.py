"""Serializers for the web API."""

from evennia.accounts.models import AccountDB
from rest_framework import serializers


class AccountPlayerSerializer(serializers.ModelSerializer):
    """Serialize account and player display information."""

    display_name = serializers.CharField(source="player_data.display_name")

    class Meta:
        model = AccountDB
        fields = ["id", "username", "display_name", "last_login"]
