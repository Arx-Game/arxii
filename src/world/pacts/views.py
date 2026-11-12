"""API views for being pacts (#4341): the pact card."""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from world.pacts.serializers import PactCardSerializer
from world.pacts.services import carded_pacts, pact_card
from world.roster.models import RosterEntry
from world.stories.pagination import StandardResultsSetPagination


class PactCardViewSet(ReadOnlyModelViewSet):
    """Characters' pacts with beings as their cards show them, newest first: active pacts
    and ended pacts still easing out. The owner reads their own characters', staff read
    anyone's; a pact with a secret faith is never shown to anyone else."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["character_sheet"]
    serializer_class = PactCardSerializer

    def get_queryset(self):
        qs = carded_pacts()
        if self.request.user.is_staff:
            return qs
        own = RosterEntry.objects.for_account(self.request.user).values_list(
            "character_sheet_id", flat=True
        )
        return qs.filter(character_sheet_id__in=list(own))

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            return self.get_paginated_response(
                PactCardSerializer([pact_card(pact) for pact in page], many=True).data
            )
        return Response(PactCardSerializer([pact_card(p) for p in queryset], many=True).data)

    def retrieve(self, request, *args, **kwargs):
        return Response(PactCardSerializer(pact_card(self.get_object())).data)
