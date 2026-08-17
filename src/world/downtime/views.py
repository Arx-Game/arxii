"""Views for scheduled-downtime announcements (#3194)."""

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from world.downtime.serializers import PlannedDowntimeSerializer
from world.downtime.services import get_next_downtime


class NextDowntimeView(APIView):
    """Public GET — the next planned downtime, or ``{"downtime": null}``.

    Polled by the web client's banner; must stay cheap and anonymous-safe
    (one bounded query plus one small file read).
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request: Request, *args, **kwargs) -> Response:
        downtime = get_next_downtime()
        if downtime is None:
            return Response({"downtime": None})
        return Response({"downtime": PlannedDowntimeSerializer(downtime).data})
