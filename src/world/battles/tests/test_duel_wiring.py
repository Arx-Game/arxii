"""Tests for the Champion duel outcome trigger wiring (#1710)."""

from django.test import TestCase
from evennia import create_object

from flows.events.payloads import EncounterCompletedPayload
from world.battles.constants import BattleSideRole, BattleUnitStatus
from world.battles.duel_wiring import (
    apply_champion_duel_outcome,
    install_champion_duel_trigger,
    wire_champion_duel_trigger,
)
from world.battles.factories import (
    BattleFactory,
    BattleParticipantFactory,
    BattlePlaceFactory,
    BattleSideFactory,
    BattleUnitFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.duels import create_lethal_duel, resolve_duel_end
from world.combat.factories import ThreatPoolFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import CovenantFactory
from world.military.factories import MilitaryUnitFactory


class ChampionDuelOutcomeWiringTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pc_sheet = CharacterSheetFactory()
        cls.threat_pool = ThreatPoolFactory()

    def setUp(self):
        wire_champion_duel_trigger()
        self.room = create_object("typeclasses.rooms.Room", key="Duel Wiring Room", nohome=True)
        self.battle = BattleFactory()
        self.battle.scene.location = self.room
        self.battle.scene.save(update_fields=["location"])
        self.covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        self.challenger_side = BattleSideFactory(
            battle=self.battle, role=BattleSideRole.ATTACKER, covenant=self.covenant
        )
        self.enemy_side = BattleSideFactory(battle=self.battle, role=BattleSideRole.DEFENDER)
        self.place = BattlePlaceFactory(battle=self.battle)
        self.enemy_unit = BattleUnitFactory(
            battle=self.battle,
            side=self.enemy_side,
            place=self.place,
            military_unit=MilitaryUnitFactory(strength=100),
        )
        # The challenger's own BattleParticipant row — apply_champion_duel_outcome
        # resolves the winner's side by looking up a BattleParticipant matching
        # encounter.duel_winner_id, so this must exist for the victory branch to fire.
        self.challenger_participant = BattleParticipantFactory(
            battle=self.battle,
            side=self.challenger_side,
            character_sheet=self.pc_sheet,
            place=self.place,
        )

    def test_challenger_victory_routs_enemy_unit_at_place(self) -> None:
        enc = create_lethal_duel(
            self.pc_sheet,
            {"name": "Boss", "max_health": 1, "threat_pool": self.threat_pool},
            self.room,
        )
        self.place.combat_encounter = enc
        self.place.save(update_fields=["combat_encounter"])
        install_champion_duel_trigger(enc)
        # Test runs inside one wrapping transaction (Django TestCase), so the
        # on_commit-deferred cache reset in TriggerHandler.invalidate() never
        # fires. create_lethal_duel's own room activity (moving the mirror/
        # opponent surfaces into the room) already populated this room's
        # trigger_handler cache before the trigger above was installed, so a
        # synchronous refresh() is needed to see it within this transaction —
        # the same same-transaction-visibility pattern documented on
        # world.combat.services._refresh_participant_trigger_handlers.
        self.room.trigger_handler.refresh()

        # Defeat the opponent to trigger VICTORY via the real resolution path.
        from world.combat.constants import OpponentStatus
        from world.combat.models import CombatOpponent

        opponent = CombatOpponent.objects.get(encounter=enc)
        opponent.status = OpponentStatus.DEFEATED
        opponent.save(update_fields=["status"])
        resolve_duel_end(enc)

        self.enemy_unit.refresh_from_db()
        self.assertIn(self.enemy_unit.status, (BattleUnitStatus.ROUTED, BattleUnitStatus.DESTROYED))
        self.challenger_side.refresh_from_db()
        self.assertGreater(self.challenger_side.victory_points, 0)

    def test_champion_defeat_routs_own_unit_at_place(self) -> None:
        """Boss wins (challenger is None): the CHALLENGER'S OWN unit is routed.

        Mirrors the victory test above, but knocks out the PC's own character
        (instead of defeating the opponent) so ``resolve_duel_end`` takes the
        ``winner_sheet=None`` / ``EncounterOutcome.DEFEAT`` branch, and asserts
        the challenger's own side's unit at the place -- not the enemy's -- is
        the one routed/destroyed (#1710 Finding 3).
        """
        from world.vitals.constants import CharacterLifeState
        from world.vitals.factories import CharacterVitalsFactory

        challenger_unit = BattleUnitFactory(
            battle=self.battle,
            side=self.challenger_side,
            place=self.place,
            military_unit=MilitaryUnitFactory(strength=100),
        )

        enc = create_lethal_duel(
            self.pc_sheet,
            {"name": "Boss", "max_health": 1, "threat_pool": self.threat_pool},
            self.room,
        )
        self.place.combat_encounter = enc
        self.place.save(update_fields=["combat_encounter"])
        install_champion_duel_trigger(enc)
        self.room.trigger_handler.refresh()

        # Down the PC (not the opponent) so resolve_duel_end takes the DEFEAT
        # branch (winner_sheet=None) via the real resolution path.
        CharacterVitalsFactory(character_sheet=self.pc_sheet, life_state=CharacterLifeState.DEAD)
        resolve_duel_end(enc)

        challenger_unit.refresh_from_db()
        self.assertIn(challenger_unit.status, (BattleUnitStatus.ROUTED, BattleUnitStatus.DESTROYED))
        # The enemy's unit at this place must be untouched by the defeat branch.
        self.enemy_unit.refresh_from_db()
        self.assertEqual(self.enemy_unit.status, BattleUnitStatus.ACTIVE)
        self.challenger_side.refresh_from_db()
        self.assertEqual(self.challenger_side.victory_points, 0)

    def test_challenger_victory_destroys_already_weak_enemy_unit(self) -> None:
        """Preserves the existing severity rule: a unit already at/below
        ROUTED_STRENGTH_THRESHOLD is wiped out by a champion's defeat, not merely
        routed (#1712 — this exact branch had no prior test coverage)."""
        from world.battles.constants import ROUTED_STRENGTH_THRESHOLD

        self.enemy_unit.military_unit.strength = ROUTED_STRENGTH_THRESHOLD
        self.enemy_unit.military_unit.save(update_fields=["strength"])

        enc = create_lethal_duel(
            self.pc_sheet,
            {"name": "Boss", "max_health": 1, "threat_pool": self.threat_pool},
            self.room,
        )
        self.place.combat_encounter = enc
        self.place.save(update_fields=["combat_encounter"])
        install_champion_duel_trigger(enc)
        self.room.trigger_handler.refresh()

        from world.combat.constants import OpponentStatus
        from world.combat.models import CombatOpponent

        opponent = CombatOpponent.objects.get(encounter=enc)
        opponent.status = OpponentStatus.DEFEATED
        opponent.save(update_fields=["status"])
        resolve_duel_end(enc)

        self.enemy_unit.refresh_from_db()
        self.assertEqual(self.enemy_unit.status, BattleUnitStatus.DESTROYED)
        self.assertEqual(self.enemy_unit.strength, 0)
        self.assertEqual(self.enemy_unit.morale, 0)

    def test_apply_champion_duel_outcome_noop_when_not_battle_bound(self) -> None:
        enc = create_lethal_duel(
            self.pc_sheet,
            {"name": "Random Mook", "max_health": 1, "threat_pool": self.threat_pool},
            self.room,
        )
        # Not bound to any BattlePlace — handler must no-op without raising.
        payload = EncounterCompletedPayload(
            encounter=enc, outcome="victory", scene=enc.scene, room=self.room
        )
        apply_champion_duel_outcome(payload=payload)  # must not raise
