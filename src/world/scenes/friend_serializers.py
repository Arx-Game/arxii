"""Serializers for the OOC friends-list API (#1727)."""

from __future__ import annotations

from rest_framework import serializers

from world.roster.models import RosterEntry
from world.scenes.models import Friendship

_NOT_YOUR_CHARACTER = "You can only friend as one of your own characters."


class FriendshipCreateSerializer(serializers.Serializer):
    """Add a friend by character (web-friendly): the friending character + the target character.

    ``viewer`` / ``friend`` are ``RosterEntry`` pks; the view resolves each to its current tenure.
    """

    viewer = serializers.PrimaryKeyRelatedField(queryset=RosterEntry.objects.all())
    friend = serializers.PrimaryKeyRelatedField(queryset=RosterEntry.objects.all())
    all_characters = serializers.BooleanField(default=False)

    def validate_viewer(self, value: RosterEntry) -> RosterEntry:
        owned = RosterEntry.objects.for_account(self.context["request"].user).filter(pk=value.pk)
        if not owned.exists():
            raise serializers.ValidationError(_NOT_YOUR_CHARACTER)
        return value


class FriendshipSerializer(serializers.ModelSerializer):
    """A friend row — the friended character's name + which of your characters friended."""

    friend_name = serializers.SerializerMethodField()

    class Meta:
        model = Friendship
        fields = ["id", "friender_tenure", "friend_tenure", "friend_name", "created_at"]
        read_only_fields = fields

    def get_friend_name(self, obj: Friendship) -> str:
        character = obj.friend_tenure.roster_entry.character_sheet.character
        return character.db_key if character is not None else "Unknown"
