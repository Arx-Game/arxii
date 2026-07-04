"""E2E journey: the ship system end-to-end (#1832 Task 11).

Commission a ship over telnet -> complete construction -> upgrade handling over
telnet -> complete the upgrade -> install a sanctum + weave a level-3 SANCTUM
thread on the ship's deck room -> materialize the ship into a Battle alongside
an enemy ship -> REPOSITION to close the gap -> BREACH the enemy hull until it
sinks (occupants ejected) -> conclude the battle with the covenant's own hull
also breached -> assert the persistent ``needs_repair`` writeback fires.

Mirrors ``world/battles/tests/test_vehicle_journey.py`` for the battle half and
``integration_tests/pipeline/test_persona_telnet_e2e.py`` for the real (not
mocked) telnet-dispatch half. The sanctum leg reuses the same direct
``SanctumDetails``/``ThreadFactory`` construction as
``world/ships/tests/test_sanctum_bonus.py`` / ``test_battle_bridge.py`` — a
ship has at most one sanctum room for MVP, installed the same way in both
places.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models

from actions.factories import ActionTemplateFactory
from commands.ships import CmdShip
from world.battles.constants import (
    BattleActionKind,
    BattleActionScope,
    BattleOutcome,
    BattleSideRole,
    FortificationKind,
    VehicleKind,
)
from world.battles.factories import BattleFactory, BattleParticipantFactory, BattleSideFactory
from world.battles.resolution import resolve_battle_round
from world.battles.services import (
    begin_battle_round,
    conclude_battle,
    create_battle_vehicle,
    declare_battle_action,
    places_overlap,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ensure_drowning_damage_type
from world.conditions.models import CapabilityType
from world.magic.constants import SanctumSlotKind, TargetKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadFactory,
)
from world.magic.models import SanctumDetails, SanctumOwnerMode
from world.mechanics.factories import PropertyFactory
from world.projects.constants import ProjectKind
from world.projects.services import get_kind_handler
from world.room_features.factories import RoomFeatureInstanceFactory
from world.ships.battle_bridge import materialize_ship_as_battle_vehicle
from world.ships.constants import HANDLING_PER_LEVEL, SPEED_CAPABILITY_NAME
from world.ships.factories import ShipTypeFactory
from world.ships.models import ShipConstructionDetails, ShipDetails, ShipUpgradeDetails
from world.vitals.factories import CharacterVitalsFactory


def _mock_check(success_level: int) -> MagicMock:
    """Mirrors test_vehicle_journey.py's helper exactly."""
    result = MagicMock()
    result.success_level = success_level
    return result


def _ship_cmd(character, args: str) -> CmdShip:
    """Build a real ``CmdShip`` wired to *character*, mirroring
    ``integration_tests/pipeline/test_persona_telnet_e2e.py``'s ``_cmd`` helper —
    a real telnet dispatch, not a mocked one."""
    cmd = CmdShip()
    cmd.caller = character
    cmd.args = args
    cmd.raw_string = f"ship {args}"
    cmd.cmdname = "ship"
    return cmd


