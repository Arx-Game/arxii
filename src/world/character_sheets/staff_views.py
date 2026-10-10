"""Staff edit mode's row actions on the sheet API (#4221, #3988 piece B).

Every action is gated by ``can_staff_edit_sheet`` (a 404 otherwise, as a non-owner
finding a sheet's edit door should learn nothing), validates its family's input,
calls the one service that writes that family, and answers with the refreshed
sheet payload so the client replaces its cache. Each choice runs the grants CG
runs for it, so a staff-built sheet ends where CG would have left it.
"""

from __future__ import annotations

from http import HTTPMethod
from typing import TYPE_CHECKING, Any

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from world.character_creation.sheet_writers import (
    SheetWriteError,
    beginnings_consequences,
    distinction_consequences,
    initialize_full_vitals,
    path_consequences,
    set_beginnings,
    set_enemy,
    set_skill_values,
    set_stat_values,
    set_trait_descriptors,
    set_true_form_values,
    set_worship_declaration,
)
from world.character_sheets.serializers import CharacterSheetSerializer
from world.character_sheets.staff_serializers import (
    StaffBeginningsSerializer,
    StaffDistinctionAddSerializer,
    StaffDistinctionChangeSerializer,
    StaffEnemySerializer,
    StaffFormSerializer,
    StaffGoalsSerializer,
    StaffIntroductionSerializer,
    StaffMarkingAddSerializer,
    StaffMarkingRemoveSerializer,
    StaffOptionsSerializer,
    StaffPathSerializer,
    StaffSkillsSerializer,
    StaffStatsSerializer,
    StaffWorshipSerializer,
)
from world.traits.models import TraitChangeSource

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


def _refused(exc: SheetWriteError) -> Response:
    return Response({"detail": exc.user_message}, status=status.HTTP_400_BAD_REQUEST)


