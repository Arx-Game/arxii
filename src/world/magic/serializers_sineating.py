"""Serializer for the Sineating row's options (#5177)."""

from __future__ import annotations

from rest_framework import serializers

from world.character_sheets.models import CharacterSheet
from world.magic.constants import SineatingPoseRole

_ERR_SHEET_NOT_PLAYED = "character_sheet_id does not belong to the requesting account."
_ERR_SHEET_NOT_FOUND = "CharacterSheet not found."


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


class SineatingDeclineSerializer(serializers.Serializer):
    """A Sineater turns down the plea a Sinner has waiting for them (#5177)."""

    actor_sheet_id = serializers.IntegerField()
    sinner_sheet_id = serializers.IntegerField()

    def validate_actor_sheet_id(self, value: int) -> CharacterSheet:
        """The Sineater is a character the requester plays, an NPC a GM runs included."""
        request = self.context["request"]
        sheet = CharacterSheet.objects.filter(pk=value).first()
        if sheet is None:
            raise serializers.ValidationError(_ERR_SHEET_NOT_FOUND)
        played = {entry.character_sheet_id for entry in request.user.cached_roster_entries}
        if not request.user.is_staff and sheet.pk not in played:
            raise serializers.ValidationError(_ERR_SHEET_NOT_PLAYED)
        return sheet

    def decline(self) -> str:
        """Run ``DeclineSineatingAction``; its refusal is a 400 with the action's own words."""
        from actions.definitions.sineating import DeclineSineatingAction  # noqa: PLC0415

        sheet = self.validated_data["actor_sheet_id"]
        result = DeclineSineatingAction().run(
            actor=sheet.character, partner_sheet_id=self.validated_data["sinner_sheet_id"]
        )
        if not result.success:
            raise serializers.ValidationError({"detail": result.message})
        return result.message
