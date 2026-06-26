"""ViewSets for the consent API."""

from typing import Any

from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers, status, viewsets
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


def _get_actor(request: Request) -> Any:
    """Return the currently played character from the authenticated account."""
    puppet = getattr(request.user, "puppet", None)  # noqa: GETATTR_LITERAL
    if puppet is None:
        raise serializers.ValidationError(
            {"detail": "You must be playing a character to manage consent."}
        )
    return puppet


def _dispatch_consent_action(character: Any, registry_key: str, kwargs: dict[str, Any]) -> None:
    """Dispatch a consent REGISTRY action and translate failure into a 400 response.

    Successes return silently; the caller must serialize the resulting state.
    """
    from actions.constants import ActionBackend  # noqa: PLC0415
    from actions.player_interface import dispatch_player_action  # noqa: PLC0415
    from actions.types import ActionRef  # noqa: PLC0415

    ref = ActionRef(backend=ActionBackend.REGISTRY, registry_key=registry_key)
    result = dispatch_player_action(character, ref, kwargs)
    detail = result.detail
    if detail is None or not detail.success:
        message = detail.message if detail is not None else "Action failed."
        raise serializers.ValidationError({"detail": message})


class SocialConsentCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only viewset for social consent categories.

    Categories are authored by staff and shared across all players.
    """

    queryset = SocialConsentCategory.objects.all()
    serializer_class = SocialConsentCategorySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["key"]
    pagination_class = ConsentPagination


class SocialConsentPreferenceViewSet(viewsets.ModelViewSet):
    """ViewSet for per-tenure social consent preferences.

    Each tenure has at most one preference row. Results are scoped to
    the requesting player's own tenures — other players' rows return 404.
    Write endpoints route through the shared REGISTRY action seam.
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

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Create or update a preference via the set_social_consent_preference action."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenure = serializer.validated_data["tenure"]
        actor = _get_actor(request)
        _dispatch_consent_action(
            actor,
            "set_social_consent_preference",
            {
                "tenure_id": tenure.pk,
                "allow_social_actions": serializer.validated_data["allow_social_actions"],
            },
        )
        instance = SocialConsentPreference.objects.get(tenure=tenure)
        output = self.get_serializer(instance)
        return Response(output.data, status=status.HTTP_201_CREATED)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Update a preference via the set_social_consent_preference action."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        actor = _get_actor(request)
        _dispatch_consent_action(
            actor,
            "set_social_consent_preference",
            {
                "tenure_id": instance.tenure_id,
                "allow_social_actions": serializer.validated_data["allow_social_actions"],
            },
        )
        instance.refresh_from_db()
        output = self.get_serializer(instance)
        return Response(output.data)

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
    Write endpoints route through the shared REGISTRY action seam.
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

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Create a category rule via the set_social_consent_category_rule action."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        preference = serializer.validated_data["preference"]
        category = serializer.validated_data["category"]
        actor = _get_actor(request)
        _dispatch_consent_action(
            actor,
            "set_social_consent_category_rule",
            {
                "tenure_id": preference.tenure_id,
                "category_key": category.key,
                "mode": serializer.validated_data["mode"],
            },
        )
        instance = SocialConsentCategoryRule.objects.get(preference=preference, category=category)
        output = self.get_serializer(instance)
        return Response(output.data, status=status.HTTP_201_CREATED)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Update a category rule via the set_social_consent_category_rule action."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        actor = _get_actor(request)
        _dispatch_consent_action(
            actor,
            "set_social_consent_category_rule",
            {
                "tenure_id": instance.preference.tenure_id,
                "category_key": instance.category.key,
                "mode": serializer.validated_data["mode"],
            },
        )
        instance.refresh_from_db()
        output = self.get_serializer(instance)
        return Response(output.data)


class SocialConsentWhitelistViewSet(viewsets.ModelViewSet):
    """ViewSet for consent whitelist entries.

    Whitelist entries allow specific tenures to target the owner with social
    actions when the owner's category rule is ALLOWLIST mode.
    Results are scoped to the requesting player's own owner tenures.
    Write endpoints route through the shared REGISTRY action seam.
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

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Create a whitelist entry via the add_social_consent_whitelist action."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        owner_tenure = serializer.validated_data["owner_tenure"]
        allowed_tenure = serializer.validated_data["allowed_tenure"]
        category = serializer.validated_data["category"]
        actor = _get_actor(request)
        _dispatch_consent_action(
            actor,
            "add_social_consent_whitelist",
            {
                "tenure_id": owner_tenure.pk,
                "allowed_tenure_id": allowed_tenure.pk,
                "category_key": category.key,
            },
        )
        instance = SocialConsentWhitelist.objects.get(
            owner_tenure=owner_tenure,
            allowed_tenure=allowed_tenure,
            category=category,
        )
        output = self.get_serializer(instance)
        return Response(output.data, status=status.HTTP_201_CREATED)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Remove a whitelist entry via the remove_social_consent_whitelist action."""
        instance = self.get_object()
        actor = _get_actor(request)
        _dispatch_consent_action(
            actor,
            "remove_social_consent_whitelist",
            {
                "tenure_id": instance.owner_tenure_id,
                "allowed_tenure_id": instance.allowed_tenure_id,
                "category_key": instance.category.key,
            },
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
