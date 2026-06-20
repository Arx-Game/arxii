"""ViewSets for the consent API."""

from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.consent.models import (
    SocialConsentCategory,
    SocialConsentCategoryRule,
    SocialConsentPreference,
    SocialConsentWhitelist,
)
from world.consent.permissions import IsTenureOwner
from world.consent.serializers import (
    SocialConsentCategoryRuleSerializer,
    SocialConsentCategorySerializer,
    SocialConsentPreferenceDefaultSerializer,
    SocialConsentPreferenceSerializer,
    SocialConsentWhitelistSerializer,
)
from world.roster.models import RosterTenure


class ConsentPagination(PageNumberPagination):
    """Standard pagination for consent endpoints."""

    page_size = 50


class SocialConsentCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only viewset for social consent categories.

    Categories are authored by staff and shared across all players.
    """

    queryset = SocialConsentCategory.objects.all()
    serializer_class = SocialConsentCategorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields: list[str] = []
    pagination_class = ConsentPagination


class SocialConsentPreferenceViewSet(viewsets.ModelViewSet):
    """ViewSet for per-tenure social consent preferences.

    Each tenure has at most one preference row. Results are scoped to
    the requesting player's own tenures — other players' rows return 404.
    """

    serializer_class = SocialConsentPreferenceSerializer
    permission_classes = [IsTenureOwner]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["tenure"]
    pagination_class = ConsentPagination

    def get_queryset(self) -> QuerySet[SocialConsentPreference]:
        """Scope queryset to the requesting player's tenures."""
        try:
            return SocialConsentPreference.objects.filter(
                tenure__player_data=self.request.user.player_data,
            ).order_by("id")
        except AttributeError:
            return SocialConsentPreference.objects.none()

    @action(detail=False, url_path=r"for-tenure/(?P<tenure_id>[0-9]+)")
    def for_tenure(self, request: Request, tenure_id: str | None = None) -> Response:
        """Return the preference for a specific tenure, or a default if absent.

        The synthesized default is not persisted — the UI uses it to display
        initial state before the player has saved any settings.
        """
        try:
            player_data = request.user.player_data
        except AttributeError:
            return Response(status=status.HTTP_403_FORBIDDEN)

        # Verify the tenure belongs to the requesting player before doing anything.
        if not RosterTenure.objects.filter(id=tenure_id, player_data=player_data).exists():
            return Response(status=status.HTTP_404_NOT_FOUND)

        try:
            preference = SocialConsentPreference.objects.get(
                tenure_id=tenure_id,
                tenure__player_data=player_data,
            )
            serializer = SocialConsentPreferenceSerializer(preference, context={"request": request})
            return Response(serializer.data)
        except SocialConsentPreference.DoesNotExist:
            # Synthesize a default without persisting
            serializer = SocialConsentPreferenceDefaultSerializer(
                {"tenure": int(tenure_id), "allow_social_actions": True}
            )
            return Response(serializer.data)


class SocialConsentCategoryRuleViewSet(viewsets.ModelViewSet):
    """ViewSet for per-category consent rules.

    Rules are owned by the player through their SocialConsentPreference.
    Results are scoped to the requesting player's own tenures.
    """

    serializer_class = SocialConsentCategoryRuleSerializer
    permission_classes = [IsTenureOwner]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["preference", "category"]
    pagination_class = ConsentPagination

    def get_queryset(self) -> QuerySet[SocialConsentCategoryRule]:
        """Scope queryset to rules belonging to the requesting player's tenures."""
        try:
            return SocialConsentCategoryRule.objects.filter(
                preference__tenure__player_data=self.request.user.player_data,
            ).order_by("id")
        except AttributeError:
            return SocialConsentCategoryRule.objects.none()


class SocialConsentWhitelistViewSet(viewsets.ModelViewSet):
    """ViewSet for consent whitelist entries.

    Whitelist entries allow specific tenures to target the owner with social
    actions when the owner's category rule is ALLOWLIST mode.
    Results are scoped to the requesting player's own owner tenures.
    """

    serializer_class = SocialConsentWhitelistSerializer
    permission_classes = [IsTenureOwner]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["owner_tenure", "category"]
    pagination_class = ConsentPagination

    def get_queryset(self) -> QuerySet[SocialConsentWhitelist]:
        """Scope queryset to whitelist entries owned by the requesting player's tenures."""
        try:
            return SocialConsentWhitelist.objects.filter(
                owner_tenure__player_data=self.request.user.player_data,
            ).order_by("id")
        except AttributeError:
            return SocialConsentWhitelist.objects.none()
