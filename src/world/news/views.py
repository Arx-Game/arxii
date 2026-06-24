"""Public-reaction news feed API (#1450).

Read-only: returns the recent public events (deeds + scandals) the **active viewing character**
would have heard, newest first. IC awareness scopes to the active character, never the account —
the caller passes which of their characters is viewing (``viewer`` = a RosterEntry pk) and
``for_account`` confines the param to the caller's own characters.
"""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.news.serializers import PublicFeedItemSerializer
from world.news.services import public_feed_for
from world.roster.models import RosterEntry
from world.scenes.services import active_persona_for_sheet


class PublicFeedView(APIView):
    """The active character's public news feed — deeds + scandals its societies are aware of."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="viewer",
                type=int,
                required=True,
                description="RosterEntry pk of the active viewing character (the caller's own).",
            )
        ],
        responses=PublicFeedItemSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        # Single required scalar (the active character's pk), not a filterable list — a FilterSet
        # doesn't fit; the feed is a computed dataclass list, not a queryset.
        raw = request.query_params.get("viewer")  # noqa: USE_FILTERSET
        if not raw or not raw.isdigit():
            return Response([])
        viewer = RosterEntry.objects.for_account(request.user).filter(pk=int(raw)).first()
        if viewer is None:
            return Response([])
        persona = active_persona_for_sheet(viewer.character_sheet)
        feed = public_feed_for(persona)
        return Response(PublicFeedItemSerializer(feed, many=True).data)
