"""Serializers for the weather REST API (#1522)."""

from __future__ import annotations

from rest_framework import serializers

from world.weather.types import ConditionsSummary


class ConditionsRequestSerializer(serializers.Serializer):
    """Query-param validation for the conditions read — a required room id."""

    room_id = serializers.IntegerField()


class ConditionsSerializer(serializers.Serializer):
    """Read-only IC time + weather at a location (mirrors ``ConditionsSummary``).

    Every field is nullable — no game clock (time fields) or no weather designated for the
    location (weather fields). The widget renders whatever is present.
    """

    ic_time = serializers.DateTimeField(allow_null=True)
    phase = serializers.SerializerMethodField()
    season = serializers.SerializerMethodField()
    weather_type = serializers.SerializerMethodField()
    emit_text = serializers.CharField(allow_null=True)

    def get_phase(self, obj: ConditionsSummary) -> str | None:
        return obj.phase.value if obj.phase is not None else None

    def get_season(self, obj: ConditionsSummary) -> str | None:
        return obj.season.value if obj.season is not None else None

    def get_weather_type(self, obj: ConditionsSummary) -> str | None:
        return obj.weather_type.name if obj.weather_type is not None else None
