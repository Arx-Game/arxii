"""Serializer for the Sineating row's options (#5177)."""

from __future__ import annotations

from rest_framework import serializers

from world.magic.constants import SineatingPoseRole


class SineatingOptionSerializer(serializers.Serializer):
    """One plea the character can make or answer, as the composer's picker lists it."""

    role = serializers.ChoiceField(choices=SineatingPoseRole.choices)
    partner_sheet_id = serializers.IntegerField()
    partner_name = serializers.CharField()
    max_units = serializers.IntegerField()
    resonance_name = serializers.CharField()
