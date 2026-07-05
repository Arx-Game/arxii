"""DRF serializers for the action-points read API (#1446)."""

from __future__ import annotations

from rest_framework import serializers


class ActionPointPoolSerializer(serializers.Serializer):
    """The viewer's own AP pool — ``current`` is the spendable "remaining this week"."""

    current = serializers.IntegerField()
    effective_maximum = serializers.IntegerField()
    banked = serializers.IntegerField()
