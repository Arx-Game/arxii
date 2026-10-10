"""Staff edit mode's row actions on the sheet API (#4221, #3988 piece B).

Every action is gated by ``can_staff_edit_sheet`` (a 404 otherwise, as a non-owner
finding a sheet's edit door should learn nothing), validates its family's input,
calls the one service that writes that family, and answers with the refreshed
sheet payload so the client replaces its cache. Each choice runs the grants CG
runs for it, so a staff-built sheet ends where CG would have left it.
"""

from __future__ import annotations

from http import HTTPMethod
from typing import TYPE_CHECKING, Any, cast

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
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
    StaffCovenantMembershipSerializer,
    StaffCovenantRoleAddSerializer,
    StaffDistinctionAddSerializer,
    StaffDistinctionChangeSerializer,
    StaffEnemySerializer,
    StaffEstateOptionsSerializer,
    StaffFormSerializer,
    StaffGoalsSerializer,
    StaffGroupOptionsSerializer,
    StaffHouseClaimSerializer,
    StaffIntroductionSerializer,
    StaffKinshipSerializer,
    StaffMagicOptionsSerializer,
    StaffMagicSerializer,
    StaffMarkingAddSerializer,
    StaffMarkingRemoveSerializer,
    StaffMentorBondSerializer,
    StaffMentorDissolveSerializer,
    StaffNobleTitleSerializer,
    StaffOptionsSerializer,
    StaffPathSerializer,
    StaffPersonaChangeSerializer,
    StaffPersonaCreateSerializer,
    StaffPersonaRemoveSerializer,
    StaffPropertySerializer,
    StaffReputationSerializer,
    StaffResidenceSerializer,
    StaffSkillsSerializer,
    StaffStatsSerializer,
    StaffTieLabelAddSerializer,
    StaffTieLabelChangeSerializer,
    StaffTieSerializer,
    StaffTitleGrantSerializer,
    StaffTitleRevokeSerializer,
    StaffVacancySerializer,
    StaffWorshipSerializer,
)
from world.traits.models import TraitChangeSource

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

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

    @extend_schema(request=StaffMagicSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.POST], url_path="staff-magic")
    def staff_magic(self, request: Request, pk: int | None = None) -> Response:
        """Grant a giftless sheet its magic, as CG's magic stage would (#4224).

        The CG stage's structural rules hold (a gift the tradition offers on the sheet's
        path, available finished techniques within the pick limit, a resonance, an anima
        stat and skill); its costs do not. Changing magic that exists is out of scope.
        """
        from world.character_creation.magic_writer import (  # noqa: PLC0415
            MagicPicks,
            provision_magic,
            validate_staff_magic,
        )
        from world.character_creation.sheet_writers import creation_beginnings  # noqa: PLC0415
        from world.magic.constants import AcquisitionOrigin  # noqa: PLC0415
        from world.magic.exceptions import MagicError  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffMagicSerializer, request, sheet)
        tenure = sheet.roster_entry.current_tenure if sheet.roster_entry else None
        picks = MagicPicks(
            tradition=data["tradition"],
            gift=data["gift"],
            techniques=data["techniques"],
            resonance=data["resonance"],
            anima_stat=data["anima_stat"],
            anima_skill=data["anima_skill"],
            ritual_name=data.get("ritual_name") or f"{sheet.character.db_key}'s Anima Ritual",
            # The ritual is the player's; staff author it only for a character nobody plays.
            account=tenure.player_data.account if tenure else cast("AccountDB", request.user),
            origin=AcquisitionOrigin.CHARACTER_CREATION,
            species=sheet.species,
            beginnings=creation_beginnings(sheet),
            glimpse_story=data["glimpse"],
        )
        try:
            validate_staff_magic(sheet, picks)
            provision_magic(sheet, picks)
        except SheetWriteError as exc:
            return _refused(exc)
        except MagicError as exc:
            return _refused(SheetWriteError(str(exc.user_message)))
        return self._answer(request, sheet)

    @extend_schema(responses={200: StaffMagicOptionsSerializer})
    @action(detail=True, methods=[HTTPMethod.GET], url_path="staff-magic-options")
    def staff_magic_options(self, request: Request, pk: int | None = None) -> Response:
        """What Grant magic offers, given ``?tradition=`` and ``?gift=`` picked so far."""
        sheet = self._staff_sheet(request)
        return Response(
            StaffMagicOptionsSerializer(
                _magic_options(
                    sheet,
                    request.query_params.get("tradition"),
                    request.query_params.get("gift"),
                )
            ).data
        )

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

    # --- Kinship, estate and reputation (#4226, #3988 piece D) ------------------

    @extend_schema(request=StaffKinshipSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.POST], url_path="staff-kinship")
    def staff_kinship(self, request: Request, pk: int | None = None) -> Response:
        """Place the character in the kin tree: claim an open position, or self-serve one."""
        from world.character_creation.estate_writer import bind_kinship_node  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffKinshipSerializer, request, sheet)
        try:
            bind_kinship_node(sheet, node=data["node"], family=data["family"] or sheet.family)
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(request=StaffResidenceSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.POST], url_path="staff-residence")
    def staff_residence(self, request: Request, pk: int | None = None) -> Response:
        """Make the character a tenant of a room, as CG's starting residence does."""
        from world.character_creation.estate_writer import grant_residence  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffResidenceSerializer, request, sheet)
        try:
            grant_residence(sheet, data["room_profile"])
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(request=StaffPropertySerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.POST], url_path="staff-property")
    def staff_property(self, request: Request, pk: int | None = None) -> Response:
        """Grant a property house, once per profile; blank uses the Beginnings' profile."""
        from world.character_creation.estate_writer import grant_property  # noqa: PLC0415
        from world.character_creation.sheet_writers import creation_beginnings  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffPropertySerializer, request, sheet)
        profile = data["profile"]
        if profile is None:
            beginnings = creation_beginnings(sheet)
            profile = beginnings.property_grant_profile if beginnings is not None else None
        if profile is None:
            return _refused(SheetWriteError("Choose a grant profile; the Beginnings carries none."))
        try:
            grant_property(sheet, profile)
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(request=StaffHouseClaimSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.POST], url_path="staff-house-claim")
    def staff_house_claim(self, request: Request, pk: int | None = None) -> Response:
        """Materialize an approved house claim with this character as its founder."""
        from world.character_creation.estate_writer import bind_house_claim  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffHouseClaimSerializer, request, sheet)
        try:
            bind_house_claim(sheet, data["claim"])
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(request=StaffVacancySerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.POST], url_path="staff-vacancy")
    def staff_vacancy(self, request: Request, pk: int | None = None) -> Response:
        """Take an opening: its kin position, if it has one, then the membership."""
        from world.character_creation.estate_writer import bind_vacancy  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffVacancySerializer, request, sheet)
        try:
            bind_vacancy(sheet, data["vacancy"], created_by=cast("AccountDB", request.user))
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(request=StaffReputationSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.PUT], url_path="staff-reputation")
    def staff_reputation(self, request: Request, pk: int | None = None) -> Response:
        """Set an organization's opinion of the character (the clamp holds)."""
        from world.character_creation.estate_writer import (  # noqa: PLC0415
            set_organization_reputation,
        )

        sheet = self._staff_sheet(request)
        data = self._validated(StaffReputationSerializer, request, sheet)
        try:
            set_organization_reputation(sheet, data["organization"], data["value"])
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(responses={200: StaffEstateOptionsSerializer})
    @action(detail=True, methods=[HTTPMethod.GET], url_path="staff-estate-options")
    def staff_estate_options(self, request: Request, pk: int | None = None) -> Response:
        """What the kin, estate and reputation editors offer; ``?room=`` searches rooms."""
        self._staff_sheet(request)  # the gate: a 404 for anyone who may not edit it
        options = _estate_options(request.query_params.get("room", ""))
        return Response(StaffEstateOptionsSerializer(options).data)

    # --- Group fit (#4229, #3988 piece E) ---------------------------------------

    @extend_schema(request=StaffPersonaCreateSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.POST], url_path="staff-personas")
    def staff_add_persona(self, request: Request, pk: int | None = None) -> Response:
        """Give the character a new established identity (no cap for staff)."""
        from world.character_sheets.group_writer import (  # noqa: PLC0415
            create_established_persona,
        )

        sheet = self._staff_sheet(request)
        data = self._validated(StaffPersonaCreateSerializer, request, sheet)
        try:
            create_established_persona(sheet, data["name"])
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(request=StaffPersonaChangeSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.PATCH], url_path="staff-persona")
    def staff_change_persona(self, request: Request, pk: int | None = None) -> Response:
        """Rename one of the character's faces and/or write its cover bio (versioned)."""
        from django.db import transaction  # noqa: PLC0415

        from world.character_sheets.group_writer import (  # noqa: PLC0415
            rename_persona,
            set_guise_prose,
        )
        from world.character_sheets.serializers import GUISE_FIELDS  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffPersonaChangeSerializer, request, sheet)
        persona = data["persona"]
        prose = {field: data[field] for field in GUISE_FIELDS if field in data}
        try:
            with transaction.atomic():
                if "name" in data:  # noqa: STRING_LITERAL - the input serializer's field name
                    rename_persona(persona, data["name"])
                if prose:
                    set_guise_prose(persona, edited_by=cast("AccountDB", request.user), prose=prose)
        except SheetWriteError as exc:
            persona.flush_from_cache(force=True)
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(request=StaffPersonaRemoveSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.POST], url_path="staff-persona-remove")
    def staff_remove_persona(self, request: Request, pk: int | None = None) -> Response:
        """Remove an identity nobody has played; one with history stays."""
        from world.character_sheets.group_writer import remove_persona  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffPersonaRemoveSerializer, request, sheet)
        try:
            remove_persona(data["persona"])
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(request=StaffTitleGrantSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.POST], url_path="staff-titles")
    def staff_grant_title(self, request: Request, pk: int | None = None) -> Response:
        """Give one of the character's faces a title reward or one of its deeds."""
        from world.character_sheets.group_writer import grant_persona_title  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffTitleGrantSerializer, request, sheet)
        try:
            grant_persona_title(
                data["persona"], reward=data["reward"], legend_entry=data["legend_entry"]
            )
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(request=StaffTitleRevokeSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.POST], url_path="staff-title-remove")
    def staff_revoke_title(self, request: Request, pk: int | None = None) -> Response:
        """Take a title away from one of the character's faces."""
        from world.character_sheets.group_writer import revoke_persona_title  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffTitleRevokeSerializer, request, sheet)
        revoke_persona_title(data["title"])
        return self._answer(request, sheet)

    @extend_schema(request=StaffNobleTitleSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.POST], url_path="staff-noble-title")
    def staff_noble_title(self, request: Request, pk: int | None = None) -> Response:
        """Seat the character on a noble title (staff fiat through ``pass_title``)."""
        from world.character_sheets.group_writer import seat_noble_title  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffNobleTitleSerializer, request, sheet)
        try:
            seat_noble_title(sheet, data["title"])
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(request=StaffTieLabelAddSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.POST], url_path="staff-tie-labels")
    def staff_add_tie_label(self, request: Request, pk: int | None = None) -> Response:
        """Declare a label on either side of a tie with another character."""
        from world.character_sheets.group_writer import (  # noqa: PLC0415
            declare_tie_label,
            tie_side,
        )

        sheet = self._staff_sheet(request)
        data = self._validated(StaffTieLabelAddSerializer, request, sheet)
        try:
            side = tie_side(sheet, data["other"], data["direction"])
            declare_tie_label(side, data["type"], data["awareness"])
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(request=StaffTieLabelChangeSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.PATCH], url_path="staff-tie-label")
    def staff_change_tie_label(self, request: Request, pk: int | None = None) -> Response:
        """Shift, reveal or end a label on either side of one of the character's ties."""
        from world.character_sheets.group_writer import change_tie_label  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffTieLabelChangeSerializer, request, sheet)
        try:
            change_tie_label(
                data["label"],
                new_type=data["new_type"],
                awareness=data["awareness"],
                end=data["end"],
            )
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(request=StaffTieSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.PATCH], url_path="staff-tie")
    def staff_tie(self, request: Request, pk: int | None = None) -> Response:
        """Set a side's summary and/or claimed tier (no XP, no capstone entry)."""
        from world.character_sheets.group_writer import (  # noqa: PLC0415
            set_tie_state,
            tie_side,
        )

        sheet = self._staff_sheet(request)
        data = self._validated(StaffTieSerializer, request, sheet)
        try:
            side = tie_side(sheet, data["other"], data["direction"])
            set_tie_state(side, summary=data["summary"], tier=data["tier"])
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(
        request=StaffCovenantRoleAddSerializer, responses={200: CharacterSheetSerializer}
    )
    @action(detail=True, methods=[HTTPMethod.POST], url_path="staff-covenant-roles")
    def staff_add_covenant_role(self, request: Request, pk: int | None = None) -> Response:
        """Make the character a covenant member in a role (no induction, no band gate)."""
        from world.character_sheets.group_writer import assign_role  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffCovenantRoleAddSerializer, request, sheet)
        try:
            assign_role(sheet, data["covenant"], data["covenant_role"], rank=data["rank"])
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(
        request=StaffCovenantMembershipSerializer, responses={200: CharacterSheetSerializer}
    )
    @action(detail=True, methods=[HTTPMethod.PATCH], url_path="staff-covenant-role")
    def staff_change_covenant_role(self, request: Request, pk: int | None = None) -> Response:
        """One change to a membership: role, rank, engagement, or end it."""
        from world.character_sheets.group_writer import change_membership  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffCovenantMembershipSerializer, request, sheet)
        try:
            change_membership(
                data["membership"],
                covenant_role=data["covenant_role"],
                rank=data["rank"],
                engaged=data["engaged"],
                as_secondary=data["as_secondary"],
                end=data["end"],
            )
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(
        request=StaffMentorBondSerializer,
        responses={
            200: inline_serializer(
                name="StaffMentorBondResult",
                fields={
                    "warning": serializers.CharField(allow_blank=True),
                    "sheet": CharacterSheetSerializer(),
                },
            )
        },
    )
    @action(detail=True, methods=[HTTPMethod.POST], url_path="staff-mentor-bonds")
    def staff_add_mentor_bond(self, request: Request, pk: int | None = None) -> Response:
        """Bond the character and another as mentor and sidekick in a covenant.

        A pair outside the level band is bonded anyway and the answer carries the warning.
        """
        from world.character_sheets.group_writer import bond_mentor  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffMentorBondSerializer, request, sheet)
        other = data["other"]
        mentor, sidekick = (sheet, other) if data["as_mentor"] else (other, sheet)
        try:
            _bond, warning = bond_mentor(data["covenant"], mentor=mentor, sidekick=sidekick)
        except SheetWriteError as exc:
            return _refused(exc)
        return Response({"warning": warning, "sheet": self._answer(request, sheet).data})

    @extend_schema(request=StaffMentorDissolveSerializer, responses={200: CharacterSheetSerializer})
    @action(detail=True, methods=[HTTPMethod.POST], url_path="staff-mentor-bond-end")
    def staff_end_mentor_bond(self, request: Request, pk: int | None = None) -> Response:
        """End one of the character's mentor bonds."""
        from world.character_sheets.group_writer import dissolve_mentor  # noqa: PLC0415

        sheet = self._staff_sheet(request)
        data = self._validated(StaffMentorDissolveSerializer, request, sheet)
        try:
            dissolve_mentor(data["bond"])
        except SheetWriteError as exc:
            return _refused(exc)
        return self._answer(request, sheet)

    @extend_schema(responses={200: StaffGroupOptionsSerializer})
    @action(detail=True, methods=[HTTPMethod.GET], url_path="staff-group-options")
    def staff_group_options(self, request: Request, pk: int | None = None) -> Response:
        """What the group-fit editors offer; ``?character=`` searches other characters."""
        sheet = self._staff_sheet(request)
        options = _group_options(sheet, request.query_params.get("character", ""))
        return Response(StaffGroupOptionsSerializer(options).data)


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


