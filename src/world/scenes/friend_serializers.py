"""Serializers for the OOC friends-list API (#1727)."""

from __future__ import annotations

from rest_framework import serializers

from world.roster.models import RosterTenure
from world.scenes.models import Friendship

_NOT_YOUR_CHARACTER = "You can only friend as one of your own characters."


class FriendshipCreateSerializer(serializers.Serializer):
    """Add a friend: which of your characters friends (or all), and the friended tenure."""

    friender_tenure = serializers.PrimaryKeyRelatedField(queryset=RosterTenure.objects.all())
    friend_tenure = serializers.PrimaryKeyRelatedField(queryset=RosterTenure.objects.all())
    all_characters = serializers.BooleanField(default=False)

    def validate_friender_tenure(self, value: RosterTenure) -> RosterTenure:
        if value.player_data.account_id != self.context["request"].user.pk:
            raise serializers.ValidationError(_NOT_YOUR_CHARACTER)
        return value


class FriendshipSerializer(serializers.ModelSerializer):
    """A friend row — the friended character's name + the tenures."""

    friend_name = serializers.SerializerMethodField()

    class Meta:
        model = Friendship
        fields = ["id", "friender_tenure", "friend_tenure", "friend_name", "created_at"]
        read_only_fields = fields

    def get_friend_name(self, obj: Friendship) -> str:
        character = obj.friend_tenure.roster_entry.character_sheet.character
        return character.db_key if character is not None else "Unknown"