class StaffSheetRowsMixin:
    """The row-writing staff actions; the viewset supplies the gate and the payload."""

    def _staff_sheet(self, request: Request) -> CharacterSheet:
        sheet = self.get_object()
        self._require_staff_edit(sheet)
        return sheet

    def _validated(self, serializer_cls: Any, request: Request, sheet: CharacterSheet) -> Any:
        serializer = serializer_cls(data=request.data, context={"sheet": sheet})
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def _answer(self, request: Request, sheet: CharacterSheet) -> Response:
        return self._fresh_payload(request, sheet.pk)

    @extend_schema(request=StaffStatsSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.PATCH], url_path="staff-stats")
    def staff_stats(self, request: Request, pk: int | None = None) -> Response:
        """Set stats at display scale (1 to 5); missing rows are created."""
        sheet = self._staff_sheet(request)
        data = self._validated(StaffStatsSerializer, request, sheet)
        try:
            set_stat_values(sheet, data["stats"], source=TraitChangeSource.STAFF_EDIT)
            _ensure_vitals_if_missing(sheet)
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(request=StaffSkillsSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.PATCH], url_path="staff-skills")
    def staff_skills(self, request: Request, pk: int | None = None) -> Response:
        """Set skills and specializations within the configured caps; no point budget."""
        sheet = self._staff_sheet(request)
        data = self._validated(StaffSkillsSerializer, request, sheet)
        try:
            set_skill_values(
                sheet,
                data["skills"],
                data["specializations"],
                source=TraitChangeSource.STAFF_EDIT,
            )
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(request=StaffDistinctionAddSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.POST], url_path="staff-distinctions")
    def staff_add_distinction(self, request: Request, pk: int | None = None) -> Response:
        """Add a distinction (origin Staff): exclusions hold, no XP, no request."""
        from world.distinctions.staff import staff_add_distinction  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffDistinctionAddSerializer, request, sheet)
        try:
            staff_add_distinction(
                sheet,
                data["distinction"],
                rank=data["rank"],
                feature_trait=data["feature_trait"],
                feature_marking=data["feature_marking"],
            )
            distinction_consequences(sheet, data["distinction"])
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(
        request=StaffDistinctionChangeSerializer, responses={200: CharacterSheetSerializer}
    )
    @action(detail=True, methods=[HTTPMethod.PATCH], url_path="staff-distinction")
    def staff_change_distinction(self, request: Request, pk: int | None = None) -> Response:
        """Re-rank a held distinction (``rank``), or remove it (no ``rank``). No XP."""
        from world.distinctions.staff import (  # noqa: PLC0415
            staff_remove_distinction,
            staff_set_distinction_rank,
        )

        sheet = self._staff_sheet(request)
        data = self._validated(StaffDistinctionChangeSerializer, request, sheet)
        try:
            if "rank" in data:  # noqa: STRING_LITERAL - the input serializer's field name
                staff_set_distinction_rank(data["character_distinction"], data["rank"])
            else:
                staff_remove_distinction(data["character_distinction"])
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(request=StaffFormSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.PATCH], url_path="staff-form")
    def staff_form(self, request: Request, pk: int | None = None) -> Response:
        """Set the TRUE form's options (creating the form) and the primary face's descriptors."""
        sheet = self._staff_sheet(request)
        data = self._validated(StaffFormSerializer, request, sheet)
        try:
            if data["values"]:
                set_true_form_values(sheet, data["values"])
            if data["descriptors"]:
                set_trait_descriptors(sheet.primary_persona, data["descriptors"])
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(request=StaffBeginningsSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.PUT], url_path="staff-beginnings")
    def staff_beginnings(self, request: Request, pk: int | None = None) -> Response:
        """Set where play began; its rituals, codex and languages follow."""
        sheet = self._staff_sheet(request)
        data = self._validated(StaffBeginningsSerializer, request, sheet)
        set_beginnings(sheet, data["beginnings"])
        beginnings_consequences(sheet, data["beginnings"])
        return self._answer(request, sheet)

    @extend_schema(request=StaffPathSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.PATCH], url_path="staff-path")
    def staff_path(self, request: Request, pk: int | None = None) -> Response:
        """Give a pathless sheet its first path, and/or set the primary class level.

        Changing an existing path is out of scope: crossing into a path grants its magic.
        """
        from world.classes.services import (  # noqa: PLC0415
            ensure_default_character_class,
            set_primary_class_level,
        )
        from world.progression.models import CharacterPathHistory  # noqa: PLC0415
        from world.progression.services.advancement import select_initial_path  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffPathSerializer, request, sheet)
        path = data.get("path")
        if path is not None:
            if CharacterPathHistory.objects.filter(character=sheet).exists():
                return _refused(SheetWriteError("This character already has a path."))
            select_initial_path(sheet.character, path)
            path_consequences(sheet, path)
        if "level" in data:  # noqa: STRING_LITERAL - the input serializer's field name
            set_primary_class_level(
                sheet.character, ensure_default_character_class(), data["level"]
            )
        _ensure_vitals_if_missing(sheet)
        return self._answer(request, sheet)

    @extend_schema(request=StaffGoalsSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.PUT], url_path="staff-goals")
    def staff_goals(self, request: Request, pk: int | None = None) -> Response:
        """Replace the goals; the point cap holds, the weekly revision limit does not."""
        from world.goals.services import set_character_goals  # noqa: PLC0415
        from world.goals.types import GoalError  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffGoalsSerializer, request, sheet)
        try:
            set_character_goals(character=sheet, goals=data["goals"], bypass_revision_gate=True)
        except GoalError as exc:
            return _refused(SheetWriteError(exc.user_message))
        return self._answer(request, sheet)

    @extend_schema(request=StaffWorshipSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.PUT], url_path="staff-worship")
    def staff_worship(self, request: Request, pk: int | None = None) -> Response:
        """Set the public and secret worship; a secret being mints its Secret."""
        sheet = self._staff_sheet(request)
        data = self._validated(StaffWorshipSerializer, request, sheet)
        set_worship_declaration(sheet, data["public_being"], data["secret_being"])
        return self._answer(request, sheet)

    @extend_schema(request=StaffMarkingAddSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.POST], url_path="staff-markings")
    def staff_add_marking(self, request: Request, pk: int | None = None) -> Response:
        """Add a marking (a distinctive feature) to the TRUE form."""
        from world.forms.services.markings import grant_marking  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffMarkingAddSerializer, request, sheet)
        grant_marking(sheet, **data)
        return self._answer(request, sheet)

    @extend_schema(request=StaffMarkingRemoveSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.PATCH], url_path="staff-marking-remove")
    def staff_remove_marking(self, request: Request, pk: int | None = None) -> Response:
        """Remove a marking; a per-feature distinction aimed at it goes with it."""
        from world.forms.services.markings import remove_marking  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffMarkingRemoveSerializer, request, sheet)
        remove_marking(data["marking"])
        return self._answer(request, sheet)

    @extend_schema(request=StaffEnemySerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.PUT], url_path="staff-enemy")
    def staff_enemy(self, request: Request, pk: int | None = None) -> Response:
        """Write the Actor's Sheet enemy row: a new one, or the one ``id`` names."""
        sheet = self._staff_sheet(request)
        data = dict(self._validated(StaffEnemySerializer, request, sheet))
        enemy = data.pop("enemy", None)
        try:
            set_enemy(sheet, enemy=enemy, **data)
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(request=StaffIntroductionSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.POST], url_path="staff-introductions")
    def staff_introduction(self, request: Request, pk: int | None = None) -> Response:
        """Write one Introduction as the character's journal (#3621). No journal XP."""
        from world.journals.services import create_journal_entry  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffIntroductionSerializer, request, sheet)
        create_journal_entry(
            author=sheet,
            title=data["title"],
            body=data["body"],
            is_public=True,
            award_weekly_xp=False,
            kind=data["kind"],
        )
        return self._answer(request, sheet)

    @extend_schema(responses={200: StaffOptionsSerializer})
    @action(detail=True, methods=[HTTPMethod.GET], url_path="staff-options")
    def staff_options(self, request: Request, pk: int | None = None) -> Response:
        """What the row editors pick from: the catalogs and this species' form options."""
        sheet = self._staff_sheet(request)
        return Response(StaffOptionsSerializer(_staff_options(sheet)).data)

    @extend_schema(request=None, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.POST], url_path="staff-vitals")
    def staff_vitals(self, request: Request, pk: int | None = None) -> Response:
        """Create the vitals row and fill health, for a sheet that has none."""
        sheet = self._staff_sheet(request)
        initialize_full_vitals(sheet)
        return self._answer(request, sheet)


