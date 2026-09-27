"""Menu and dispatch share one check (#4030): check_availability agrees with run()."""

from __future__ import annotations

import django.test

from actions.registry import get_action
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.consent.factories import SocialConsentPreferenceFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import (
    PersonaType,
    RoundStatus,
    SceneRoundParticipantStatus,
    SceneRoundStartReason,
)
from world.scenes.factories import PersonaFactory
from world.scenes.models import SceneActionDeclaration, SceneRound, SceneRoundParticipant


def _room(name: str) -> object:
    return ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.rooms.Room")


def _pc(name: str, room: object) -> tuple:
    actor = CharacterFactory(db_key=name, location=room)
    sheet = CharacterSheetFactory(character=actor)
    RosterTenureFactory(roster_entry=RosterEntryFactory(character_sheet=sheet))
    return actor, sheet


class ChallengeAvailabilityTests(django.test.TestCase):
    def setUp(self) -> None:
        self.room = _room("Arena")
        self.actor, _ = _pc("Challenger", self.room)
        self.target, self.target_sheet = _pc("Target", self.room)
        self.persona_pk = self.target_sheet.primary_persona.pk

    def _availability(self):
        return get_action("challenge").check_availability(
            self.actor, context={"kwargs": {"target": self.persona_pk}}
        )

    def test_available_for_a_consenting_colocated_target(self) -> None:
        assert self._availability().available

    def test_other_room_is_unavailable_with_the_run_message(self) -> None:
        self.target.move_to(_room("Elsewhere"), quiet=True)
        availability = self._availability()
        result = get_action("challenge").run(self.actor, target=self.persona_pk)
        assert not availability.available
        assert availability.reasons == [result.message]

    def test_self_is_unavailable(self) -> None:
        own = self.actor.sheet_data.primary_persona.pk
        availability = get_action("challenge").check_availability(
            self.actor, context={"kwargs": {"target": own}}
        )
        assert not availability.available

    def test_refusal_never_names_the_real_key(self) -> None:
        SocialConsentPreferenceFactory(
            tenure=self.target_sheet.roster_entry.current_tenure, allow_social_actions=False
        )
        availability = self._availability()
        assert not availability.available
        assert "Target" not in " ".join(availability.reasons)


class GuardAvailabilityTests(django.test.TestCase):
    def test_no_active_round_is_unavailable_with_the_run_message(self) -> None:
        room = _room("Hall")
        actor, _ = _pc("Guard", room)
        _ally, ally_sheet = _pc("Ally", room)
        pk = ally_sheet.primary_persona.pk
        for key in ("scene_succor", "scene_interpose"):
            availability = get_action(key).check_availability(
                actor, context={"kwargs": {"target_persona_id": pk}}
            )
            result = get_action(key).run(actor, target_persona_id=pk)
            assert not availability.available
            assert availability.reasons == [result.message]


class SuccorFindsAMaskedAllyByPersonaIdTests(django.test.TestCase):
    """A masked ally's ``ally_name=persona.name`` can't match the real character key —
    ``target_persona_id`` resolves through the persona itself, mask or not (#4030)."""

    def setUp(self) -> None:
        self.room = _room("MaskedHall")
        self.guard, self.guard_sheet = _pc("MaskedGuard", self.room)
        self.ally, self.ally_sheet = _pc("MaskedAllyRealName", self.room)
        self.mask = PersonaFactory(
            character_sheet=self.ally_sheet,
            name="A Cloaked Stranger",
            persona_type=PersonaType.TEMPORARY,
            is_fake_name=True,
        )
        self.scene_round = SceneRound.objects.create(
            room=RoomProfileFactory(objectdb=self.room),
            status=RoundStatus.DECLARING,
            round_number=1,
            start_reason=SceneRoundStartReason.OPT_IN,
        )
        self.guard_participant = SceneRoundParticipant.objects.create(
            scene_round=self.scene_round,
            character_sheet=self.guard_sheet,
            status=SceneRoundParticipantStatus.ACTIVE,
        )
        self.ally_participant = SceneRoundParticipant.objects.create(
            scene_round=self.scene_round,
            character_sheet=self.ally_sheet,
            status=SceneRoundParticipantStatus.ACTIVE,
        )

    def test_available_via_target_persona_id_under_a_mask(self) -> None:
        availability = get_action("scene_succor").check_availability(
            self.guard, context={"kwargs": {"target_persona_id": self.mask.pk}}
        )
        assert availability.available

    def test_ally_name_on_the_masked_display_name_does_not_resolve(self) -> None:
        """The old ``ally_name`` path matches the real character key, not the mask's name."""
        availability = get_action("scene_succor").check_availability(
            self.guard, context={"kwargs": {"ally_name": self.mask.name}}
        )
        assert not availability.available

    def test_run_declares_succor_against_the_real_participant(self) -> None:
        result = get_action("scene_succor").run(self.guard, target_persona_id=self.mask.pk)

        assert result.success, result.message
        decl = SceneActionDeclaration.objects.get(
            scene_round=self.scene_round,
            round_number=1,
            participant=self.guard_participant,
        )
        assert decl.succor_target_id == self.ally_participant.pk