class ShipJourneyE2ETests(TestCase):
    def test_commission_upgrade_sanctum_battle_sink_and_repair(self) -> None:  # noqa: PLR0915
        # Flush the SharedMemoryModel identity-map cache to prevent PK-recycling
        # flakiness from prior tests (see project memory / test_persona_telnet_e2e.py).
        idmapper_models.flush_cache()

        sheet = CharacterSheetFactory()
        captain = sheet.character
        captain.msg = MagicMock()
        ShipTypeFactory(
            name="Sloop",
            base_hull=8,
            base_handling=15,
            base_armament=5,
            base_crew_capacity=8,
            base_cargo_capacity=10,
        )

        # -- Step 1: commission via real telnet dispatch -----------------------
        _ship_cmd(captain, "commission ship_type=Sloop name=The Black Pearl").func()

        construction = ShipConstructionDetails.objects.select_related("project").get(
            name="The Black Pearl"
        )
        construction_handler = get_kind_handler(ProjectKind.SHIP_CONSTRUCTION)
        ship = construction_handler(construction.project, None)

        self.assertIsInstance(ship, ShipDetails)
        self.assertEqual(ship.ship_type.name, "Sloop")
        self.assertEqual(ship.building.owner_persona_id, sheet.primary_persona.pk)
        deck_room = ship.building.entry_room
        self.assertIsNotNone(deck_room)
        self.assertEqual(deck_room.objectdb.db_key, "Main Deck")
        self.assertIn("The Black Pearl", ship.building.area.name)

        # Stand the captain aboard the new ship — upgrade/status ops resolve
        # their target ship from the actor's current room when no ship_id is given.
        captain.location = deck_room.objectdb

        # -- Step 2: upgrade handling via real telnet dispatch ------------------
        _ship_cmd(captain, "upgrade stat=handling level=2").func()

        upgrade_details = ShipUpgradeDetails.objects.select_related("project").get(
            ship=ship, stat="handling"
        )
        upgrade_handler = get_kind_handler(ProjectKind.SHIP_UPGRADE)
        upgrade_handler(upgrade_details.project, None)

        ship.refresh_from_db()
        self.assertEqual(ship.handling_level, 2)

        # Battle technique resolution evaluates the caster's real-world room's
        # resonance environment (world.magic.services.resonance_environment);
        # the ship's deck room carries a real Area, which is irrelevant to the
        # battle leg below — clear the captain's location so casting during the
        # battle doesn't pull in that (unrelated) evaluation path.
        captain.location = None

        # -- Step 3: install a sanctum + weave a level-3 SANCTUM thread ----------
        feature_instance = RoomFeatureInstanceFactory(room_profile=deck_room)
        sanctum = SanctumDetails.objects.create(
            feature_instance=feature_instance,
            resonance_type=ResonanceFactory(),
            owner_mode=SanctumOwnerMode.PERSONAL,
            founder_character_sheet=sheet,
        )
        sanctum_resonance = ResonanceFactory()
        ThreadFactory(
            owner=sheet,
            target_kind=TargetKind.SANCTUM,
            target_trait=None,
            target_sanctum_details=sanctum,
            slot_kind=SanctumSlotKind.PERSONAL_OWN,
            resonance=sanctum_resonance,
            level=3,
        )

        # -- Step 4: materialize the ship (+ an enemy ship) into a Battle -------
        battle = BattleFactory(round_limit=20)
        covenant_side = BattleSideFactory(battle=battle, role=BattleSideRole.ATTACKER)
        enemy_side = BattleSideFactory(battle=battle, role=BattleSideRole.DEFENDER)

        covenant_vehicle = materialize_ship_as_battle_vehicle(
            ship=ship, battle=battle, side=covenant_side, place_name="The Black Pearl"
        )
        enemy_vehicle = create_battle_vehicle(
            battle=battle,
            side=enemy_side,
            place_name="The Iron Gull",
            vehicle_kind=VehicleKind.SHIP,
        )

        # Speed capability reflects effective_handling() (base 15 + 2 upgrade
        # levels * HANDLING_PER_LEVEL) plus the level-3 sanctum bonus (+3).
        expected_handling = ship.ship_type.base_handling + ship.handling_level * HANDLING_PER_LEVEL
        self.assertEqual(ship.effective_handling(), expected_handling)
        speed = CapabilityType.objects.get(name=SPEED_CAPABILITY_NAME)
        self.assertEqual(
            covenant_vehicle.unit.effective_capability(speed),
            ship.effective_handling() + 3,
        )

        technique = TechniqueFactory(action_template=ActionTemplateFactory())

        captain_participant = BattleParticipantFactory(
            battle=battle,
            side=covenant_side,
            character_sheet=sheet,
            place=covenant_vehicle.place,
        )
        covenant_vehicle.unit.commander = sheet
        covenant_vehicle.unit.save(update_fields=["commander"])
        CharacterTechniqueFactory(character=sheet, technique=technique)
        CharacterAnimaFactory(character=captain, current=30, maximum=30)

        gunner = BattleParticipantFactory(
            battle=battle,
            side=covenant_side,
            place=covenant_vehicle.place,
        )
        CharacterTechniqueFactory(character=gunner.character_sheet, technique=technique)
        CharacterAnimaFactory(character=gunner.character_sheet.character, current=30, maximum=30)

        non_swimmer = BattleParticipantFactory(
            battle=battle,
            side=enemy_side,
            place=enemy_vehicle.place,
        )
        CharacterVitalsFactory(
            character_sheet=non_swimmer.character_sheet, health=100, max_health=100
        )
        PropertyFactory(name="aquatic")

        enemy_vehicle.place.x = Decimal(0)
        enemy_vehicle.place.y = Decimal(0)
        enemy_vehicle.place.footprint_radius = Decimal(5)
        enemy_vehicle.place.save(update_fields=["x", "y", "footprint_radius"])
        covenant_vehicle.place.x = Decimal(50)
        covenant_vehicle.place.y = Decimal(0)
        covenant_vehicle.place.footprint_radius = Decimal(5)
        covenant_vehicle.place.save(update_fields=["x", "y", "footprint_radius"])

        self.assertFalse(places_overlap(covenant_vehicle.place, enemy_vehicle.place))

        # -- Step 5a: REPOSITION to overlap --------------------------------------
        while not places_overlap(covenant_vehicle.place, enemy_vehicle.place):
            battle_round = begin_battle_round(battle=battle)
            declare_battle_action(
                participant=captain_participant,
                action_kind=BattleActionKind.REPOSITION,
                technique=technique,
                scope=BattleActionScope.PLACE,
                target_place=covenant_vehicle.place,
                reposition_dx=Decimal(-50),
                reposition_dy=Decimal(0),
            )
            with patch("world.battles.resolution.perform_check", return_value=_mock_check(2)):
                resolve_battle_round(battle_round=battle_round)
            covenant_vehicle.place.refresh_from_db()

        # -- Step 5b: BREACH the enemy hull until it sinks -----------------------
        enemy_hull = enemy_vehicle.place.fortifications.get(kind=FortificationKind.HULL)
        while not enemy_hull.breached:
            battle_round = begin_battle_round(battle=battle)
            declare_battle_action(
                participant=gunner,
                action_kind=BattleActionKind.BREACH,
                technique=technique,
                target_fortification=enemy_hull,
            )
            with patch("world.battles.resolution.perform_check", return_value=_mock_check(2)):
                resolve_battle_round(battle_round=battle_round)
            enemy_hull.refresh_from_db()

        self.assertTrue(enemy_hull.breached)

        # Ejection consequence ran: the non-swimmer's place is cleared and they
        # took real drowning damage.
        non_swimmer.refresh_from_db()
        self.assertIsNone(non_swimmer.place)
        self.assertLess(non_swimmer.character_sheet.vitals.health, 100)
        self.assertEqual(ensure_drowning_damage_type().name, "Drowning")

        # -- Step 6: conclude the battle with the covenant's OWN hull breached ---
        # too — exercises the SHIP_REPAIR writeback gate (Task 7's registered
        # battle-conclusion hook). The hook registry is production-registered at
        # world.ships.apps.ready() and is NOT reset here (Task 7 fix — the
        # registry survives test isolation); this relies on that directly.
        covenant_hull = covenant_vehicle.place.fortifications.get(kind=FortificationKind.HULL)
        covenant_hull.breached = True
        covenant_hull.save(update_fields=["breached"])

        conclude_battle(battle=battle, outcome=BattleOutcome.ATTACKER_DECISIVE)

        ship.refresh_from_db()
        self.assertTrue(ship.needs_repair)
