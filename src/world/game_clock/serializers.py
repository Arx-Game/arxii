"""Serializers for the game clock REST API."""

from rest_framework import serializers

from world.game_clock.constants import Season, TimePhase


class ClockStateSerializer(serializers.Serializer):
    """Read-only serializer for the current clock state."""

    ic_datetime = serializers.DateTimeField()
    year = serializers.IntegerField()
    month = serializers.IntegerField()
    day = serializers.IntegerField()
    hour = serializers.IntegerField()
    minute = serializers.IntegerField()
    phase = serializers.ChoiceField(choices=TimePhase.choices)
    season = serializers.ChoiceField(choices=Season.choices)
    light_level = serializers.FloatField()
    paused = serializers.BooleanField()


class ClockConvertSerializer(serializers.Serializer):
    """Request serializer for date conversion — exactly one field required."""

    ic_date = serializers.DateTimeField(required=False)
    real_date = serializers.DateTimeField(required=False)

    def validate(self, attrs: dict) -> dict:
        """Ensure exactly one of ic_date or real_date is provided."""
        has_ic = "ic_date" in attrs
        has_real = "real_date" in attrs
        if has_ic == has_real:
            msg = "Provide exactly one of 'ic_date' or 'real_date'."
            raise serializers.ValidationError(msg)
        return attrs


class ClockConvertResponseSerializer(serializers.Serializer):
    """Response serializer for date conversion results."""

    ic_date = serializers.DateTimeField(required=False)
    real_date = serializers.DateTimeField(required=False)


class ClockAdjustSerializer(serializers.Serializer):
    """Request serializer for staff clock adjustment."""

    ic_datetime = serializers.DateTimeField()
    reason = serializers.CharField(max_length=500)


class ClockRatioSerializer(serializers.Serializer):
    """Request serializer for staff time-ratio change."""

    ratio = serializers.FloatField(min_value=0.01)
    reason = serializers.CharField(max_length=500)
