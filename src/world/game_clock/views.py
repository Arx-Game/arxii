"""API views for the game clock system."""

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.game_clock.models import GameClock
from world.game_clock.serializers import (
    ClockAdjustSerializer,
    ClockConvertResponseSerializer,
    ClockConvertSerializer,
    ClockRatioSerializer,
    ClockStateSerializer,
)
from world.game_clock.services import (
    get_ic_date_for_real_time,
    get_ic_phase,
    get_ic_season,
    get_light_level,
    get_real_time_for_ic_date,
    pause_clock,
    set_clock,
    set_time_ratio,
    unpause_clock,
)
from world.game_clock.types import ClockError


class ClockViewSet(viewsets.ViewSet):
    """ViewSet for game clock queries and staff management."""

    permission_classes = [IsAuthenticated]
    _staff_actions = frozenset({"adjust", "ratio", "pause", "unpause"})

    def get_permissions(self) -> list[object]:
        """Staff actions require IsAdminUser; everything else requires IsAuthenticated."""
        if self.action in self._staff_actions:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def list(self, request: Request) -> Response:
        """GET / — return the current clock state."""
        clock = GameClock.get_active()
        if clock is None:
            return Response(
                {"detail": ClockError.NOT_CONFIGURED},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        real_now = timezone.now()
        ic_now = clock.get_ic_now(real_now=real_now)
        phase = get_ic_phase(real_now=real_now)
        season = get_ic_season(real_now=real_now)
        light_level = get_light_level(real_now=real_now)

        data = {
            "ic_datetime": ic_now,
            "year": ic_now.year,
            "month": ic_now.month,
            "day": ic_now.day,
            "hour": ic_now.hour,
            "minute": ic_now.minute,
            "phase": phase,
            "season": season,
            "light_level": light_level,
            "paused": clock.paused,
        }
        serializer = ClockStateSerializer(data)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def convert(self, request: Request) -> Response:
        """GET /convert/ — convert between IC and real dates."""
        serializer = ClockConvertSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        ic_date = serializer.validated_data.get("ic_date")
        real_date = serializer.validated_data.get("real_date")

        if real_date is not None:
            result_ic = get_ic_date_for_real_time(real_date)
            if result_ic is None:
                return Response(
                    {"detail": ClockError.NOT_CONFIGURED},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            response_data = {"ic_date": result_ic}
        else:
            result_real = get_real_time_for_ic_date(ic_date)
            if result_real is None:
                # Distinguish "no clock" from "clock paused/zero ratio"
                clock = GameClock.get_active()
                if clock is None:
                    return Response(
                        {"detail": ClockError.NOT_CONFIGURED},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
                return Response(
                    {"detail": ClockError.CONVERSION_UNAVAILABLE},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            response_data = {"real_date": result_real}

        response_serializer = ClockConvertResponseSerializer(response_data)
        return Response(response_serializer.data)

    @action(detail=False, methods=["post"])
    def adjust(self, request: Request) -> Response:
        """POST /adjust/ — staff: set the IC clock time."""
        serializer = ClockAdjustSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            set_clock(
                new_ic_time=serializer.validated_data["ic_datetime"],
                changed_by=request.user,
                reason=serializer.validated_data["reason"],
            )
        except ClockError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"detail": "Clock adjusted."})

    @action(detail=False, methods=["post"])
    def ratio(self, request: Request) -> Response:
        """POST /ratio/ — staff: change the time ratio."""
        serializer = ClockRatioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            set_time_ratio(
                ratio=serializer.validated_data["ratio"],
                changed_by=request.user,
                reason=serializer.validated_data["reason"],
            )
        except ClockError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"detail": "Time ratio updated."})

    @action(detail=False, methods=["post"])
    def pause(self, request: Request) -> Response:
        """POST /pause/ — staff: pause the clock."""
        try:
            pause_clock(changed_by=request.user, reason="Paused via API")
        except ClockError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"detail": "Clock paused."})

    @action(detail=False, methods=["post"])
    def unpause(self, request: Request) -> Response:
        """POST /unpause/ — staff: unpause the clock."""
        try:
            unpause_clock(changed_by=request.user, reason="Unpaused via API")
        except ClockError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"detail": "Clock unpaused."})
