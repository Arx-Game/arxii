"""Regression test: champion-duel and party-encounter outcome triggers must not
cross-fire on each other's encounters (#2008 final-review Critical finding).

Both ``duel_wiring.install_champion_duel_trigger`` and
``place_encounter_wiring.install_place_encounter_trigger`` install their Trigger on
the *room* shared by every ``BattlePlace`` in a ``Battle`` (``battle.scene.location``),
and neither Trigger filters on the completed encounter's ``encounter_type``. Once a
battle has used both a champion duel at one front and a party encounter at another
front, both Triggers are present on the room for the rest of the battle's lifetime,
so *every* ``ENCOUNTER_COMPLETED`` in that room fires both handlers — regardless of
which front/encounter it actually came from. This double-fires VP awards and can rout
the wrong side. See ``apply_place_encounter_outcome`` / ``apply_champion_duel_outcome``
for the ``encounter_type`` guards that fix this.
"""

from django.test import TestCase
from evennia import create_object

from world.battles.constants import BattleSideRole, BattleUnitStatus
from world.battles.duel_wiring import (
    CHAMPION_DUEL_VP_BONUS,
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
from world.battles.place_encounter_wiring import (
    PLACE_ENCOUNTER_VP_BONUS,
    install_place_encounter_trigger,
    wire_place_encounter_trigger,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import EncounterOutcome, EncounterType, OpponentStatus, RiskLevel
from world.combat.duels import create_lethal_duel, resolve_duel_end
from world.combat.factories import ThreatPoolFactory
from world.combat.models import CombatEncounter, CombatOpponent
from world.combat.services import complete_encounter, join_encounter
from world.covenants.constants import CovenantType
from world.covenants.factories import CovenantFactory
from world.military.factories import MilitaryUnitFactory
from world.scenes.constants import RoundStatus


class OutcomeTriggerCoexistenceTests(TestCase):
    """One battle, two fronts, both outcome triggers installed on the shared room."""

    @classmethod
    def setUpTestData(cls):
        cls.duel_pc_sheet = CharacterSheetFactory()
        cls.party_pc_sheet = CharacterSheetFactory()
        cls.threat_pool = ThreatPoolFactory()

    def setUp(self):
        wire_champion_duel_trigger()
        wire_place_encounter_trigger()
        self.room = create_object(
            "typeclasses.rooms.Room", key="Coexistence Wiring Room", nohome=True
        )
        self.battle = BattleFactory()
        self.battle.scene.location = self.room
        self.battle.scene.save(update_fields=["location"])
        self.covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        self.attacker_side = BattleSideFactory(
            battle=self.battle, role=BattleSideRole.ATTACKER, covenant=self.covenant
        )
        self.defender_side = BattleSideFactory(battle=self.battle, role=BattleSideRole.DEFENDER)

        # Front 1: a champion-duel place.
        self.duel_place = BattlePlaceFactory(battle=self.battle)
        self.enemy_unit_at_duel = BattleUnitFactory(
            battle=self.battle,
            side=self.defender_side,
            place=self.duel_place,
            military_unit=MilitaryUnitFactory(strength=100),
        )
        self.challenger_participant = BattleParticipantFactory(
            battle=self.battle,
            side=self.attacker_side,
            character_sheet=self.duel_pc_sheet,
            place=self.duel_place,
        )

        # Front 2: a party-encounter place.
        self.party_place = BattlePlaceFactory(battle=self.battle)
        self.pc_unit_at_party = BattleUnitFactory(
            battle=self.battle,
            side=self.attacker_side,
            place=self.party_place,
            military_unit=MilitaryUnitFactory(strength=100),
        )
        self.enemy_unit_at_party = BattleUnitFactory(
            battle=self.battle,
            side=self.defender_side,
            place=self.party_place,
            military_unit=MilitaryUnitFactory(strength=100),
        )
        self.party_participant = BattleParticipantFactory(
            battle=self.battle,
            side=self.attacker_side,
            character_sheet=self.party_pc_sheet,
            place=self.party_place,
        )

    def test_party_and_duel_outcome_triggers_do_not_cross_fire(self) -> None:
        # Bind the party encounter to its front and install its Trigger on the room.
        party_enc = CombatEncounter.objects.create(
            room=self.room,
            scene=self.battle.scene,
            encounter_type=EncounterType.PARTY_COMBAT,
            risk_level=RiskLevel.LETHAL,
            status=RoundStatus.DECLARING,
        )
        self.party_place.combat_encounter = party_enc
        self.party_place.save(update_fields=["combat_encounter"])
        install_place_encounter_trigger(party_enc)

        # Bind the duel to its own front and install ITS Trigger on the same room —
        # both Triggers now coexist on the room, exactly as they would after a real
        # battle has used both encounter types (#2008).
        duel_enc = create_lethal_duel(
            self.duel_pc_sheet,
            {"name": "Boss", "max_health": 1, "threat_pool": self.threat_pool},
            self.room,
        )
        self.duel_place.combat_encounter = duel_enc
        self.duel_place.save(update_fields=["combat_encounter"])
        install_champion_duel_trigger(duel_enc)

        # Same-transaction trigger-cache visibility — see test_duel_wiring's comment.
        self.room.trigger_handler.refresh()

        # --- Complete the party encounter first. ---
        join_encounter(party_enc, self.party_pc_sheet)
        complete_encounter(party_enc, outcome=EncounterOutcome.VICTORY)

        self.pc_unit_at_party.refresh_from_db()
        self.enemy_unit_at_party.refresh_from_db()
        self.attacker_side.refresh_from_db()

        # The place-encounter handler correctly routs only the enemy at this front...
        self.assertIn(
            self.enemy_unit_at_party.status, (BattleUnitStatus.ROUTED, BattleUnitStatus.DESTROYED)
        )
        self.assertEqual(self.attacker_side.victory_points, PLACE_ENCOUNTER_VP_BONUS)
        # ...and the winning joiners' OWN unit must NOT be routed by the champion-duel
        # handler cross-firing on this party encounter (duel_winner_id is None here,
        # which — unguarded — sends the duel handler down its DEFEAT branch).
        self.assertEqual(self.pc_unit_at_party.status, BattleUnitStatus.ACTIVE)

        # --- Now complete the duel. ---
        opponent = CombatOpponent.objects.get(encounter=duel_enc)
        opponent.status = OpponentStatus.DEFEATED
        opponent.save(update_fields=["status"])
        resolve_duel_end(duel_enc)

        self.enemy_unit_at_duel.refresh_from_db()
        self.attacker_side.refresh_from_db()

        self.assertIn(
            self.enemy_unit_at_duel.status, (BattleUnitStatus.ROUTED, BattleUnitStatus.DESTROYED)
        )
        # Exactly one VP award from each front's own handler — the place-encounter
        # handler cross-firing on this duel (unguarded) would double-award VICTORY VP.
        self.assertEqual(
            self.attacker_side.victory_points,
            PLACE_ENCOUNTER_VP_BONUS + CHAMPION_DUEL_VP_BONUS,
        )
