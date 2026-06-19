"""Shared position serializers for use across combat, scenes, and other apps."""

from rest_framework import serializers


class PositionSummarySerializer(serializers.Serializer):
    """Compact public representation of a Position (id + name)."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)


class PersonaPositionSerializer(serializers.Serializer):
    """A scene persona and the Position it currently occupies (or null)."""

    persona_id = serializers.IntegerField(read_only=True)
    position = PositionSummarySerializer(read_only=True, allow_null=True)


class PositionAdjacencyItemSerializer(serializers.Serializer):
    """Read-only serializer for a single PositionAdjacency entry.

    Exposes the ADJACENT-reach neighbor graph for one position so the
    frontend can pre-filter selectable targets by position before declaring.
    """

    position_id = serializers.IntegerField(read_only=True)
    adjacent_position_ids = serializers.ListField(child=serializers.IntegerField(), read_only=True)
