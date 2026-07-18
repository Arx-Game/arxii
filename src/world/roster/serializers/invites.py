"""Serializers for game invites (#2483)."""

from __future__ import annotations

from rest_framework import serializers

from world.roster.models import GameInvite


class GameInviteCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a game invite."""

    class Meta:
        model = GameInvite
        fields = ["message"]
        extra_kwargs = {"message": {"required": True}}


class GameInviteSerializer(serializers.ModelSerializer):
    """Serializer for listing/viewing game invites.

    Shows the inviter's display name (not account username) to preserve
    player anonymity. The token is included so the inviter can share the link.
    """

    inviter_display = serializers.CharField(source="inviter.display_name", read_only=True)

    class Meta:
        model = GameInvite
        fields = [
            "id",
            "inviter_display",
            "token",
            "message",
            "status",
            "created_at",
            "claimed_at",
            "expires_at",
        ]
        read_only_fields = [
            "id",
            "inviter_display",
            "token",
            "status",
            "created_at",
            "claimed_at",
            "expires_at",
        ]


class GameInviteResolveSerializer(serializers.Serializer):
    """Serializer for the resolve endpoint (AllowAny, display-safe context only).

    Returns only the inviter's display name and message — never account info.
    """

    inviter_display = serializers.CharField(source="inviter.display_name", read_only=True)
    message = serializers.CharField(read_only=True)
