from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from world.forms.models import Build, CharacterForm, FormTrait, HeightBand
from world.forms.serializers import (
    ApparentFormSerializer,
    BuildSerializer,
    CharacterFormSerializer,
    FormTraitSerializer,
    HeightBandSerializer,
)
from world.forms.services import get_apparent_form, get_cg_builds, get_cg_height_bands


class FormTraitViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for browsing form trait definitions."""

    queryset = FormTrait.objects.all()
    serializer_class = FormTraitSerializer
    permission_classes = [IsAuthenticated]


class CharacterFormViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing a character's forms."""

    serializer_class = CharacterFormSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter to forms belonging to the user's characters."""
        if not self.request.user.is_authenticated:
            return CharacterForm.objects.none()
        # Get characters owned by this account
        return (
            CharacterForm.objects.filter(character__db_account=self.request.user)
            .select_related("character")
            .prefetch_related("values__trait", "values__option")
        )

    @action(detail=False, methods=["get"])
    def apparent(self, request):
        """Get the apparent form for the user's active character."""
        character = request.user.puppet if hasattr(request.user, "puppet") else None
        if not character:
            return Response({"detail": "No active character"}, status=400)

        apparent = get_apparent_form(character)
        serializer = ApparentFormSerializer(apparent)
        return Response(serializer.data)


class HeightBandViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for browsing height bands."""

    serializer_class = HeightBandSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return CG-selectable bands by default, all for staff."""
        if self.request.user.is_staff:
            return HeightBand.objects.all()
        return get_cg_height_bands()


class BuildViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for browsing builds."""

    serializer_class = BuildSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return CG-selectable builds by default, all for staff."""
        if self.request.user.is_staff:
            return Build.objects.all()
        return get_cg_builds()
