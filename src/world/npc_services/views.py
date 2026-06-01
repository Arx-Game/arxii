"""DRF viewsets for the unified NPC service framework.

Staff-only CRUD over NPCRole, NPCServiceOffer, NPCStanding, and per-kind
details models. Player-facing surfaces (the interaction state machine
that consumes these models) live in `world.npc_services.services` and
get their own endpoint set later.
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser, IsAuthenticated

from world.npc_services.filters import (
    NPCRoleFilterSet,
    NPCServiceOfferFilterSet,
    NPCStandingFilterSet,
)
from world.npc_services.models import (
    NPCRole,
    NPCServiceOffer,
    NPCStanding,
    PermitOfferDetails,
)
from world.npc_services.serializers import (
    NPCRoleSerializer,
    NPCServiceOfferSerializer,
    NPCStandingSerializer,
    PermitOfferDetailsSerializer,
)


class NPCServicesPagination(PageNumberPagination):
    """Shared pagination for the NPC services authoring API."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class NPCStandingViewSet(viewsets.ModelViewSet):
    """Staff CRUD for per-(PC persona, NPC persona) standing rows."""

    queryset = NPCStanding.objects.all().order_by("pk")
    serializer_class = NPCStandingSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = NPCServicesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = NPCStandingFilterSet


class NPCRoleViewSet(viewsets.ModelViewSet):
    """Staff CRUD for NPC roles (the kind-of-NPC bundle for offers)."""

    queryset = NPCRole.objects.all().order_by("pk")
    serializer_class = NPCRoleSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = NPCServicesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = NPCRoleFilterSet


class NPCServiceOfferViewSet(viewsets.ModelViewSet):
    """Staff CRUD for offers (gated services on an NPC role)."""

    queryset = NPCServiceOffer.objects.all().order_by("pk")
    serializer_class = NPCServiceOfferSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = NPCServicesPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = NPCServiceOfferFilterSet


class PermitOfferDetailsViewSet(viewsets.ModelViewSet):
    """Staff CRUD for permit offer details (1:1 to an NPCServiceOffer)."""

    queryset = PermitOfferDetails.objects.all().order_by("pk")
    serializer_class = PermitOfferDetailsSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    pagination_class = NPCServicesPagination
