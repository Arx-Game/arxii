"""API views for the achievements system."""

from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from world.achievements.models import Achievement, AchievementReward, CharacterAchievement
from world.achievements.serializers import (
    AchievementListSerializer,
    AchievementSerializer,
    CharacterAchievementSerializer,
)


class AchievementViewSet(ReadOnlyModelViewSet):
    """
    ViewSet for listing and retrieving achievements.

    Returns active achievements that are either visible (not hidden) or
    have been earned by the requesting user's characters.
    """

    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ["name", "description"]

    def get_queryset(self):  # type: ignore[override]
        """Return active achievements visible to the requesting user."""
        qs = Achievement.objects.filter(is_active=True)
        earned_ids = CharacterAchievement.objects.filter(
            character_sheet__character__roster_entry__tenures__player_data__account=self.request.user,
            character_sheet__character__roster_entry__tenures__end_date__isnull=True,
        ).values_list("achievement_id", flat=True)
        return qs.filter(hidden=False) | qs.filter(id__in=earned_ids)

    def get_serializer_class(self):  # type: ignore[override]
        """Use list serializer for list action, full serializer for detail."""
        if self.action == "list":
            return AchievementListSerializer
        return AchievementSerializer


class CharacterAchievementViewSet(ReadOnlyModelViewSet):
    """
    ViewSet for listing character achievements.

    Returns achievements earned by characters, filterable by character_sheet.
    """

    serializer_class = CharacterAchievementSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["character_sheet"]

    def get_queryset(self):  # type: ignore[override]
        """Return character achievements with related data prefetched."""
        return CharacterAchievement.objects.select_related(
            "achievement", "discovery"
        ).prefetch_related(
            Prefetch(
                "achievement__rewards",
                queryset=AchievementReward.objects.select_related("reward"),
                to_attr="cached_rewards",
            ),
        )