def _magic_options(sheet: CharacterSheet, tradition_id: str | None, gift_id: str | None) -> dict:
    """Traditions; the tradition's gifts on the sheet's path; the gift's techniques and
    resonances; the anima stats and skills; the sheet's technique limit."""
    from world.character_creation.magic_writer import technique_pick_limit  # noqa: PLC0415
    from world.magic.models import Tradition  # noqa: PLC0415
    from world.magic.services.cg_catalog import (  # noqa: PLC0415
        get_gift_options,
        get_species_technique_options,
        get_technique_options,
    )
    from world.progression.models import CharacterPathHistory  # noqa: PLC0415
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    path_row = CharacterPathHistory.objects.filter(character=sheet).order_by("-pk").first()
    tradition = Tradition.objects.filter(pk=tradition_id).first() if tradition_id else None
    gifts = get_gift_options(tradition, path_row.path) if tradition and path_row else []
    gift = next((g for g in gifts if str(g.pk) == gift_id), None) if gift_id else None
    techniques: list[Any] = []
    if gift is not None and tradition is not None and path_row is not None:
        options = get_technique_options(
            path_row.path, gift, tradition, include_unready=True, exclude_gated=True
        )
        techniques = [
            technique
            for technique in [
                *options.pool,
                *options.tradition,
                *get_species_technique_options(sheet.species, include_unready=True),
            ]
            if technique.action_template_id
        ]
    return {
        "traditions": _named(Tradition.objects.order_by("name")),
        "gifts": _named(gifts),
        "techniques": _named(list({t.pk: t for t in techniques}.values())),
        "resonances": _named(gift.resonances.order_by("name")) if gift else [],
        "stats": _named(Trait.objects.filter(trait_type=TraitType.STAT).order_by("name")),
        "skills": _named(
            Skill.objects.filter(is_active=True).select_related("trait").order_by("trait__name")
        ),
        "technique_limit": technique_pick_limit(sheet),
    }


