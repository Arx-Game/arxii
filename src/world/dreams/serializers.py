"""Serializers for the dreams API (response-shape only; no model writes, #3003)."""

from rest_framework import serializers


class DreamCharacterRefSerializer(serializers.Serializer):
    """A character referenced from the dream payload."""

    id = serializers.IntegerField()
    name = serializers.CharField()


class DreamRoomSerializer(serializers.Serializer):
    """The dreamspace room the character currently perceives."""

    id = serializers.IntegerField()
    key = serializers.CharField()
    description = serializers.CharField(allow_blank=True)


class DreamStateSerializer(serializers.Serializer):
    """Everything the dreamspace panel needs for one character (#3003)."""

    is_dreamside = serializers.BooleanField()
    dream_room = DreamRoomSerializer(allow_null=True)
    co_dreamers = DreamCharacterRefSerializer(many=True)
    dreamwalk_host = DreamCharacterRefSerializer(allow_null=True)
    dreamwalk_candidates = DreamCharacterRefSerializer(many=True)
    can_descend = serializers.BooleanField()
    descent_name = serializers.CharField(allow_blank=True)
    can_ascend = serializers.BooleanField()
    wake_blocked = serializers.BooleanField()
