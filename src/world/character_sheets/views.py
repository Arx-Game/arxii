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
    MaturationSpendInputSerializer,
    MaturationStateSerializer,
    OriginSlotClearSerializer,
    OriginSlotInputSerializer,
    ProfileTextVersionSerializer,
    StatPointStateSerializer,
    _viewer_is_privileged,
    get_character_sheet_queryset,
)
from world.character_sheets.services import can_edit_character_sheet
from world.scenes.block_services import sheet_blocked_for_viewer


def _spendable_stat_rows(sheet: CharacterSheet, cap: int | None) -> list[dict]:
    """Display-dot stat rows for the maturation/stat-point spend panels (#2756/#3001)."""
    from world.traits.constants import STAT_DISPLAY_DIVISOR  # noqa: PLC0415
    from world.traits.models import CharacterTraitValue, Trait, TraitType  # noqa: PLC0415

    values = {
        tv.trait_id: tv.value // STAT_DISPLAY_DIVISOR
        for tv in CharacterTraitValue.objects.filter(
            character=sheet, trait__trait_type=TraitType.STAT
        )
    }
    return [
        {
            "trait_id": trait.pk,
            "name": trait.name,
            "value": values.get(trait.pk, 0),
            "at_cap": cap is not None and values.get(trait.pk, 0) >= cap,
        }
        for trait in Trait.objects.filter(trait_type=TraitType.STAT, is_public=True).order_by(
            "name"
        )
    ]


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
        """Set a character's origin-story slot answer (#2478, #3617).

        A costed pick-list choice is set at character creation only; a non-staff
        caller sending ``choice_id`` here is refused. A text-only write on a slot
        that already carries a choice keeps that choice (write-ins never clear it).
        """
        sheet = self.get_object()
        self._check_ownership(sheet)
        serializer = OriginSlotInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from world.character_creation.models import (  # noqa: PLC0415
            CharacterOriginSlot,
            OriginTemplateSlot,
        )

        try:
            slot = OriginTemplateSlot.objects.get(pk=serializer.validated_data["slot_id"])
        except OriginTemplateSlot.DoesNotExist:
            return Response({"detail": "Slot not found."}, status=status.HTTP_404_NOT_FOUND)

        choice_id = serializer.validated_data.get("choice_id")
        if choice_id is not None:
            if not request.user.is_staff:
                return Response(
                    {"detail": "Upbringing choices are set at character creation."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            from world.character_creation.models import OriginTemplateSlotChoice  # noqa: PLC0415

            choice = OriginTemplateSlotChoice.objects.filter(pk=choice_id, slot=slot).first()
            if choice is None:
                return Response({"detail": "Choice not found."}, status=status.HTTP_404_NOT_FOUND)
        else:
            existing = CharacterOriginSlot.objects.filter(sheet=sheet, slot=slot).first()
            choice = existing.choice if existing is not None else None
        set_origin_slot(sheet, slot, serializer.validated_data["value"], choice=choice)
        return Response(status=status.HTTP_200_OK)

    @action(detail=True, methods=[HTTPMethod.POST], url_path="clear-origin-slot")
    def clear_origin_slot_action(self, request: Request, pk: int | None = None) -> Response:
        """Clear a character's origin-story slot answer (#2478, #3617).

        A slot holding a costed choice was set at character creation; a
        non-staff caller clearing it here would erase a priced pick for free,
        so that combination is refused the same way setting one is.
        """
        sheet = self.get_object()
        self._check_ownership(sheet)
        serializer = OriginSlotClearSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from world.character_creation.models import (  # noqa: PLC0415
            CharacterOriginSlot,
            OriginTemplateSlot,
        )

        try:
            slot = OriginTemplateSlot.objects.get(pk=serializer.validated_data["slot_id"])
        except OriginTemplateSlot.DoesNotExist:
            return Response({"detail": "Slot not found."}, status=status.HTTP_404_NOT_FOUND)
        existing = CharacterOriginSlot.objects.filter(sheet=sheet, slot=slot).first()
        if existing is not None and existing.choice_id is not None and not request.user.is_staff:
            return Response(
                {"detail": "Upbringing choices are set at character creation."},
                status=status.HTTP_403_FORBIDDEN,
            )
        clear_origin_slot(sheet, slot)
        return Response(status=status.HTTP_200_OK)

    @extend_schema(responses={200: MaturationStateSerializer})
    @action(detail=True, methods=[HTTPMethod.GET], url_path="maturation")
    def maturation(self, request: Request, pk: int | None = None) -> Response:
        """The owner's Maturation Point panel state (#2756)."""
        from world.progression.services.maturation import (  # noqa: PLC0415
            available_points,
            next_milestone_year,
            stat_cap_for,
        )

        sheet = self.get_object()
        self._check_ownership(sheet)
        next_milestone = next_milestone_year(sheet.matured_years)
        cap = stat_cap_for(sheet)
        stats = _spendable_stat_rows(sheet, cap)
        payload = MaturationStateSerializer(
            {
                "available_points": available_points(sheet),
                "stat_cap": cap,
                "matured_years": sheet.matured_years,
                "next_milestone_year": next_milestone,
                "stats": stats,
            }
        )
        return Response(payload.data)

    @extend_schema(
        request=MaturationSpendInputSerializer, responses={200: MaturationStateSerializer}
    )
    @action(detail=True, methods=[HTTPMethod.POST], url_path="spend-maturation-point")
    def spend_maturation_point_action(self, request: Request, pk: int | None = None) -> Response:
        """Spend one Maturation Point on +1 to a stat (#2756)."""
        from world.progression.exceptions import MaturationError  # noqa: PLC0415
        from world.progression.services.maturation import spend_maturation_point  # noqa: PLC0415
        from world.traits.models import Trait  # noqa: PLC0415

        sheet = self.get_object()
        self._check_ownership(sheet)
        serializer = MaturationSpendInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            trait = Trait.objects.get(pk=serializer.validated_data["trait_id"])
        except Trait.DoesNotExist:
            return Response({"detail": "Trait not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            spend_maturation_point(sheet, trait)
        except MaturationError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return self.maturation(request, pk=pk)

    @extend_schema(responses={200: StatPointStateSerializer})
    @action(detail=True, methods=[HTTPMethod.GET], url_path="stat-points")
    def stat_points(self, request: Request, pk: int | None = None) -> Response:
        """The owner's Level Stat Point panel state (#3001)."""
        from world.progression.services.maturation import stat_cap_for  # noqa: PLC0415
        from world.progression.services.skill_development import (  # noqa: PLC0415
            get_character_path_level,
        )
        from world.progression.services.stat_points import available_stat_points  # noqa: PLC0415

        sheet = self.get_object()
        self._check_ownership(sheet)
        cap = stat_cap_for(sheet)
        stats = _spendable_stat_rows(sheet, cap)
        payload = StatPointStateSerializer(
            {
                "available_points": available_stat_points(sheet),
                "stat_cap": cap,
                "level": get_character_path_level(sheet.character),
                "stats": stats,
            }
        )
        return Response(payload.data)

    @extend_schema(
        request=MaturationSpendInputSerializer, responses={200: StatPointStateSerializer}
    )
    @action(detail=True, methods=[HTTPMethod.POST], url_path="spend-stat-point")
    def spend_stat_point_action(self, request: Request, pk: int | None = None) -> Response:
        """Spend one Level Stat Point on +1 to a stat (#3001)."""
        from world.progression.exceptions import StatPointError  # noqa: PLC0415
        from world.progression.services.stat_points import spend_level_stat_point  # noqa: PLC0415
        from world.traits.models import Trait  # noqa: PLC0415

        sheet = self.get_object()
        self._check_ownership(sheet)
        serializer = MaturationSpendInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            trait = Trait.objects.get(pk=serializer.validated_data["trait_id"])
        except Trait.DoesNotExist:
            return Response({"detail": "Trait not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            spend_level_stat_point(sheet, trait)
        except StatPointError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return self.stat_points(request, pk=pk)

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
