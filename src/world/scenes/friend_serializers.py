"""Serializers for the OOC friends-list API (#1727) and rivalry declarations (#2170)."""

from __future__ import annotations

from rest_framework import serializers

from world.roster.models import RosterEntry
from world.scenes.models import Friendship, Rivalry

_NOT_YOUR_CHARACTER = "You can only friend as one of your own characters."
_NOT_YOUR_CHARACTER_RIVAL = "You can only declare a rival as one of your own characters."
_SELF_RIVAL = "A character cannot declare themselves a rival."


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


class RivalryCreateSerializer(serializers.Serializer):
    """Declare a rival by character (web-friendly): your declaring character + the target.

    ``viewer`` / ``rival`` are ``RosterEntry`` pks; the view resolves each to its current tenure
    (rivalries are tenure-based, mirroring ``FriendshipCreateSerializer``).
    """

    viewer = serializers.PrimaryKeyRelatedField(queryset=RosterEntry.objects.all())
    rival = serializers.PrimaryKeyRelatedField(queryset=RosterEntry.objects.all())

    def validate_viewer(self, value: RosterEntry) -> RosterEntry:
        owned = RosterEntry.objects.for_account(self.context["request"].user).filter(pk=value.pk)
        if not owned.exists():
            raise serializers.ValidationError(_NOT_YOUR_CHARACTER_RIVAL)
        return value

    def validate(self, attrs: dict) -> dict:
        if attrs["viewer"].pk == attrs["rival"].pk:
            raise serializers.ValidationError(_SELF_RIVAL)
        return attrs


class RivalrySerializer(serializers.ModelSerializer):
    """One of your rival declarations — target name, which character declared, mutual or pending.

    ``is_mutual`` reports the #2170 double-opt-in state: True only once the other side has
    declared you back (the list queryset annotates it; the create path stamps it explicitly).
    ``rivaler_entry`` / ``rival_entry`` expose the RosterEntry pks web clients speak.
    """

    rival_name = serializers.SerializerMethodField()
    rivaler_entry = serializers.IntegerField(
        source="rivaler_tenure.roster_entry_id", read_only=True
    )
    rival_entry = serializers.IntegerField(source="rival_tenure.roster_entry_id", read_only=True)
    is_mutual = serializers.BooleanField(read_only=True)

    class Meta:
        model = Rivalry
        fields = [
            "id",
            "rivaler_tenure",
            "rival_tenure",
            "rivaler_entry",
            "rival_entry",
            "rival_name",
            "is_mutual",
            "created_at",
        ]
        read_only_fields = fields

    def get_rival_name(self, obj: Rivalry) -> str:
        character = obj.rival_tenure.roster_entry.character_sheet.character
        return character.db_key if character is not None else "Unknown"
