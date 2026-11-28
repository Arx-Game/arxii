"""Serializer for the "Your resonances" panel (#5124).

One row per resonance the character holds: whether a situation kindles it now, the strength
in its staff-given word and the reasons in player words. No numbers leave the server.
"""

from __future__ import annotations

from rest_framework import serializers

from world.magic.models import RecordedAct


class KindledResonanceSerializer(serializers.Serializer):
    """A ``KindledResonance`` as the panel reads it."""

    id = serializers.IntegerField(source="resonance.pk")
    name = serializers.CharField(source="resonance.name")
    affinity_name = serializers.CharField(source="resonance.affinity.name")
    kindled = serializers.BooleanField(source="is_kindled")
    strength_name = serializers.SerializerMethodField()
    reasons = serializers.ListField(child=serializers.CharField())
    waiting_trickle = serializers.SerializerMethodField()

    def get_strength_name(self, obj) -> str | None:
        return obj.tier.name if obj.tier is not None else None

    def get_waiting_trickle(self, obj) -> int:
        """What the character's days have piled up in this resonance for the next anima ritual
        to harvest (#5308). The view puts the amounts in ``context["trickle"]`` (resonance id
        to amount)."""
        return self.context.get("trickle", {}).get(obj.resonance.pk, 0)


class RecordedActSuggestionSerializer(serializers.Serializer):
    """One resonance a situation suggested for an act (#5327): its id, its name and the line the
    player reads beside the act. No strength or amount leaves the server."""

    resonance_id = serializers.IntegerField()
    resonance_name = serializers.CharField(source="resonance.name")
    reason = serializers.CharField()


class RecordedActSerializer(serializers.ModelSerializer):
    """An act a player can point a mark at (#5327): what she did and what situations suggested.

    ``suggestions`` is strongest first. The view prefetches them in that order.
    """

    suggestions = RecordedActSuggestionSerializer(
        many=True, read_only=True, source="cached_suggestions"
    )

    class Meta:
        model = RecordedAct
        fields = ["id", "label", "created_at", "suggestions"]
        read_only_fields = fields


class ImpulseSerializer(serializers.Serializer):
    """An ``Impulse`` as the panel reads it (#5177): the pull of corruption the character
    carries in one resonance. ``label`` is the condition's display name ("Intrusive Thoughts:
    <resonance>" or "Compulsion: <resonance>"); ``text`` is the words staff wrote for it."""

    resonance_id = serializers.IntegerField(source="resonance.pk")
    resonance_name = serializers.CharField(source="resonance.name")
    label = serializers.CharField()
    present = serializers.BooleanField()
    is_compulsion = serializers.BooleanField()
    text = serializers.CharField()
    reasons = serializers.ListField(child=serializers.CharField())
