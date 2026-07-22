"""
Views for the character sheets API.
"""

from http import HTTPMethod

from django.db.models import QuerySet
from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from world.character_creation.services import (
    clear_origin_slot,
    set_origin_slot,
)
from world.character_sheets.models import CharacterSheet
from world.character_sheets.serializers import (
    CharacterSheetSerializer,
    OriginSlotClearSerializer,
    OriginSlotInputSerializer,
    ProfileTextVersionSerializer,
    _viewer_is_privileged,
    get_character_sheet_queryset,
)
from world.character_sheets.services import can_edit_character_sheet
from world.scenes.block_services import sheet_blocked_for_viewer


class CharacterSheetViewSet(RetrieveModelMixin, GenericViewSet):
    """Read-only detail endpoint for character sheets, keyed by character pk.

    Returns character sheet data for a single character. The response
    includes a `can_edit` flag based on whether the requesting user is
    the original creator or staff.
    """

    pagination_class = None  # 2026-07 audit: opt out of default paginator (ADR-0138)

    serializer_class = CharacterSheetSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = []

    def get_queryset(self) -> QuerySet[CharacterSheet]:
        """Return character sheets with related data."""
        return get_character_sheet_queryset()

    def get_object(self) -> CharacterSheet:
        """Resolve the sheet, but 404 if a block hides it from the viewer (#1278).

        A blocked viewer should find the character "might as well not exist" — a 404, not a
        "you're blocked" banner. Staff bypass blocks.
        """
        sheet = super().get_object()
        user = self.request.user
        if not user.is_staff and sheet_blocked_for_viewer(viewer_account=user, sheet=sheet):
            raise Http404
        return sheet

    def _check_ownership(self, sheet: CharacterSheet) -> None:
        """404 if the requesting user can't edit this sheet.

        Uses 404 (not 403) so a non-owner can't distinguish "not yours" from
        "doesn't exist" — mirrors the block-viewer pattern in ``get_object``.
        """
        roster_entry = sheet.roster_entry
        if roster_entry is None or not can_edit_character_sheet(self.request.user, roster_entry):
            raise Http404

    @action(detail=True, methods=[HTTPMethod.POST], url_path="set-origin-slot")
    def set_origin_slot_action(self, request: Request, pk: int | None = None) -> Response:
        """Set a character's origin-story slot answer (#2478)."""
        sheet = self.get_object()
        self._check_ownership(sheet)
        serializer = OriginSlotInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from world.character_creation.models import OriginTemplateSlot  # noqa: PLC0415

        try:
            slot = OriginTemplateSlot.objects.get(pk=serializer.validated_data["slot_id"])
        except OriginTemplateSlot.DoesNotExist:
            return Response({"detail": "Slot not found."}, status=status.HTTP_404_NOT_FOUND)
        set_origin_slot(sheet, slot, serializer.validated_data["value"])
        return Response(status=status.HTTP_200_OK)

    @action(detail=True, methods=[HTTPMethod.POST], url_path="clear-origin-slot")
    def clear_origin_slot_action(self, request: Request, pk: int | None = None) -> Response:
        """Clear a character's origin-story slot answer (#2478)."""
        sheet = self.get_object()
        self._check_ownership(sheet)
        serializer = OriginSlotClearSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from world.character_creation.models import OriginTemplateSlot  # noqa: PLC0415

        try:
            slot = OriginTemplateSlot.objects.get(pk=serializer.validated_data["slot_id"])
        except OriginTemplateSlot.DoesNotExist:
            return Response({"detail": "Slot not found."}, status=status.HTTP_404_NOT_FOUND)
        clear_origin_slot(sheet, slot)
        return Response(status=status.HTTP_200_OK)

    @extend_schema(responses={200: ProfileTextVersionSerializer(many=True)})
    @action(detail=True, methods=[HTTPMethod.GET], url_path="profile-text-versions")
    def profile_text_versions(self, request: Request, pk: int | None = None) -> Response:
        """The sheet's prose-history timeline (#2631) — all versioned fields at once.

        Owner and staff only (per the #2631 ruling): past versions are the
        character's private history by default, stricter than the current
        text's own visibility. Everyone else gets an empty list,
        indistinguishable from "no history yet". (A player-controlled
        openness tier could relax this later via the SheetVisibility
        machinery — deliberately not built now.)
        """
        from world.gm.models import ProfileTextRequestDetails  # noqa: PLC0415

        sheet = self.get_object()
        if not _viewer_is_privileged(sheet, request.user):
            return Response([])

        versions = list(
            sheet.true_profile.text_versions.select_related("era").order_by("field", "-created_at")
        )
        reasoning_by_version = {
            row.applied_version_id: row.request.player_reasoning
            for row in ProfileTextRequestDetails.objects.filter(
                applied_version__in=versions
            ).select_related("request")
        }
        serializer = ProfileTextVersionSerializer(
            versions,
            many=True,
            context={"reasoning_by_version": reasoning_by_version},
        )
        return Response(serializer.data)