def _ensure_vitals_if_missing(sheet: CharacterSheet) -> None:
    """A sheet without vitals may not function in play; a stat or level edit fills them."""
    from world.vitals.models import CharacterVitals  # noqa: PLC0415

    if not CharacterVitals.objects.filter(character_sheet=sheet).exists():
        initialize_full_vitals(sheet)


def _named(rows: Any, name: str = "name") -> list[dict[str, Any]]:
    return [{"id": row.pk, "name": getattr(row, name)} for row in rows]


def _staff_options(sheet: CharacterSheet) -> dict[str, Any]:
    """The catalogs a staff editor picks from; form options are the species' CG palette."""
    from world.character_creation.models import Beginnings  # noqa: PLC0415
    from world.character_sheets.types import (  # noqa: PLC0415
        EnemyDegree,
        EnemyKind,
        EnemyPowerTier,
    )
    from world.classes.models import Path  # noqa: PLC0415
    from world.distinctions.models import Distinction  # noqa: PLC0415
    from world.forms.constants import MarkingKind  # noqa: PLC0415
    from world.forms.services import get_cg_form_options  # noqa: PLC0415
    from world.items.constants import BodyRegion  # noqa: PLC0415
    from world.skills.models import Skill, Specialization  # noqa: PLC0415
    from world.traits.models import Trait, TraitType  # noqa: PLC0415
    from world.worship.models import WorshippedBeing  # noqa: PLC0415

    form = get_cg_form_options(sheet.species) if sheet.species is not None else {}
    return {
        "stats": _named(Trait.objects.filter(trait_type=TraitType.STAT).order_by("name")),
        "skills": _named(Skill.objects.select_related("trait").order_by("trait__name")),
        "specializations": _named(Specialization.objects.order_by("name")),
        "distinctions": _named(Distinction.objects.order_by("name")),
        "form_traits": [
            {
                "id": trait.pk,
                "name": trait.display_name,
                "options": _named(options, "display_name"),
            }
            for trait, options in form.items()
        ],
        "beginnings": _named(Beginnings.objects.order_by("name")),
        "paths": _named(Path.objects.order_by("name")),
        "beings": _named(WorshippedBeing.objects.order_by("name")),
        "marking_regions": _choices(BodyRegion),
        "marking_kinds": _choices(MarkingKind),
        "enemy_kinds": _choices(EnemyKind),
        "enemy_degrees": _choices(EnemyDegree),
        "enemy_power_tiers": _choices(EnemyPowerTier),
    }


def _choices(choices: Any) -> list[dict[str, str]]:
    return [{"value": value, "label": label} for value, label in choices.choices]
