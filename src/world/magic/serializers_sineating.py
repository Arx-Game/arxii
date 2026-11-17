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


class MireRowSerializer(serializers.Serializer):
    """One resonance a Sineater carries corruption in for a Sinner."""

    resonance_name = serializers.CharField()
    amount = serializers.IntegerField()
    label = serializers.CharField(
        help_text="The name shown for the Sineater's corruption in this resonance at its stage."
    )


class MireForSinnerSerializer(serializers.Serializer):
    """What the viewing Sineater carries for one Sinner (#5177). Never shown to the Sinner."""

    sinner_sheet_id = serializers.IntegerField()
    sinner_name = serializers.CharField()
    rows = MireRowSerializer(many=True)
    total = serializers.IntegerField()
