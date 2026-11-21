"""Serializers for the game clock REST API."""

from datetime import datetime

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from world.game_clock.constants import AgeHandling, JumpDirection, Season, TimePhase
from world.game_clock.models import GameClockHistory
from world.game_clock.services import format_ic_date, format_ic_date_long


@extend_schema_field(OpenApiTypes.STR)
class IcDateDisplayField(serializers.Field):
    """Read-only IC date in the game's calendar, e.g. "Dreaming 14 (1/14/1012)" (#4185).

    Point ``source`` at an IC datetime field. Formatting stays on the backend so
    the month names live in one place and the browser's timezone can't move the day.
    """

    def __init__(self, **kwargs: object) -> None:
        kwargs["read_only"] = True
        super().__init__(**kwargs)

    def to_representation(self, value: datetime) -> str:
        return format_ic_date(value)


class ClockStateSerializer(serializers.Serializer):
    """Read-only serializer for the current clock state."""

    ic_datetime = serializers.DateTimeField()
    year = serializers.IntegerField()
    month = serializers.IntegerField()
    month_name = serializers.CharField(help_text="IC month name, e.g. 'Dreaming'.")
    date_display = serializers.CharField(
        help_text="Full IC date, e.g. 'the 14th of the Month of Dreaming, Year 1012'."
    )
    day = serializers.IntegerField()
    hour = serializers.IntegerField()
    minute = serializers.IntegerField()
    phase = serializers.ChoiceField(choices=TimePhase.choices)
    season = serializers.ChoiceField(choices=Season.choices)
    light_level = serializers.FloatField()
    paused = serializers.BooleanField()
    time_ratio = serializers.FloatField(help_text="IC seconds per real second.")
    month_names = serializers.ListField(
        child=serializers.CharField(),
        help_text="The twelve IC month names in order, for a date picker.",
    )


class ClockConvertSerializer(serializers.Serializer):
    """Request serializer for date conversion — exactly one field required."""

    ic_date = serializers.DateTimeField(required=False)
    real_date = serializers.DateTimeField(required=False)

    def validate(self, attrs: dict) -> dict:
        """Ensure exactly one of ic_date or real_date is provided."""
        has_ic = attrs.get("ic_date") is not None
        has_real = attrs.get("real_date") is not None
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
    age_handling = serializers.ChoiceField(
        choices=AgeHandling.choices,
        help_text=(
            "Whether characters age with the calendar or keep their ages (#5248). A "
            "change to an earlier date must keep them."
        ),
    )


class ClockJumpPreviewRequestSerializer(serializers.Serializer):
    """Query serializer for the preview of a date change."""

    ic_datetime = serializers.DateTimeField()


class ClockJumpPreviewSerializer(serializers.Serializer):
    """What setting the clock to a date would do, before anything is written."""

    current_ic_time = serializers.DateTimeField()
    current_date_display = serializers.CharField(
        help_text="The current IC date in full, for the sentence the dialog shows."
    )
    new_ic_time = serializers.DateTimeField()
    direction = serializers.ChoiceField(choices=JumpDirection.choices)
    year_shift = serializers.IntegerField(
        help_text="Calendar years between the dates: what birth years move by if ages are kept."
    )
    characters_with_birth_year = serializers.IntegerField()
    upcoming_events = serializers.IntegerField()
    heritages_not_yet_appeared = serializers.ListField(child=serializers.CharField())


class ClockHistorySerializer(serializers.ModelSerializer):
    """One recorded change to the clock, for the staff page's Recent changes list."""

    changed_by_name = serializers.CharField(
        source="changed_by.username", read_only=True, default=""
    )
    new_date_display = serializers.SerializerMethodField()

    class Meta:
        model = GameClockHistory
        fields = [
            "id",
            "changed_at",
            "changed_by_name",
            "change",
            "new_anchor_ic_time",
            "new_date_display",
            "old_time_ratio",
            "new_time_ratio",
            "birth_year_shift",
            "reason",
        ]
        read_only_fields = fields

    def get_new_date_display(self, obj: GameClockHistory) -> str:
        return format_ic_date_long(obj.new_anchor_ic_time)


class ClockRatioSerializer(serializers.Serializer):
    """Request serializer for staff time-ratio change."""

    ratio = serializers.FloatField(min_value=0.01)
    reason = serializers.CharField(max_length=500)


class ClockDetailSerializer(serializers.Serializer):
    """Generic ``{"detail": "..."}`` response (staff actions + errors)."""

    detail = serializers.CharField()
