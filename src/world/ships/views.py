"""Ship API views (#1832 Task 10).

Lean read-oriented surface modeled on ``world/magic/views_sanctum.py``:
``ShipViewSet`` lists/retrieves the ships the requesting user's active
persona owns (directly, or via a covenant deed-holder — mirrors
``actions.prerequisites.IsShipOwnerPrerequisite``'s ownership definition).
Writes (commission/upgrade/repair) stay on ``action.run()`` via the existing
``actions/definitions/ships.py`` REGISTRY actions and telnet's ``CmdShip`` —
no web dispatch endpoint exists yet on this ViewSet (a fast-follow once the
frontend needs it).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, IsAuthenticated

from world.ships.filters import ShipDetailsFilterSet
from world.ships.models import ShipDetails, ShipType
from world.ships.serializers import ShipDetailsSerializer, ShipTypeSerializer

if TYPE_CHECKING:
    from rest_framework.request import Request

    from world.scenes.models import Persona


class ShipPagination(PageNumberPagination):
    """Pagination for the "my ships" list — mirrors ``ItemTemplatePagination``."""

    page_size = 50


def _active_persona_for_request(request: Request) -> Persona | None:
    """Resolve the request user's ACTIVE persona, or ``None`` if unresolvable.

    Mirrors ``world.magic.views_sanctum._active_persona_for_request`` — ships
    are persona-scoped for the same alt-separation reason (see
    `feedback_account_fk_wrong_for_ic_items`). Returns ``None`` instead of
    raising when the account has no active roster entry, so an unauthenticated
    or character-less caller simply sees an empty list rather than a 400.
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    if not request.user.is_authenticated:
        return None
    entry = RosterEntry.objects.for_account(request.user).first()
    if entry is None:
        return None
    return active_persona_for_sheet(entry.character_sheet)


def _covenant_owned_ship_ids(persona: Persona) -> list[int]:
    """Ship (== Building == Area) pks a covenant *persona* is a member of holds.

    A ship's Area ownership is transferred to the commissioning covenant's
    ``Organization`` at construction (see
    ``world.ships.services.complete_ship_construction``); ``Building.area``
    is a primary-key OneToOne, so ``ShipDetails.pk == building_id == area_id``.
    Membership lookup intentionally mirrors
    ``world.locations.services._persona_organization_ids`` (no lifecycle
    filter on ``OrganizationMembership`` — presence in the table is current
    membership per that helper's own docstring) to keep ownership semantics
    identical to ``IsShipOwnerPrerequisite``, the write-side gate this
    queryset mirrors.
    """
    from world.locations.constants import HolderType, LocationParentType  # noqa: PLC0415
    from world.locations.models import LocationOwnership  # noqa: PLC0415
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    org_ids = OrganizationMembership.objects.filter(persona=persona).values_list(
        "organization_id", flat=True
    )
    return list(
        LocationOwnership.objects.filter(
            parent_type=LocationParentType.AREA,
            holder_type=HolderType.ORGANIZATION,
            holder_organization_id__in=org_ids,
            ended_at__isnull=True,
        ).values_list("area_id", flat=True)
    )


class ShipPermission(BasePermission):
    """Object-level ownership gate for ``ShipViewSet`` (#1832).

    ``ShipViewSet.get_queryset`` already scopes list/retrieve to owned ships,
    so this is belt-and-suspenders per the "permissions belong in permission
    classes, not inline checks" standard — and the seam any future
    detail-level write action on this ViewSet would need.
    """

    def has_permission(self, request: Request, view: object) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request: Request, view: object, obj: ShipDetails) -> bool:
        persona = _active_persona_for_request(request)
        if persona is None:
            return False
        if obj.building.owner_persona_id == persona.pk:
            return True
        return obj.pk in _covenant_owned_ship_ids(persona)


class ShipViewSet(viewsets.ReadOnlyModelViewSet):
    """Read endpoints for the player's "My Ships" surface."""

    serializer_class = ShipDetailsSerializer
    permission_classes = [IsAuthenticated, ShipPermission]
    pagination_class = ShipPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = ShipDetailsFilterSet

    def get_queryset(self) -> QuerySet[ShipDetails]:
        persona = _active_persona_for_request(self.request)
        if persona is None:
            return ShipDetails.objects.none()
        covenant_owned_ids = _covenant_owned_ship_ids(persona)
        return (
            ShipDetails.objects.select_related("ship_type", "building__owner_persona")
            .filter(Q(building__owner_persona=persona) | Q(pk__in=covenant_owned_ids))
            .distinct()
        )


class ShipTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only catalog of authored ``ShipType`` rows."""

    queryset = ShipType.objects.all()
    serializer_class = ShipTypeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Small lookup table
