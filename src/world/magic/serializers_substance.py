"""Serializers for a gift's substance (#5018): cast-card lines and call-up offers."""

from __future__ import annotations

from rest_framework import serializers


class SurroundingsLineSerializer(serializers.Serializer):
    """One line the cast card shows under its cost about where she stands (#5018)."""

    kind = serializers.CharField(
        read_only=True, help_text="power | call_up | blocked | needs (an unmet restriction)."
    )
    text = serializers.CharField(read_only=True)
    amount = serializers.IntegerField(read_only=True, help_text="Signed power, or the penalty.")
    anima = serializers.IntegerField(read_only=True)
    resonance = serializers.IntegerField(read_only=True)
    detail = serializers.CharField(
        read_only=True, help_text="A call-up line's right-hand cost; blank otherwise."
    )


class CallUpOfferSerializer(serializers.Serializer):
    """One gift whose substance she can call up with no technique, priced now (#5018).

    Never a gate: shown and pressable whatever her anima.
    """

    gift_id = serializers.IntegerField(read_only=True)
    label = serializers.CharField(read_only=True, source="plan.label")
    effective_cost = serializers.IntegerField(read_only=True)
    resonance_cost = serializers.IntegerField(read_only=True, source="plan.resonance_cost")
    already_present = serializers.BooleanField(read_only=True, source="plan.already_present")
    can_call_up = serializers.BooleanField(read_only=True, source="plan.calls_up")
    cost_line = serializers.CharField(read_only=True)
    balance_line = serializers.CharField(read_only=True)
