"""NPCAsset API (#1872, #2295).

Read endpoints for the player's own promoted assets, plus the introduce
action for voluntary co-ownership.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from world.assets.filters import NPCAssetFilter
from world.assets.models import NPCAsset
from world.assets.serializers import NPCAssetSerializer

if TYPE_CHECKING:
    from rest_framework.request import Request

    from world.scenes.models import Persona


class NPCAssetPagination(PageNumberPagination):
    page_size = 50


def _active_persona_for_request(request: Request) -> Persona | None:
    """Resolve the request user's ACTIVE persona, or None if unresolvable."""
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    if not request.user.is_authenticated:
        return None
    entry = RosterEntry.objects.for_account(request.user).first()
    if entry is None:
        return None
    return active_persona_for_sheet(entry.character_sheet)


class NPCAssetViewSet(viewsets.ReadOnlyModelViewSet):
    """Read endpoints for the player's own promoted assets + introduce action.

    Also backs the stakes-editor ASSET subject picker (#3561, `?name=`
    search) - see `get_queryset`'s staff/GM widening below. An NPCAsset is
    per-player private content (name, role_context, status, created_at), so
    that widening is scoped narrowly: a non-staff GM only sees assets
    promoted by a character who participates in a story that GM LEADS, never
    every asset in the game (#3561 review fix - the first cut let any
    GMProfile holder, unrelated to the asset's owner, list every player's
    private assets, which was a privacy leak).
    """

    serializer_class = NPCAssetSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = NPCAssetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = NPCAssetFilter

    def get_queryset(self):
        base = NPCAsset.objects.select_related("asset_persona")
        user = self.request.user
        if not user.is_authenticated:
            return NPCAsset.objects.none()
        if user.is_staff:
            return base

        persona = _active_persona_for_request(self.request)
        own_q = Q(promoter_persona=persona) if persona is not None else Q(pk__in=[])

        gm_profile = user.gm_profile_or_none
        if gm_profile is None:
            # Not a GM at all: the original "my own assets" dashboard scope.
            return base.filter(own_q)

        # #3561: a non-staff GM's search scope is every NPCAsset promoted by
        # a persona whose character sheet participates in a story this GM
        # LEADS - Lead GM = Story.primary_table.gm == this GM's profile, the
        # same rule every authoring gate in this PR uses
        # (world.stories.permissions.account_may_route_beat /
        # user_owns_or_leads_story) - union'd with their own assets so a
        # junior GM who leads no story still sees their own assets, not
        # nothing. `.distinct()` guards the join fanning out one row per
        # matching StoryParticipation.
        led_q = Q(
            promoter_persona__character_sheet__story_participations__story__primary_table__gm=(
                gm_profile
            )
        )
        return base.filter(led_q | own_q).distinct()

    @action(detail=True, methods=["post"])
    def extract(self, request: Request, pk: str | None = None) -> Response:
        """Pull your recruited agent out of their public job (#2827 phase 3)."""
        from world.assets.services import ExtractionError, extract_asset  # noqa: PLC0415

        persona = _active_persona_for_request(request)
        asset = NPCAsset.objects.filter(pk=pk).first()
        if persona is None or asset is None:
            return Response({"detail": "No such agent."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            vacated = extract_asset(asset, persona)
        except ExtractionError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        detail = (
            f"{asset.asset_persona} quits their post and answers to you alone."
            if vacated
            else f"{asset.asset_persona} held no public post to leave."
        )
        return Response({"detail": detail, "vacated": vacated})

    @action(detail=True, methods=["post"])
    def donate(self, request: Request, pk: str | None = None) -> Response:
        """Transfer one of your assets to an org you belong to (#2820 phase 2).

        POST /api/assets/{id}/donate/ with org_id. The relationship becomes
        org-held: control follows org leadership thereafter.
        """
        from world.assets.services import OrgTransferError, transfer_asset_to_org  # noqa: PLC0415
        from world.societies.models import Organization, OrganizationMembership  # noqa: PLC0415

        persona = _active_persona_for_request(request)
        asset = NPCAsset.objects.filter(pk=pk).first()
        if persona is None or asset is None or asset.promoter_persona_id != persona.pk:
            return Response(
                {"detail": "That is not one of your assets."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        org = Organization.objects.filter(pk=request.data.get("org_id")).first()
        is_member = (
            org is not None
            and OrganizationMembership.objects.filter(
                organization=org,
                persona=persona,
                left_at__isnull=True,
                exiled_at__isnull=True,
            ).exists()
        )
        if not is_member:
            return Response(
                {"detail": "You can only donate to an organization you belong to."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            transfer_asset_to_org(asset, org)
        except OrgTransferError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": f"{asset.asset_persona} now serves {org.name}."})

    @action(detail=False, methods=["post"])
    def introduce(self, request: Request) -> Response:
        """Introduce an owned asset to a co-present ally (#2295).

        POST /api/assets/introduce/ with asset_id + ally_persona_id.
        """
        from actions.registry import get_action  # noqa: PLC0415

        asset_id = request.data.get("asset_id")
        ally_persona_id = request.data.get("ally_persona_id")
        if asset_id is None or ally_persona_id is None:
            return Response(
                {"detail": "Both asset_id and ally_persona_id are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        puppet = request.user.puppet if hasattr(request.user, "puppet") else None
        if puppet is None:
            return Response(
                {"detail": "No puppeted character."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        action_obj = get_action("introduce_asset")
        result = action_obj.run(
            actor=puppet,
            asset_id=asset_id,
            ally_persona_id=ally_persona_id,
        )
        if not result.success:
            return Response({"detail": result.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": result.message}, status=status.HTTP_200_OK)
