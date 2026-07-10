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
    UseItemManeuverAction,
)
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    CombatManeuver,
    EncounterType,
    OpponentTier,
    PaceMode,
    ParticipantStatus,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatParticipant, CombatRoundAction
from world.combat.services import declare_flee
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals


class CombatManeuverActionTestBase(TestCase):
    """Shared fixture: a player character active in a DECLARING encounter."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory(db_key="maneuverchar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
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
        other_enc = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
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


class UseItemManeuverActionTest(CombatManeuverActionTestBase):
    """Tests for UseItemManeuverAction (#2120), key ``combat_use``."""

    def _held_item(self, key: str = "healing draught"):
        item_obj = ObjectDBFactory(db_key=key, location=self.character)
        return ItemInstanceFactory(template=ItemTemplateFactory(), game_object=item_obj)

    def test_use_item_by_id_declares_use_item_maneuver(self) -> None:
        item = self._held_item()
        result = UseItemManeuverAction().run(self.character, item_instance_id=item.pk)
        self.assertTrue(result.success, result.message)
        action = CombatRoundAction.objects.get(participant=self.participant, round_number=1)
        self.assertEqual(action.maneuver, CombatManeuver.USE_ITEM)
        self.assertEqual(action.item_instance_id, item.pk)

    def test_use_item_by_name_resolves_from_held_items(self) -> None:
        item = self._held_item(key="smoke bomb")
        result = UseItemManeuverAction().run(self.character, item_name="smoke bomb")
        self.assertTrue(result.success, result.message)
        action = CombatRoundAction.objects.get(participant=self.participant, round_number=1)
        self.assertEqual(action.item_instance_id, item.pk)

    def test_use_item_without_item_fails(self) -> None:
        result = UseItemManeuverAction().run(self.character)
        self.assertFalse(result.success)

    def test_use_item_with_ally_target(self) -> None:
        ally_sheet = CharacterSheetFactory(character=CharacterFactory(db_key="useitemally"))
        ally = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=ally_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        item = self._held_item()
        result = UseItemManeuverAction().run(
            self.character, item_instance_id=item.pk, ally_participant_id=ally.pk
        )
        self.assertTrue(result.success, result.message)
        action = CombatRoundAction.objects.get(participant=self.participant, round_number=1)
        self.assertEqual(action.focused_ally_target_id, ally.pk)

    def test_use_item_unheld_fails(self) -> None:
        loose = ItemInstanceFactory(template=ItemTemplateFactory())  # no game_object -> unheld
        result = UseItemManeuverAction().run(self.character, item_instance_id=loose.pk)
        self.assertFalse(result.success)

    def test_use_item_fails_when_not_in_combat(self) -> None:
        loner = CharacterFactory(db_key="useitemloner")
        CharacterSheetFactory(character=loner)
        result = UseItemManeuverAction().run(loner, item_name="anything")
        self.assertFalse(result.success)


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


class PaceModeReadyActionTest(TestCase):
    """ReadyAction wired to PaceMode.READY early resolution (#2120)."""

    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            pace_mode=PaceMode.READY,
            round_number=1,
        )
        CombatOpponentFactory(encounter=self.encounter, tier=OpponentTier.MOOK)
        self.first = CharacterFactory(db_key="readymodefirst")
        self.first_sheet = CharacterSheetFactory(character=self.first)
        self.first_participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.first_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        self.second = CharacterFactory(db_key="readymodesecond")
        self.second_sheet = CharacterSheetFactory(character=self.second)
        self.second_participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.second_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        for sheet in (self.first_sheet, self.second_sheet):
            CharacterVitals.objects.get_or_create(
                character_sheet=sheet, defaults={"health": 50, "max_health": 100}
            )

    def _declare_passive(self, participant, *, ready: bool) -> CombatRoundAction:
        """A passives-only declaration — resolves as a no-op at round resolution.

        Keeps these tests focused on the ready-count wiring without needing
        FleeConfig or a seeded check pipeline at resolve time.
        """
        return CombatRoundAction.objects.create(
            participant=participant,
            round_number=self.encounter.round_number,
            is_ready=ready,
        )

    def test_both_readying_resolves_without_a_timer(self) -> None:
        self._declare_passive(self.first_participant, ready=True)
        self._declare_passive(self.second_participant, ready=False)
        # Drive the wire under test: ReadyAction.execute -> toggle (False -> True)
        # -> maybe_resolve_on_ready notices every ACTIVE participant is ready.
        ReadyAction().run(self.second)

        self.encounter.refresh_from_db()
        self.assertNotEqual(self.encounter.status, RoundStatus.DECLARING)

    def test_lone_ready_participant_does_not_resolve(self) -> None:
        self._declare_passive(self.first_participant, ready=True)
        self._declare_passive(self.second_participant, ready=True)
        ReadyAction().run(self.second)  # toggle -> False; only first remains ready

        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.status, RoundStatus.DECLARING)


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
            status=RoundStatus.DECLARING,
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
            status=RoundStatus.BETWEEN_ROUNDS,
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
            status=RoundStatus.DECLARING,
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
