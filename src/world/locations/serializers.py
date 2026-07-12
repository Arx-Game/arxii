"""Serializers for the locations REST API (#1522, #2222).

The per-character comfort read — "how uncomfortable am I, and why" — the web face of the
``comfort`` command, mirroring ``character_comfort.character_comfort_summary``. Also the
portal-destinations discovery read (#2222), mirroring
``world.magic.services.portal_travel.PortalDestination``.
"""

from __future__ import annotations

from rest_framework import serializers

from world.locations.character_comfort import CharacterComfortSummary


class ComfortRequestSerializer(serializers.Serializer):
    """Query-param validation for the comfort read — a required character id.

    ``character_id`` is the character's ObjectDB pk (== CharacterSheet pk by construction).
    """

    character_id = serializers.IntegerField()


class CharacterComfortSerializer(serializers.Serializer):
    """Read-only per-character comfort readout (mirrors ``CharacterComfortSummary``).

    ``felt`` is the per-axis residual exposure (room felt minus the character's mitigation,
    floored), keyed by the lowercased exposure-axis name (``cold``/``heat``/``wet``/…) and
    carrying only the nonzero axes.
    """

    band = serializers.CharField()
    band_index = serializers.IntegerField()
    discomfort = serializers.IntegerField()
    reasons = serializers.ListField(child=serializers.CharField())
    injury = serializers.IntegerField()
    felt = serializers.SerializerMethodField()

    def get_felt(self, obj: CharacterComfortSummary) -> dict[str, int]:
        return {axis.value: value for axis, value in obj.felt.items()}


class PortalDestinationsRequestSerializer(serializers.Serializer):
    """Query-param validation for the portal-destinations read — a required character id.

    Mirrors ``ComfortRequestSerializer``: ``character_id`` is the character's ObjectDB pk
    (== ``CharacterSheet`` pk by construction).
    """

    character_id = serializers.IntegerField()


class PortalDestinationSerializer(serializers.Serializer):
    """One anchor a character could portal-travel to right now (mirrors ``PortalDestination``).

    Explicit fields only — never a raw model/dataclass dump, since a locked anchor's
    visibility is already gated upstream by
    ``world.magic.services.portal_travel.portal_destinations`` (#2222 leak table).
    """

    anchor_id = serializers.IntegerField(source="anchor.pk")
    room_id = serializers.IntegerField(source="room.id")
    room_name = serializers.CharField(source="room.key")
    kind_name = serializers.CharField(source="kind.name")
    anchor_name = serializers.CharField(source="anchor.name")
