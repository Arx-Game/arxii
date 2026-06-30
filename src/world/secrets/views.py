"""Secret-tab API (#1334) — the active character's known secrets about a character.

Read-only: returns the ``SecretKnowledge`` the **active viewing character** holds (newest first),
filterable by ``subject`` (a CharacterSheet pk) for one person's tab. IC knowledge is scoped to
the active character the caller passes (``viewer`` = a RosterEntry pk), **never** the account —
``for_account`` confines it to the caller's own characters so the param can't reach another
account's knowledge. Locked partial-knowledge layers render as "Unknown" in the serializer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db.models import BooleanField, Exists, ExpressionWrapper, OuterRef
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from world.relationships.models import GrievanceOption, RelationshipTrack
from world.roster.models import RosterEntry
from world.secrets.constants import GossipAction
from world.secrets.filters import KnownSecretFilter
from world.secrets.models import Secret, SecretKnowledge
from world.secrets.serializers import (
    GossipActionSerializer,
    GossipResultSerializer,
    GossipSecretSerializer,
    GrievanceOptionSerializer,
    KnownSecretSerializer,
    SecretGrievanceSerializer,
)
from world.secrets.services import SecretError, known_secrets_for, register_secret_grievance

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from rest_framework.request import Request


class SecretsPagination(PageNumberPagination):
    page_size = 50


class KnownSecretViewSet(ReadOnlyModelViewSet):
    """A viewer's known secrets — the data behind the profile secret tab (#1334)."""

    serializer_class = KnownSecretSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = SecretsPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = KnownSecretFilter

    def get_queryset(self) -> QuerySet[SecretKnowledge]:
        viewer = self._viewer_entry()
        if viewer is None:
            return SecretKnowledge.objects.none()
        # Shared with the telnet sheet/secret section (`known_secrets_for`); the `subject` FilterSet
        # narrows to one tab. #1429 — `can_grieve`: the viewer is a wronged party who hasn't yet
        # answered this secret (two Exists subqueries, no N+1), so the "Respond" prompt shows once
        # and disappears after they grieve.
        from world.secrets.models import SecretGrievance, SecretVictim  # noqa: PLC0415

        is_victim = Exists(
            SecretVictim.objects.filter(
                secret=OuterRef("secret"), persona__character_sheet=viewer.character_sheet
            )
        )
        already_grieved = Exists(
            SecretGrievance.objects.filter(
                secret=OuterRef("secret"), victim_sheet=viewer.character_sheet
            )
        )
        return known_secrets_for(viewer).annotate(
            can_grieve=ExpressionWrapper(is_victim & ~already_grieved, output_field=BooleanField())
        )

    def _viewer_entry(self) -> RosterEntry | None:
        """The active (viewing) character, validated as owned by the requester (#1334).

        IC knowledge scopes to the active character, never the account: the caller passes which of
        their characters is viewing (``viewer`` = a RosterEntry pk); ``for_account`` confines the
        lookup to their own, so the param can never reach another account's knowledge. No (or an
        unowned) ``viewer`` → no secrets, rather than an account-wide aggregate.
        """
        raw = self.request.query_params.get("viewer")  # noqa: use_filterset — auth scope, not a filter
        if not raw or not raw.isdigit():
            return None
        return RosterEntry.objects.for_account(self.request.user).filter(pk=int(raw)).first()


class GrievanceOptionListView(ListAPIView):
    """The grievance responses a wronged character may choose from (#1429)."""

    permission_classes = [IsAuthenticated]
    serializer_class = GrievanceOptionSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[GrievanceOption]:
        return GrievanceOption.objects.filter(is_active=True).select_related("track")