#: How many rooms a residence search answers with; rooms are searched, never listed.
ROOM_SEARCH_LIMIT = 20


def _estate_options(room_query: str) -> dict[str, Any]:
    """Open kin positions, families, matching rooms, grant profiles, approved house
    claims, open vacancies and organizations, for the piece D editors (#4226)."""
    from django.db.models import Q  # noqa: PLC0415

    from evennia_extensions.models import RoomProfile  # noqa: PLC0415
    from world.buildings.models import PropertyGrantProfile  # noqa: PLC0415
    from world.roster.models import Family, Kinsperson  # noqa: PLC0415
    from world.societies.houses.constants import HouseClaimStatus  # noqa: PLC0415
    from world.societies.houses.models import HouseClaim  # noqa: PLC0415
    from world.societies.models import Organization, Vacancy  # noqa: PLC0415

    positions = (
        Kinsperson.objects.filter(is_appable=True, sheet__isnull=True)
        .select_related("family")
        .order_by("family__name", "name")
    )
    query = room_query.strip()
    rooms = (
        RoomProfile.objects.filter(objectdb__db_key__icontains=query)
        .select_related("objectdb")
        .order_by("objectdb__db_key")[:ROOM_SEARCH_LIMIT]
        if query
        else []
    )
    vacancies = (
        Vacancy.objects.filter(is_active=True)
        .filter(Q(count_remaining__isnull=True) | Q(count_remaining__gt=0))
        .select_related("organization")
        .order_by("organization__name", "name")
    )
    return {
        "open_positions": [
            {
                "id": node.pk,
                "name": f"{node.name} ({node.family.name})" if node.family else node.name,
            }
            for node in positions
        ],
        "families": _named(Family.objects.order_by("name")),
        "rooms": [{"id": room.pk, "name": room.objectdb.db_key} for room in rooms],
        "grant_profiles": _named(PropertyGrantProfile.objects.order_by("name")),
        "house_claims": _named(
            HouseClaim.objects.filter(
                status=HouseClaimStatus.APPROVED, draft__account__is_staff=True
            ).order_by("house_name"),
            "house_name",
        ),
        "vacancies": [{"id": v.pk, "name": f"{v.organization.name}: {v.name}"} for v in vacancies],
        "organizations": _named(Organization.objects.order_by("name")),
    }


