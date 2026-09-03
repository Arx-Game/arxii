"""Serializers for the clue read surface (#1575).

The held-clue journal: what a character has discovered. Player-visible clue fields only (name +
description); the *target* a clue points at is not leaked here — discovering the clue is the
hook, resolving its target is the separate research/grant layer.
"""

from rest_framework import serializers

from world.clues.models import CharacterClue


class HeldClueSerializer(serializers.ModelSerializer):
    """One clue a character holds — the journal row (#1575)."""

    name = serializers.CharField(source="clue.name", read_only=True)
    description = serializers.CharField(source="clue.description", read_only=True)
    target_kind = serializers.CharField(source="clue.target_kind", read_only=True)

    class Meta:
        model = CharacterClue
        fields = ["id", "name", "description", "target_kind", "found_at"]
        read_only_fields = fields


class ClueSearchResultSerializer(serializers.Serializer):
    """One row of the GM clue search picker (#3566): id, name, and target_kind only.

    No description or target FK: the picker is for choosing which clue a stake reward
    line grants, not for browsing clue content.
    """

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    target_kind = serializers.CharField(read_only=True)
