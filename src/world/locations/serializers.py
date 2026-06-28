"""Serializers for the locations REST API (#1522).

Currently just the per-character comfort read — "how uncomfortable am I, and why" — the web
face of the ``comfort`` command, mirroring ``character_comfort.character_comfort_summary``.
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
