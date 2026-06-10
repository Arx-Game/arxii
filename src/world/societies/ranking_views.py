"""#761 — player-scoped read API for diegetic ranking displays.

The web-first home of the herald/Academy boards: the React client fetches
the structured ranking for an in-world display object (the same object a
telnet player examines). Gating mirrors ``render_ranking_display`` exactly
— SOCIETY_PRESTIGE boards require the viewer's presented persona to belong
to the scoped society; non-members get the cloaked state (they learn a
board exists, never its names). Raw numbers never leave the server.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from world.societies.models import RankingDisplay
from world.societies.ranking_services import (
    get_academy_legend_top_n,
    get_society_prestige_top_n,
    viewer_is_member_of_society,
)

_MSG_NO_DISPLAY = "No ranking display there."


class RankingRowSerializer(serializers.Serializer):
    """One row: a name and the qualitative phrase the world speaks. No numbers."""

    persona_name = serializers.CharField()
    band_label = serializers.CharField(allow_blank=True)


class RankingBoardSerializer(serializers.Serializer):
    """A rendered board. ``cloaked`` = the viewer may know it exists, not its names."""

    display_id = serializers.IntegerField()
    ranking_type = serializers.CharField()
    title = serializers.CharField()
    cloaked = serializers.BooleanField()
    rows = RankingRowSerializer(many=True)


class RankingDisplayViewSet(viewsets.ViewSet):
    """Retrieve-only player surface for one diegetic ranking display.

    Keyed by the display OBJECT's id (RankingDisplay is OneToOne with the
    in-world object the player is looking at). No list endpoint — boards
    are discovered in the world, not browsed (diegetic-discovery, #676).
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={
            200: RankingBoardSerializer,
            404: OpenApiResponse(description="No ranking display on that object."),
        },
    )
    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        display = RankingDisplay.objects.filter(pk=pk).select_related("scope_society").first()
        if display is None:
            raise NotFound(_MSG_NO_DISPLAY)
        payload = _board_payload(display, _viewer_persona(request))
        return Response(RankingBoardSerializer(payload).data)


def _viewer_persona(request: Request):
    """The viewer's presented persona (PRIMARY convention), or None.

    None viewers see public boards and the cloaked state on gated ones —
    same posture as a telnet examine with no persona context.
    """
    from world.scenes.services import (  # noqa: PLC0415
        MissingPrimaryPersonaError,
        persona_for_character,
    )

    try:
        puppet = request.user.puppet
    except (AttributeError, Exception):  # noqa: BLE001
        return None
    if puppet is None:
        return None
    try:
        return persona_for_character(puppet)
    except MissingPrimaryPersonaError:
        return None


def _board_payload(display: RankingDisplay, viewer_persona) -> dict:
    if display.ranking_type == RankingDisplay.RankingType.ACADEMY_LEGEND:
        rows = get_academy_legend_top_n(n=display.top_n)
        return {
            "display_id": display.pk,
            "ranking_type": display.ranking_type,
            "title": "PLACEHOLDER The Academy's most legendary",
            "cloaked": False,
            "rows": [{"persona_name": r.persona_name, "band_label": r.band_label} for r in rows],
        }
    society = display.scope_society
    if society is None or not viewer_is_member_of_society(viewer_persona, society):
        return {
            "display_id": display.pk,
            "ranking_type": display.ranking_type,
            "title": (
                f"PLACEHOLDER The names of {society.name} are not for your ears"
                if society
                else "PLACEHOLDER An empty board"
            ),
            "cloaked": True,
            "rows": [],
        }
    rows = get_society_prestige_top_n(society, n=display.top_n)
    return {
        "display_id": display.pk,
        "ranking_type": display.ranking_type,
        "title": f"PLACEHOLDER Those {society.name} holds highest",
        "cloaked": False,
        "rows": [{"persona_name": r.persona_name, "band_label": r.band_label} for r in rows],
    }
