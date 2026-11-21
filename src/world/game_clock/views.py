"""API views for the game clock system."""

from django.db.models import QuerySet
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from web.api.pagination import DefaultPagination
from world.game_clock.constants import IC_MONTH_NAMES, MAX_CLOCK_YEAR, MIN_CLOCK_YEAR
from world.game_clock.filters import ClockHistoryFilter
from world.game_clock.models import GameClock, GameClockHistory
from world.game_clock.serializers import (
    ClockAdjustSerializer,
    ClockConvertResponseSerializer,
    ClockConvertSerializer,
    ClockDetailSerializer,
    ClockHistorySerializer,
    ClockJumpPreviewRequestSerializer,
    ClockJumpPreviewSerializer,
    ClockRatioSerializer,
    ClockStateSerializer,
)
from world.game_clock.services import (
    format_ic_date_long,
    get_ic_date_for_real_time,
    get_real_time_for_ic_date,
    ic_month_name,
    light_level_from_ic_time,
    pause_clock,
    phase_from_ic_time,
    preview_clock_jump,
    season_from_ic_time,
    set_clock,
    set_time_ratio,
    unpause_clock,
)
from world.game_clock.types import ClockError


@extend_schema(tags=["game-clock"])
class ClockViewSet(viewsets.ViewSet):
    """ViewSet for game clock queries and staff management."""

    # Schema default read shape — drf-spectacular uses this for
    # introspection on viewsets.ViewSet; per-action decorators override.
    serializer_class = ClockStateSerializer
    permission_classes = [IsAuthenticated]
    # Must stay in sync with the @action methods that require IsAdminUser below.
    _staff_actions = frozenset({"adjust", "adjust_preview", "ratio", "pause", "unpause"})

    def get_permissions(self) -> list[object]:
        """Staff actions require IsAdminUser; everything else requires IsAuthenticated."""
        if self.action in self._staff_actions:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    @extend_schema(responses=ClockStateSerializer)
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
        phase = phase_from_ic_time(ic_now)
        season = season_from_ic_time(ic_now)
        light_level = light_level_from_ic_time(ic_now)

        data = {
            "ic_datetime": ic_now,
            "year": ic_now.year,
            "month": ic_now.month,
            "month_name": ic_month_name(ic_now.month),
            "date_display": format_ic_date_long(ic_now),
            "day": ic_now.day,
            "hour": ic_now.hour,
            "minute": ic_now.minute,
            "phase": phase,
            "season": season,
            "light_level": light_level,
            "paused": clock.paused,
            "time_ratio": clock.time_ratio,
            "month_names": [IC_MONTH_NAMES[month] for month in sorted(IC_MONTH_NAMES)],
            "min_year": MIN_CLOCK_YEAR,
            "max_year": MAX_CLOCK_YEAR,
        }
        serializer = ClockStateSerializer(data)
        return Response(serializer.data)

    @extend_schema(
        parameters=[ClockConvertSerializer],
        responses=ClockConvertResponseSerializer,
    )
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
            try:
                result_real = get_real_time_for_ic_date(ic_date)
            except ClockError as exc:
                return Response(
                    {"detail": exc.user_message},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if result_real is None:
                return Response(
                    {"detail": ClockError.NOT_CONFIGURED},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            response_data = {"real_date": result_real}

        response_serializer = ClockConvertResponseSerializer(response_data)
        return Response(response_serializer.data)

    @extend_schema(request=ClockAdjustSerializer, responses=ClockDetailSerializer)
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
                age_handling=serializer.validated_data["age_handling"],
            )
        except ClockError as exc:
            return Response(
                {"detail": exc.user_message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"detail": "Clock adjusted."})

    @extend_schema(
        parameters=[ClockJumpPreviewRequestSerializer],
        responses=ClockJumpPreviewSerializer,
    )
    @action(detail=False, methods=["get"], url_path="adjust-preview")
    def adjust_preview(self, request: Request) -> Response:
        """GET /adjust-preview/ — staff: what setting this date would do; writes nothing."""
        serializer = ClockJumpPreviewRequestSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        try:
            preview = preview_clock_jump(serializer.validated_data["ic_datetime"])
        except ClockError as exc:
            return Response(
                {"detail": exc.user_message},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        data = {
            "current_ic_time": preview.current_ic_time,
            "current_date_display": format_ic_date_long(preview.current_ic_time),
            "new_ic_time": preview.new_ic_time,
            "direction": preview.direction,
            "year_shift": preview.year_shift,
            "characters_with_birth_year": preview.characters_with_birth_year,
            "upcoming_events": preview.upcoming_events,
            "heritages_not_yet_appeared": preview.heritages_not_yet_appeared,
        }
        return Response(ClockJumpPreviewSerializer(data).data)

    @extend_schema(request=ClockRatioSerializer, responses=ClockDetailSerializer)
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
                {"detail": exc.user_message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"detail": "Time ratio updated."})

    @extend_schema(request=None, responses=ClockDetailSerializer)
    @action(detail=False, methods=["post"])
    def pause(self, request: Request) -> Response:
        """POST /pause/ — staff: pause the clock."""
        try:
            pause_clock(changed_by=request.user)
        except ClockError as exc:
            return Response(
                {"detail": exc.user_message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"detail": "Clock paused."})

    @extend_schema(request=None, responses=ClockDetailSerializer)
    @action(detail=False, methods=["post"])
    def unpause(self, request: Request) -> Response:
        """POST /unpause/ — staff: unpause the clock."""
        try:
            unpause_clock(changed_by=request.user)
        except ClockError as exc:
            return Response(
                {"detail": exc.user_message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"detail": "Clock unpaused."})


@extend_schema(tags=["game-clock"])
class ClockHistoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Staff: the recorded changes to the clock, newest first (#5248)."""

    serializer_class = ClockHistorySerializer
    permission_classes = [IsAdminUser]
    pagination_class = DefaultPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = ClockHistoryFilter

    def get_queryset(self) -> QuerySet[GameClockHistory]:
        return GameClockHistory.objects.select_related("changed_by").order_by("-changed_at", "-pk")
