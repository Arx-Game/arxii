"""DRF serializers for the currency player API (#1446)."""

from __future__ import annotations

from rest_framework import serializers

from world.currency.models import CharacterPurse


class CharacterPurseSerializer(serializers.ModelSerializer):
    """The viewer's own coin purse — a single coppers balance (the client formats g/s/c)."""

    class Meta:
        model = CharacterPurse
        fields = ["balance"]
