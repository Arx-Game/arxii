"""
Views for the character sheets API.
"""

from http import HTTPMethod

from django.db.models import QuerySet
from django.http import Http404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ReadOnlyModelViewSet

from world.character_creation.services import (
    clear_origin_slot,
    set_origin_slot,
)
from world.character_sheets.filters import HeritageFilterSet, MoodOptionFilterSet
from world.character_sheets.models import CharacterSheet, Heritage, MoodOption
from world.character_sheets.serializers import (
    CharacterSheetSerializer,
    CharacterXPLedgerSerializer,
    HeritageSerializer,
    MaturationSpendInputSerializer,
    MaturationStateSerializer,
    MoodOptionSerializer,
    OriginSlotClearSerializer,
    OriginSlotInputSerializer,
    ProfileTextVersionSerializer,
    StaffEditSerializer,
    StatPointStateSerializer,
    _viewer_is_privileged,
    get_character_sheet_queryset,
)
from world.character_sheets.services import (
    StaffEditError,
    can_edit_character_sheet,
    can_staff_edit_sheet,
    restore_profile_text_version,
    staff_edit_sheet,
)
from world.character_sheets.types import ProfileTextField
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

    @extend_schema(responses={200: CharacterXPLedgerSerializer})
    @action(detail=True, methods=[HTTPMethod.GET], url_path="xp-ledger")
    def xp_ledger(self, request: Request, pk: int | None = None) -> Response:
        """What the owner has earned on, and invested in, this character (#3748).

        Owner-only: XP is the player's business, not something other players read
        off a public sheet.
        """
        from world.progression.selectors import character_xp_ledger  # noqa: PLC0415

        sheet = self.get_object()
        self._check_ownership(sheet)
        return Response(CharacterXPLedgerSerializer(character_xp_ledger(sheet)).data)

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
        if not _viewer_is_privileged(sheet, request.user) or sheet.true_profile is None:
            return Response([])

        versions_qs = sheet.true_profile.text_versions.select_related("era")
        if not request.user.is_staff:
            # The real concept is staff's (#3988): its history is too.
            versions_qs = versions_qs.exclude(field=ProfileTextField.REAL_CONCEPT)
            # Tenure-scoped (#3988, amends the #2631 ruling): a player sees only what was
            # written since their own current tenure began, so a new roster tenant never
            # reads the previous player's prose. The character's first player wrote all of
            # it, so their view has no cutoff. A later tenure with no start date shows none.
            tenure = sheet.roster_entry.current_tenure if sheet.roster_entry else None
            if tenure is None:
                return Response([])
            if tenure.player_number != 1:
                if tenure.start_date is None:
                    return Response([])
                versions_qs = versions_qs.filter(created_at__gte=tenure.start_date)
        versions = list(versions_qs.order_by("field", "-created_at"))
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

    def _require_staff_edit(self, sheet: CharacterSheet) -> None:
        """404 unless this account may edit the sheet in place (#3988)."""
        if not can_staff_edit_sheet(self.request.user, sheet):
            raise Http404

    def _fresh_payload(self, request: Request, pk: int | None) -> Response:
        """The refreshed sheet payload, read the way GET reads it."""
        sheet = get_character_sheet_queryset().get(pk=pk)
        return Response(CharacterSheetSerializer(sheet, context={"request": request}).data)

    @extend_schema(request=StaffEditSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.PATCH], url_path="staff-edit")
    def staff_edit(self, request: Request, pk: int | None = None) -> Response:
        """Edit a sheet's prose and identity in place (#3988, staff edit mode).

        Prose saves through ``update_profile_text``, so every change is a version.
        Fields outside the staff-edit list are refused. Answers with the refreshed
        sheet payload.
        """
        sheet = self.get_object()
        self._require_staff_edit(sheet)
        serializer = StaffEditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            staff_edit_sheet(sheet, serializer.validated_data, edited_by=request.user)
        except StaffEditError as exc:
            return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)
        return self._fresh_payload(request, pk)

    @extend_schema(request=None, responses={200: CharacterSheetSerializer})
    @action(
        detail=True,
        methods=[HTTPMethod.POST],
        url_path=r"profile-text-versions/(?P<version_id>[0-9]+)/restore",
    )
    def restore_profile_text_version(
        self, request: Request, pk: int | None = None, version_id: str | None = None
    ) -> Response:
        """Write a past version back as the current text (#3988). Staff only.

        A restore adds a version and deletes nothing.
        """
        sheet = self.get_object()
        self._require_staff_edit(sheet)
        if sheet.true_profile is None:
            raise Http404
        version = sheet.true_profile.text_versions.filter(pk=version_id).first()
        if version is None:
            raise Http404
        restore_profile_text_version(version, edited_by=request.user)
        return self._fresh_payload(request, pk)


class HeritageViewSet(ReadOnlyModelViewSet):
    """Every heritage, for staff edit mode's heritage picker (#3988)."""

    pagination_class = None  # a handful of rows; the picker is the whole list (ADR-0138)
    serializer_class = HeritageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = HeritageFilterSet

    def get_queryset(self) -> QuerySet[Heritage]:
        return Heritage.objects.order_by("name")


class MoodOptionViewSet(ReadOnlyModelViewSet):
    """The moods a look can be tagged with (#4151), for the Gallery's mood picker."""

    serializer_class = MoodOptionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = MoodOptionFilterSet

    def get_queryset(self) -> QuerySet[MoodOption]:
        return MoodOption.objects.filter(is_active=True).order_by("sort_order", "name")
