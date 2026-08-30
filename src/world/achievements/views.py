"""API views for the achievements system."""

from django.db.models import Prefetch
import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from world.achievements.models import (
    Achievement,
    AchievementReward,
    CharacterAchievement,
    PersonaTitle,
)
from world.achievements.serializers import (
    AchievementListSerializer,
    AchievementSerializer,
    CharacterAchievementSerializer,
    CharacterTitleSerializer,
)
from world.stories.pagination import StandardResultsSetPagination


class AchievementViewSet(ReadOnlyModelViewSet):
    """
    ViewSet for listing and retrieving achievements.

    Returns active achievements that are either visible (not hidden) or
    have been earned by the requesting user's characters.
    """

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ["name", "description"]

    def get_queryset(self):  # type: ignore[override]
        """Return active achievements visible to the requesting user."""
        qs = Achievement.objects.filter(is_active=True)
        earned_ids = CharacterAchievement.objects.filter(
            character_sheet__roster_entry__tenures__player_data__account=self.request.user,
            character_sheet__roster_entry__tenures__end_date__isnull=True,
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
    # Paginated (2026-07 audit): the character_sheet filter is optional, so a
    # bare GET returned every character-achievement row game-wide.
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["character_sheet"]

    def get_queryset(self):  # type: ignore[override]
        """Return character achievements with related data prefetched.

        ``achievement__discovery`` is select_related so ``is_discoverer()`` can read
        ``discovered_by_tenure_id`` for free; the shared-co-discoverer M2M is
        prefetched onto ``Discovery.cached_shared_tenures`` so no row triggers an
        extra query for the shared-credit check (#3055 -- replaces the old
        ``discovery`` FK select_related).
        """
        return CharacterAchievement.objects.select_related(
            "achievement", "achievement__discovery"
        ).prefetch_related(
            Prefetch(
                "achievement__rewards",
                queryset=AchievementReward.objects.select_related("reward"),
                to_attr="cached_rewards",
            ),
            Prefetch(
                "achievement__discovery__shared_with_tenures",
                to_attr="cached_shared_tenures",
            ),
        )


class CharacterTitleFilterSet(django_filters.FilterSet):
    """Filter ``PersonaTitle`` by the owning character (#3466).

    ``character_sheet`` traverses the persona FK rather than naming a direct model
    field, since titles retargeted onto ``Persona``. Kept as a stepping stone for the
    existing route/param names; the persona-scoped read-surface rename (route +
    ``?persona=``) is a separate, later change.
    """

    character_sheet = django_filters.NumberFilter(field_name="persona__character_sheet")

    class Meta:
        model = PersonaTitle
        fields = ["character_sheet"]


class CharacterTitleViewSet(ReadOnlyModelViewSet):
    """List a character's earned, displayable titles (#1522).

    Titles are cosmetic and public — a character shows them off — so any authenticated user can
    read any character's titles. Filter by ``character_sheet`` (== character ObjectDB pk).
    """

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    serializer_class = CharacterTitleSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = CharacterTitleFilterSet

    def get_queryset(self):  # type: ignore[override]
        """Earned titles with the title's reward prefetched, newest first."""
        return PersonaTitle.objects.select_related("reward").order_by("-earned_at")
