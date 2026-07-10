"""Tests for the general party-encounter outcome trigger wiring (#2008)."""

from django.test import TestCase
from evennia import create_object

from flows.events.payloads import EncounterCompletedPayload
from world.battles.constants import BattleSideRole, BattleUnitStatus
from world.battles.factories import (
    BattleFactory,
    BattleParticipantFactory,
    BattlePlaceFactory,
    BattleSideFactory,
    BattleUnitFactory,
)
from world.battles.place_encounter_wiring import (
    PLACE_ENCOUNTER_VP_BONUS,
    apply_place_encounter_outcome,
    install_place_encounter_trigger,
    wire_place_encounter_trigger,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import EncounterOutcome, EncounterType, RiskLevel
from world.combat.models import CombatEncounter
from world.combat.services import complete_encounter, join_encounter
from world.scenes.constants import RoundStatus


class PlaceEncounterOutcomeWiringTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pc_sheet = CharacterSheetFactory()

    def setUp(self):
        wire_place_encounter_trigger()
        self.room = create_object(
            "typeclasses.rooms.Room", key="Place Encounter Wiring Room", nohome=True
        )
        self.battle = BattleFactory()
        self.battle.scene.location = self.room
        self.battle.scene.save(update_fields=["location"])
        self.pc_side = BattleSideFactory(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.enemy_side = BattleSideFactory(battle=self.battle, role=BattleSideRole.DEFENDER)
        self.place = BattlePlaceFactory(battle=self.battle)
        self.enemy_unit = BattleUnitFactory(
            battle=self.battle, side=self.enemy_side, place=self.place, strength=100
        )
        self.pc_unit = BattleUnitFactory(
            battle=self.battle, side=self.pc_side, place=self.place, strength=100
        )
        self.participant = BattleParticipantFactory(
            battle=self.battle,
            side=self.pc_side,
            character_sheet=self.pc_sheet,
            place=self.place,
        )

    def _open_bound_encounter(self) -> CombatEncounter:
        enc = CombatEncounter.objects.create(
            room=self.room,
            scene=self.battle.scene,
            encounter_type=EncounterType.PARTY_COMBAT,
            risk_level=RiskLevel.LETHAL,
            status=RoundStatus.DECLARING,
        )
        self.place.combat_encounter = enc
        self.place.save(update_fields=["combat_encounter"])
        install_place_encounter_trigger(enc)
        # Same-transaction trigger-cache visibility as the champion-duel tests
        # (world.battles.tests.test_duel_wiring) — see that file's comment for why.
        self.room.trigger_handler.refresh()
        return enc

    def test_victory_awards_vp_and_routs_enemy_side(self) -> None:
        enc = self._open_bound_encounter()
        join_encounter(enc, self.pc_sheet)

        complete_encounter(enc, outcome=EncounterOutcome.VICTORY)

        self.enemy_unit.refresh_from_db()
        self.assertIn(self.enemy_unit.status, (BattleUnitStatus.ROUTED, BattleUnitStatus.DESTROYED))
        self.pc_unit.refresh_from_db()
        self.assertEqual(self.pc_unit.status, BattleUnitStatus.ACTIVE)
        self.pc_side.refresh_from_db()
        self.assertEqual(self.pc_side.victory_points, PLACE_ENCOUNTER_VP_BONUS)

    def test_defeat_routs_own_side(self) -> None:
        enc = self._open_bound_encounter()
        join_encounter(enc, self.pc_sheet)

        complete_encounter(enc, outcome=EncounterOutcome.DEFEAT)

        self.pc_unit.refresh_from_db()
        self.assertIn(self.pc_unit.status, (BattleUnitStatus.ROUTED, BattleUnitStatus.DESTROYED))
        self.enemy_unit.refresh_from_db()
        self.assertEqual(self.enemy_unit.status, BattleUnitStatus.ACTIVE)
        self.pc_side.refresh_from_db()
        self.assertEqual(self.pc_side.victory_points, 0)

    def test_fled_has_no_mechanical_effect(self) -> None:
        enc = self._open_bound_encounter()
        join_encounter(enc, self.pc_sheet)

        complete_encounter(enc, outcome=EncounterOutcome.FLED)

        self.pc_unit.refresh_from_db()
        self.enemy_unit.refresh_from_db()
        self.assertEqual(self.pc_unit.status, BattleUnitStatus.ACTIVE)
        self.assertEqual(self.enemy_unit.status, BattleUnitStatus.ACTIVE)
        self.pc_side.refresh_from_db()
        self.assertEqual(self.pc_side.victory_points, 0)

    def test_tied_pc_sides_has_no_mechanical_effect(self) -> None:
        enemy_sheet = CharacterSheetFactory()
        BattleParticipantFactory(
            battle=self.battle,
            side=self.enemy_side,
            character_sheet=enemy_sheet,
            place=self.place,
        )
        enc = self._open_bound_encounter()
        join_encounter(enc, self.pc_sheet)
        join_encounter(enc, enemy_sheet)

        complete_encounter(enc, outcome=EncounterOutcome.VICTORY)

        self.pc_unit.refresh_from_db()
        self.enemy_unit.refresh_from_db()
        self.assertEqual(self.pc_unit.status, BattleUnitStatus.ACTIVE)
        self.assertEqual(self.enemy_unit.status, BattleUnitStatus.ACTIVE)
        self.pc_side.refresh_from_db()
        self.enemy_side.refresh_from_db()
        self.assertEqual(self.pc_side.victory_points, 0)
        self.assertEqual(self.enemy_side.victory_points, 0)

    def test_noop_when_not_battle_bound(self) -> None:
        enc = CombatEncounter.objects.create(
            room=self.room,
            scene=self.battle.scene,
            encounter_type=EncounterType.PARTY_COMBAT,
            risk_level=RiskLevel.LETHAL,
            status=RoundStatus.DECLARING,
        )
        # Not bound to any BattlePlace — handler must no-op without raising.
        payload = EncounterCompletedPayload(
            encounter=enc, outcome=EncounterOutcome.VICTORY, scene=enc.scene, room=self.room
        )
        apply_place_encounter_outcome(payload=payload)  # must not raise
