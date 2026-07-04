"""E2E siege journeys (#1713): breach-to-victory, hold-the-walls, and the
persistent fortification-investment path from Project funding through to a
Fortification's snapshotted integrity."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from actions.factories import ActionTemplateFactory
from world.battles.constants import (
    BASE_INTEGRITY,
    FORTIFICATION_LEVEL_INTEGRITY_BONUS,
    BattleActionKind,
    BattleActionScope,
    BattleOutcome,
    BattleSideRole,
    FortificationKind,
    VehicleKind,
)
from world.battles.exceptions import (
    FortificationOwnershipMismatchError,
    NotVehicleCommanderError,
    PlacesDoNotOverlapError,
)
from world.battles.factories import (
    BattleFactory,
    BattleParticipantFactory,
    BattlePlaceFactory,
    BattleSideFactory,
)
from world.battles.models import BattleUnitCapability
from world.battles.resolution import resolve_battle_round
from world.battles.services import (
    begin_battle_round,
    create_battle_vehicle,
    create_fortification,
    declare_battle_action,
    maybe_conclude_on_timer,
)
from world.buildings.factories import BuildingFactory, FortificationUpgradeDetailsFactory
from world.buildings.fortification_services import complete_fortification_upgrade
from world.conditions.factories import CapabilityTypeFactory
from world.magic.factories import CharacterAnimaFactory, CharacterTechniqueFactory, TechniqueFactory
from world.projects.factories import ProjectFactory
from world.scenes.constants import RoundStatus


def _mock_check(success_level: int) -> MagicMock:
    """Mirrors test_actions.py's ResolveBattleRoundActionTests._mock_check exactly."""
    result = MagicMock()
    result.success_level = success_level
    return result


class SiegeBreachJourneyTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory(round_limit=10)
        self.attacker_side = BattleSideFactory(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender_side = BattleSideFactory(battle=self.battle, role=BattleSideRole.DEFENDER)
        self.place = BattlePlaceFactory(battle=self.battle)
        # Low integrity so 2 rounds of success_level=2 (2*BREACH_INTEGRITY_PER_LEVEL=20
        # damage/round) breaches it — no need to grind through a full-ceiling siege here.
        self.fort = create_fortification(place=self.place, defending_side=self.defender_side)
        self.fort.integrity = 30
        self.fort.max_integrity = 30
        self.fort.save(update_fields=["integrity", "max_integrity"])

        self.technique = TechniqueFactory(action_template=ActionTemplateFactory())
        self.attacker = BattleParticipantFactory(battle=self.battle, side=self.attacker_side)
        self.defender = BattleParticipantFactory(battle=self.battle, side=self.defender_side)
        CharacterTechniqueFactory(character=self.attacker.character_sheet, technique=self.technique)
        CharacterTechniqueFactory(character=self.defender.character_sheet, technique=self.technique)
        CharacterAnimaFactory(
            character=self.attacker.character_sheet.character, current=30, maximum=30
        )
        CharacterAnimaFactory(
            character=self.defender.character_sheet.character, current=30, maximum=30
        )

    def test_breach_own_fortification_is_rejected(self):
        """Sanity-check the ownership guard end-to-end (not just Task 3's direct unit
        test) before asserting the happy path below."""
        begin_battle_round(battle=self.battle)
        with self.assertRaises(FortificationOwnershipMismatchError):
            declare_battle_action(
                participant=self.defender,
                action_kind=BattleActionKind.BREACH,
                technique=self.technique,
                target_fortification=self.fort,
            )

    def test_repeated_breach_grinds_integrity_to_zero_and_awards_vp(self):
        from world.battles.resolution import resolve_battle_round

        for _ in range(self.battle.round_limit):
            self.fort.refresh_from_db()
            if self.fort.breached:
                break
            battle_round = begin_battle_round(battle=self.battle)
            declare_battle_action(
                participant=self.attacker,
                action_kind=BattleActionKind.BREACH,
                technique=self.technique,
                target_fortification=self.fort,
            )
            with patch("world.battles.resolution.perform_check", return_value=_mock_check(2)):
                resolve_battle_round(battle_round=battle_round)

        self.fort.refresh_from_db()
        self.assertTrue(self.fort.breached)
        self.assertEqual(self.fort.integrity, 0)
        self.attacker_side.refresh_from_db()
        self.assertGreater(self.attacker_side.victory_points, 0)


class HoldTheWallsJourneyTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory(round_limit=2)
        self.attacker_side = BattleSideFactory(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender_side = BattleSideFactory(battle=self.battle, role=BattleSideRole.DEFENDER)
        self.place = BattlePlaceFactory(battle=self.battle)
        self.fort = create_fortification(place=self.place, defending_side=self.defender_side)

    def test_defender_wins_by_timeout_default_when_undefeated(self):
        # No BREACH ever declared — the Fortification is untouched. Mirrors
        # MaybeConcludeOnTimerTests._exhaust_rounds exactly: advance and complete
        # round_limit rounds with no declarations at all, then let the EXISTING,
        # unchanged maybe_conclude_on_timer default resolve the battle. Proves
        # "hold-the-walls" needs zero siege-specific win-condition code.
        for _ in range(self.battle.round_limit):
            battle_round = begin_battle_round(battle=self.battle)
            battle_round.status = RoundStatus.COMPLETED
            battle_round.completed_at = timezone.now()
            battle_round.save()

        result = maybe_conclude_on_timer(battle=self.battle)

        self.assertEqual(result, BattleOutcome.DEFENDER_MARGINAL)
        self.fort.refresh_from_db()
        self.assertFalse(self.fort.breached)
        self.battle.refresh_from_db()
        self.assertTrue(self.battle.is_concluded)


class FortificationInvestmentJourneyTests(TestCase):
    def test_funded_upgrade_raises_snapshot_integrity_for_next_siege(self):
        building = BuildingFactory(fortification_level=0)
        project = ProjectFactory()
        FortificationUpgradeDetailsFactory(project=project, building=building, target_level=3)
        complete_fortification_upgrade(project)
        building.refresh_from_db()
        self.assertEqual(building.fortification_level, 3)

        battle = BattleFactory()
        side = BattleSideFactory(battle=battle, role=BattleSideRole.DEFENDER)
        place = BattlePlaceFactory(battle=battle)
        fort = create_fortification(place=place, defending_side=side, building=building)

        expected = BASE_INTEGRITY[FortificationKind.WALL] + 3 * FORTIFICATION_LEVEL_INTEGRITY_BONUS
        self.assertEqual(fort.max_integrity, expected)

    def test_second_lower_upgrade_does_not_regress_next_siege_integrity(self):
        building = BuildingFactory(fortification_level=0)
        high_project = ProjectFactory()
        FortificationUpgradeDetailsFactory(project=high_project, building=building, target_level=4)
        complete_fortification_upgrade(high_project)

        low_project = ProjectFactory()
        FortificationUpgradeDetailsFactory(project=low_project, building=building, target_level=1)
        complete_fortification_upgrade(low_project)

        building.refresh_from_db()
        battle = BattleFactory()
        side = BattleSideFactory(battle=battle, role=BattleSideRole.DEFENDER)
        place = BattlePlaceFactory(battle=battle)
        fort = create_fortification(place=place, defending_side=side, building=building)

        expected = BASE_INTEGRITY[FortificationKind.WALL] + 4 * FORTIFICATION_LEVEL_INTEGRITY_BONUS
        self.assertEqual(fort.max_integrity, expected)


class RepositionDeclarationTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory(round_limit=10)
        self.side = BattleSideFactory(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.vehicle = create_battle_vehicle(
            battle=self.battle,
            side=self.side,
            place_name="The Gull",
            vehicle_kind=VehicleKind.SHIP,
        )
        self.technique = TechniqueFactory(action_template=ActionTemplateFactory())
        self.participant = BattleParticipantFactory(battle=self.battle, side=self.side)
        CharacterTechniqueFactory(
            character=self.participant.character_sheet, technique=self.technique
        )
        CharacterAnimaFactory(
            character=self.participant.character_sheet.character, current=30, maximum=30
        )

    def test_commander_can_declare_reposition(self):
        self.vehicle.unit.commander = self.participant.character_sheet
        self.vehicle.unit.save(update_fields=["commander"])
        begin_battle_round(battle=self.battle)

        declaration = declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.REPOSITION,
            technique=self.technique,
            scope=BattleActionScope.PLACE,
            target_place=self.vehicle.place,
        )

        self.assertEqual(declaration.action_kind, BattleActionKind.REPOSITION)

    def test_non_commander_cannot_declare_reposition(self):
        begin_battle_round(battle=self.battle)

        with self.assertRaises(NotVehicleCommanderError):
            declare_battle_action(
                participant=self.participant,
                action_kind=BattleActionKind.REPOSITION,
                technique=self.technique,
                scope=BattleActionScope.PLACE,
                target_place=self.vehicle.place,
            )


class RepositionResolutionTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory(round_limit=10)
        self.side = BattleSideFactory(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.vehicle = create_battle_vehicle(
            battle=self.battle,
            side=self.side,
            place_name="The Gull",
            vehicle_kind=VehicleKind.SHIP,
        )
        speed = CapabilityTypeFactory(name="speed")
        BattleUnitCapability.objects.create(unit=self.vehicle.unit, capability=speed, value=5)
        self.technique = TechniqueFactory(action_template=ActionTemplateFactory())
        self.participant = BattleParticipantFactory(battle=self.battle, side=self.side)
        self.vehicle.unit.commander = self.participant.character_sheet
        self.vehicle.unit.save(update_fields=["commander"])
        CharacterTechniqueFactory(
            character=self.participant.character_sheet, technique=self.technique
        )
        CharacterAnimaFactory(
            character=self.participant.character_sheet.character, current=30, maximum=30
        )

    def test_moves_place_toward_declared_delta_bounded_by_speed(self):
        battle_round = begin_battle_round(battle=self.battle)
        declare_battle_action(
            participant=self.participant,
            action_kind=BattleActionKind.REPOSITION,
            technique=self.technique,
            scope=BattleActionScope.PLACE,
            target_place=self.vehicle.place,
            reposition_dx=Decimal(10),
            reposition_dy=Decimal(0),
        )
        with patch("world.battles.resolution.perform_check", return_value=_mock_check(2)):
            resolve_battle_round(battle_round=battle_round)

        self.vehicle.place.refresh_from_db()
        self.assertEqual(self.vehicle.place.x, Decimal("5.00"))


class CrossVehicleTargetingTests(TestCase):
    def setUp(self) -> None:
        self.battle = BattleFactory(round_limit=10)
        self.attacker_side = BattleSideFactory(battle=self.battle, role=BattleSideRole.ATTACKER)
        self.defender_side = BattleSideFactory(battle=self.battle, role=BattleSideRole.DEFENDER)
        self.attacker_ship = create_battle_vehicle(
            battle=self.battle,
            side=self.attacker_side,
            place_name="Attacker Ship",
            vehicle_kind=VehicleKind.SHIP,
        )
        self.defender_ship = create_battle_vehicle(
            battle=self.battle,
            side=self.defender_side,
            place_name="Defender Ship",
            vehicle_kind=VehicleKind.SHIP,
        )
        self.technique = TechniqueFactory(action_template=ActionTemplateFactory())
        self.attacker = BattleParticipantFactory(
            battle=self.battle,
            side=self.attacker_side,
            place=self.attacker_ship.place,
        )
        CharacterTechniqueFactory(character=self.attacker.character_sheet, technique=self.technique)
        CharacterAnimaFactory(
            character=self.attacker.character_sheet.character, current=30, maximum=30
        )
        self.hull = self.defender_ship.place.fortifications.get(kind=FortificationKind.HULL)

    def _set_positions(self, *, overlapping: bool) -> None:
        self.defender_ship.place.x = Decimal(0)
        self.defender_ship.place.y = Decimal(0)
        self.defender_ship.place.footprint_radius = Decimal(5)
        self.defender_ship.place.save(update_fields=["x", "y", "footprint_radius"])
        gap_x = Decimal(6) if overlapping else Decimal(100)
        self.attacker_ship.place.x = gap_x
        self.attacker_ship.place.y = Decimal(0)
        self.attacker_ship.place.footprint_radius = Decimal(5)
        self.attacker_ship.place.save(update_fields=["x", "y", "footprint_radius"])

    def test_can_breach_hull_on_overlapping_vehicle(self):
        self._set_positions(overlapping=True)
        begin_battle_round(battle=self.battle)

        declaration = declare_battle_action(
            participant=self.attacker,
            action_kind=BattleActionKind.BREACH,
            technique=self.technique,
            target_fortification=self.hull,
        )

        self.assertEqual(declaration.target_fortification, self.hull)

    def test_cannot_breach_hull_on_non_overlapping_vehicle(self):
        self._set_positions(overlapping=False)
        begin_battle_round(battle=self.battle)

        with self.assertRaises(PlacesDoNotOverlapError):
            declare_battle_action(
                participant=self.attacker,
                action_kind=BattleActionKind.BREACH,
                technique=self.technique,
                target_fortification=self.hull,
            )

    def test_can_strike_vehicles_own_unit_on_overlapping_vehicle(self):
        """A STRIKE against a vehicle's own BattleUnit (not an occupant) is gated by
        the same overlap check as BREACH-against-hull (#1714 final review, finding 1):
        BattleVehicle.unit.place is always None by design, so the check must resolve
        the unit's paired vehicle's place rather than silently no-op."""
        self._set_positions(overlapping=True)
        begin_battle_round(battle=self.battle)

        declaration = declare_battle_action(
            participant=self.attacker,
            action_kind=BattleActionKind.STRIKE,
            technique=self.technique,
            target_unit=self.defender_ship.unit,
        )

        self.assertEqual(declaration.target_unit, self.defender_ship.unit)

    def test_cannot_strike_vehicles_own_unit_on_non_overlapping_vehicle(self):
        """Mirrors test_can_strike_vehicles_own_unit_on_overlapping_vehicle: without
        overlap, a STRIKE against a distant vehicle's own unit must be rejected —
        before the finding 1 fix this silently passed because target_unit.place_id
        is always None for a vehicle's own unit."""
        self._set_positions(overlapping=False)
        begin_battle_round(battle=self.battle)

        with self.assertRaises(PlacesDoNotOverlapError):
            declare_battle_action(
                participant=self.attacker,
                action_kind=BattleActionKind.STRIKE,
                technique=self.technique,
                target_unit=self.defender_ship.unit,
            )