#: How many characters a tie or mentor search answers with; characters are searched.
CHARACTER_SEARCH_LIMIT = 20


def _group_options(sheet: CharacterSheet, character_query: str) -> dict[str, Any]:
    """Characters matching a search, the tie catalog and ladder, title rewards, the
    character's own deeds, noble titles, and covenants with their roles and ranks (#4229)."""
    from world.achievements.constants import RewardType  # noqa: PLC0415
    from world.achievements.models import RewardDefinition  # noqa: PLC0415
    from world.covenants.models import Covenant, CovenantRank, CovenantRole  # noqa: PLC0415
    from world.relationships.constants import LabelAwareness  # noqa: PLC0415
    from world.relationships.models import RelationshipTier, RelationshipType  # noqa: PLC0415
    from world.scenes.constants import PersonaType  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415
    from world.societies.houses.models import Title  # noqa: PLC0415
    from world.societies.models import LegendEntry  # noqa: PLC0415

    query = character_query.strip()
    characters = (
        Persona.objects.filter(persona_type=PersonaType.PRIMARY, name__icontains=query)
        .exclude(character_sheet=sheet)
        .order_by("name")[:CHARACTER_SEARCH_LIMIT]
        if query
        else []
    )
    deeds = (
        LegendEntry.objects.filter(persona__character_sheet=sheet)
        .select_related("persona")
        .order_by("persona__name", "title")
    )
    covenants = list(Covenant.objects.filter(dissolved_at__isnull=True).order_by("name"))
    roles = list(CovenantRole.objects.order_by("name"))
    ranks = list(
        CovenantRank.objects.filter(covenant__in=covenants).order_by("covenant_id", "tier")
    )
    return {
        "characters": [{"id": p.character_sheet_id, "name": p.name} for p in characters],
        "relationship_types": _named(RelationshipType.objects.order_by("display_order", "name")),
        "awareness": _choices(LabelAwareness),
        "tiers": [
            {"id": tier.tier_number, "name": tier.name}
            for tier in RelationshipTier.objects.order_by("tier_number")
        ],
        "title_rewards": _named(
            RewardDefinition.objects.filter(reward_type=RewardType.TITLE).order_by("name")
        ),
        "deeds": [{"id": d.pk, "name": f"{d.title} ({d.persona.name})"} for d in deeds],
        "noble_titles": [
            {"id": t.pk, "name": t.name or t.get_tier_display()}
            for t in Title.objects.order_by("name", "pk")
        ],
        "covenants": [
            {
                "id": covenant.pk,
                "name": covenant.name,
                "roles": _named(r for r in roles if r.covenant_type == covenant.covenant_type),
                "ranks": _named(r for r in ranks if r.covenant_id == covenant.pk),
            }
            for covenant in covenants
        ],
    }
