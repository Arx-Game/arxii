"""Public read-only page-background endpoint (#2408)."""

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from evennia_extensions.models import PageBackground
from web.api.serializers import PageBackgroundSerializer


class PageBackgroundListAPIView(APIView):
    """Return every configured page background (slot -> art URL)."""

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        backgrounds = PageBackground.objects.select_related("art").all()
        data = PageBackgroundSerializer(backgrounds, many=True).data
        return Response(data)
