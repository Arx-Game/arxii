"""Serializer for the "Your resonances" panel (#5124).

One row per resonance the character holds: whether a situation kindles it now, the strength
in its staff-given word and the reasons in player words. No numbers leave the server.
"""

from __future__ import annotations

from rest_framework import serializers


class KindledResonanceSerializer(serializers.Serializer):
    """A ``KindledResonance`` as the panel reads it."""

    id = serializers.IntegerField(source="resonance.pk")
    name = serializers.CharField(source="resonance.name")
    affinity_name = serializers.CharField(source="resonance.affinity.name")
    kindled = serializers.BooleanField(source="is_kindled")
    strength_name = serializers.SerializerMethodField()
    reasons = serializers.ListField(child=serializers.CharField())

    def get_strength_name(self, obj) -> str | None:
        return obj.tier.name if obj.tier is not None else None
