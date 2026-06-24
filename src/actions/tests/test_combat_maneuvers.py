"""Tests for combat maneuver actions (#1453, #1452).

These drive the actions through ``Action.run()`` — the same lifecycle the telnet
command and web viewset reach via ``dispatch_player_action`` — so they cover the
full shared seam, not just the service call.
"""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.combat_maneuvers import (
    CoverAction,
    FleeAction,
    InterposeAction,
    JoinEncounterAction,
    LeaveEncounterAction,
    ReadyAction,
    RevertComboAction,
    UpgradeComboAction,
)
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    CombatManeuver,
    EncounterStatus,
    EncounterType,
    ParticipantStatus,
)
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import CombatParticipant, CombatRoundAction
from world.combat.services import declare_flee
from world.vitals.models import CharacterVitals


class CombatManeuverActionTestBase(TestCase):
    """Shared fixture: a player character active in a DECLARING encounter."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory(db_key="maneuverchar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            character_sheet=cls.sheet,
            status=ParticipantStatus.ACTIVE,
        )
        CharacterVitals.objects.get_or_create(
            character_sheet=cls.sheet,
            defaults={"health": 50, "max_health": 100},
        )


class FleeActionTest(CombatManeuverActionTestBase):
    def test_flee_declares_flee_maneuver(self) -> None:
        result = FleeAction().run(self.character)
        self.assertTrue(result.success, result.message)
        action = CombatRoundAction.objects.get(
            participant=self.participant,
            round_number=self.encounter.round_number,
        )
        self.assertEqual(action.maneuver, CombatManeuver.FLEE)

    def test_flee_fails_when_not_in_combat(self) -> None:
        loner = CharacterFactory(db_key="lonerchar")
        CharacterSheetFactory(character=loner)
        result = FleeAction().run(loner)
        self.assertFalse(result.success)


class CoverInterposeActionTest(CombatManeuverActionTestBase):
    def _ally_participant(self) -> CombatParticipant:
        ally_sheet = CharacterSheetFactory(character=CharacterFactory(db_key="allychar"))
        return CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=ally_sheet,
            status=ParticipantStatus.ACTIVE,
        )

    def test_cover_declares_cover_for_ally(self) -> None:
        ally = self._ally_participant()
        result = CoverAction().run(self.character, ally_participant_id=ally.pk)
        self.assertTrue(result.success, result.message)
        action = CombatRoundAction.objects.get(participant=self.participant, round_number=1)
        self.assertEqual(action.maneuver, CombatManeuver.COVER)
        self.assertEqual(action.focused_ally_target_id, ally.pk)

    def test_cover_without_ally_fails(self) -> None:
        result = CoverAction().run(self.character)
        self.assertFalse(result.success)

    def test_cover_foreign_ally_fails(self) -> None:
        other_enc = CombatEncounterFactory(status=EncounterStatus.DECLARING, round_number=1)
        foreign = CombatParticipantFactory(
            encounter=other_enc,
            character_sheet=CharacterSheetFactory(character=CharacterFactory(db_key="foreign")),
            status=ParticipantStatus.ACTIVE,
        )
        result = CoverAction().run(self.character, ally_participant_id=foreign.pk)
        self.assertFalse(result.success)

    def test_interpose_without_ally_guards_any(self) -> None:
        result = InterposeAction().run(self.character)
        self.assertTrue(result.success, result.message)
        action = CombatRoundAction.objects.get(participant=self.participant, round_number=1)
        self.assertEqual(action.maneuver, CombatManeuver.INTERPOSE)
        self.assertIsNone(action.focused_ally_target_id)


class ReadyActionTest(CombatManeuverActionTestBase):
    def test_ready_toggles_declared_action(self) -> None:
        declare_flee(self.participant)  # creates a round action with is_ready=True
        result = ReadyAction().run(self.character)
        self.assertTrue(result.success, result.message)
        action = CombatRoundAction.objects.get(participant=self.participant, round_number=1)
        self.assertFalse(action.is_ready)
        ReadyAction().run(self.character)
        action.refresh_from_db()
        self.assertTrue(action.is_ready)

    def test_ready_without_declared_action_fails(self) -> None:
        result = ReadyAction().run(self.character)
        self.assertFalse(result.success)


class ComboActionTest(CombatManeuverActionTestBase):
    def test_combo_unknown_id_fails(self) -> None:
        declare_flee(self.participant)
        result = UpgradeComboAction().run(self.character, combo_id=999999)
        self.assertFalse(result.success)

    def test_combo_without_declared_action_fails(self) -> None:
        result = UpgradeComboAction().run(self.character, combo_id=1)
        self.assertFalse(result.success)

    def test_revert_is_idempotent_with_no_combo(self) -> None:
        declare_flee(self.participant)  # no combo upgrade present
        result = RevertComboAction().run(self.character)
        self.assertTrue(result.success, result.message)
        action = CombatRoundAction.objects.get(participant=self.participant, round_number=1)
        self.assertIsNone(action.combo_upgrade_id)

    def test_revert_without_declared_action_fails(self) -> None:
        result = RevertComboAction().run(self.character)
        self.assertFalse(result.success)


class JoinLeaveActionTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.encounter = CombatEncounterFactory(
            encounter_type=EncounterType.OPEN_ENCOUNTER,
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        cls.character = CharacterFactory(db_key="joinerchar")
        cls.sheet = CharacterSheetFactory(character=cls.character)

    def test_join_adds_active_participant(self) -> None:
        result = JoinEncounterAction().run(self.character, encounter_id=self.encounter.pk)
        self.assertTrue(result.success, result.message)
        self.assertTrue(
            CombatParticipant.objects.filter(
                encounter=self.encounter,
                character_sheet=self.sheet,
                status=ParticipantStatus.ACTIVE,
            ).exists()
        )

    def test_double_join_fails(self) -> None:
        JoinEncounterAction().run(self.character, encounter_id=self.encounter.pk)
        result = JoinEncounterAction().run(self.character, encounter_id=self.encounter.pk)
        self.assertFalse(result.success)

    def test_join_no_encounter_here_fails(self) -> None:
        result = JoinEncounterAction().run(self.character)  # no id, no room encounter
        self.assertFalse(result.success)

    def test_leave_between_rounds_removes_participant(self) -> None:
        between = CombatEncounterFactory(
            encounter_type=EncounterType.OPEN_ENCOUNTER,
            status=EncounterStatus.BETWEEN_ROUNDS,
            round_number=1,
        )
        leaver = CharacterFactory(db_key="leaverchar")
        leaver_sheet = CharacterSheetFactory(character=leaver)
        CombatParticipantFactory(
            encounter=between,
            character_sheet=leaver_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        # A second participant so the encounter isn't abandoned out from under the assert.
        CombatParticipantFactory(
            encounter=between,
            character_sheet=CharacterSheetFactory(character=CharacterFactory(db_key="stayer")),
            status=ParticipantStatus.ACTIVE,
        )
        result = LeaveEncounterAction().run(leaver)
        self.assertTrue(result.success, result.message)
        self.assertFalse(
            CombatParticipant.objects.filter(
                encounter=between,
                character_sheet=leaver_sheet,
                status=ParticipantStatus.ACTIVE,
            ).exists()
        )

    def test_leave_while_declaring_fails(self) -> None:
        declaring = CombatEncounterFactory(
            encounter_type=EncounterType.OPEN_ENCOUNTER,
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        mover = CharacterFactory(db_key="moverchar")
        mover_sheet = CharacterSheetFactory(character=mover)
        CombatParticipantFactory(
            encounter=declaring,
            character_sheet=mover_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        result = LeaveEncounterAction().run(mover)
        self.assertFalse(result.success)
