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
    claim_verb = serializers.CharField(source="resonance.affinity.claim_verb")
    unclaimed = serializers.SerializerMethodField()
    waiting_trickle = serializers.SerializerMethodField()

    def get_strength_name(self, obj) -> str | None:
        return obj.tier.name if obj.tier is not None else None

    def get_unclaimed(self, obj) -> int:
        """What a kindled deed set aside for the character in this resonance and they have not
        claimed (#5181). Kindled or not: it waits however long it takes. The view puts the
        character's amounts in ``context["unclaimed"]`` (resonance id to amount)."""
        return self.context.get("unclaimed", {}).get(obj.resonance.pk, 0)

    def get_waiting_trickle(self, obj) -> int:
        """What the character's days have piled up in this resonance for the next anima ritual
        to harvest (#5308). The view puts the amounts in ``context["trickle"]`` (resonance id
        to amount)."""
        return self.context.get("trickle", {}).get(obj.resonance.pk, 0)


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