class SecretGrievanceView(APIView):
    """A secret's victim registers a grievance against its subject (#1429).

    The web face of the persona-victim prompt; converges on the same
    ``register_secret_grievance`` service the telnet ``+grievance`` command calls. The viewing
    character (``viewer`` = a RosterEntry pk) is validated as owned by the requester, and the
    service enforces that they are an entitled victim who has learned the secret.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        data = SecretGrievanceSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        payload = data.validated_data

        viewer = RosterEntry.objects.for_account(request.user).filter(pk=payload["viewer"]).first()
        if viewer is None:
            return Response(
                {"detail": "No such active character."}, status=status.HTTP_403_FORBIDDEN
            )
        secret = Secret.objects.filter(pk=payload["secret"]).first()
        if secret is None:
            return Response({"detail": "No such secret."}, status=status.HTTP_404_NOT_FOUND)

        option = None
        custom_track = None
        if payload.get("option") is not None:
            option = GrievanceOption.objects.filter(pk=payload["option"], is_active=True).first()
        else:
            custom_track = RelationshipTrack.objects.filter(pk=payload["custom_track"]).first()

        try:
            register_secret_grievance(
                roster_entry=viewer,
                secret=secret,
                option=option,
                custom_points=payload.get("custom_points"),
                custom_track=custom_track,
            )
        except SecretError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_403_FORBIDDEN)
        except ValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class GossipListView(APIView):
    """The Level-1 secrets the viewing character could spread + their heat in this region (#1572).

    The web face of bare ``gossip`` (the telnet list). IC-scoped: ``viewer`` is a RosterEntry pk
    validated by ``for_account``; no/unowned viewer → an empty list. Heat is read for the
    character's current room's region (0 when the character is roomless).
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[OpenApiParameter("viewer", int, description="Viewer's RosterEntry pk.")],
        responses=GossipSecretSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        from world.secrets.gossip import region_heat_for, spreadable_secrets  # noqa: PLC0415

        raw = request.query_params.get("viewer")  # noqa: use_filterset — auth scope, not a filter
        if not raw or not raw.isdigit():
            return Response([])
        viewer = RosterEntry.objects.for_account(request.user).filter(pk=int(raw)).first()
        if viewer is None:
            return Response([])
        character = viewer.character_sheet.character
        room = character.location
        rows = [
            {
                "id": secret.pk,
                "content": secret.content,
                "heat": region_heat_for(secret, room=room) if room is not None else 0,
            }
            for secret in spreadable_secrets(character)
        ]
        return Response(GossipSecretSerializer(rows, many=True).data)


class GossipActionView(APIView):
    """Plant / seek / suppress gossip at a social hub (#1572) — the web face of ``CmdGossip``.

    Converges on the same ``world.secrets.gossip`` services the telnet command calls. ``viewer`` is
    validated by ``for_account``; the services enforce the Gossip-skill + social-hub gates and raise
    ``GossipError`` (surfaced as its ``user_message``, never ``str(exc)``).
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(request=GossipActionSerializer, responses=GossipResultSerializer)
    def post(self, request: Request) -> Response:
        from world.secrets.gossip import (  # noqa: PLC0415
            GossipError,
            plant_gossip,
            seek_gossip,
            suppress_gossip,
        )

        data = GossipActionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        payload = data.validated_data

        viewer = RosterEntry.objects.for_account(request.user).filter(pk=payload["viewer"]).first()
        if viewer is None:
            return Response(
                {"detail": "No such active character."}, status=status.HTTP_403_FORBIDDEN
            )
        character = viewer.character_sheet.character
        room = character.location
        if room is None:
            return Response(
                {"detail": "Your character isn't anywhere to gossip."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        action = payload["action"]
        try:
            if action == GossipAction.SEEK:
                result = seek_gossip(character, room=room)
            else:
                secret = Secret.objects.filter(pk=payload["secret"]).first()
                if secret is None:
                    return Response({"detail": "No such secret."}, status=status.HTTP_404_NOT_FOUND)
                spread = plant_gossip if action == GossipAction.PLANT else suppress_gossip
                result = spread(character, secret, room=room)
        except GossipError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_403_FORBIDDEN)

        content = None
        if result.surfaced_secret_id is not None and action == GossipAction.SEEK and result.success:
            content = (
                Secret.objects.filter(pk=result.surfaced_secret_id)
                .values_list("content", flat=True)
                .first()
            )
        return Response(
            GossipResultSerializer(
                {
                    "success": result.success,
                    "heat": result.heat,
                    "went_public": result.went_public,
                    "content": content,
                }
            ).data
        )
