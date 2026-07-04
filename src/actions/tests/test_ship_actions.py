"""Tests for the ship Actions + ``IsShipOwnerPrerequisite`` (#1832 Task 8)."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.factories import CovenantFactory
from world.locations.factories import LocationOwnershipFactory
from world.projects.constants import ProjectKind
from world.projects.models import Project
from world.ships.constants import ShipUpgradeStat
from world.ships.factories import ShipDetailsFactory, ShipTypeFactory
from world.societies.factories import OrganizationMembershipFactory


def _attach_entry_room(ship):
    """Give *ship*'s building an entry room (a fresh, area-less RoomProfile).

    ``ShipDetailsFactory``'s ``BuildingFactory`` doesn't set ``entry_room`` —
    tests that need to resolve/gate the ship via "the room the actor stands
    in" attach one explicitly. The profile is deliberately area-less (the
    ``RoomProfileFactory`` default) so ``is_owner``/``effective_owner`` never
    reach the Postgres-only ``AreaClosure`` materialized view — room-level
    ``LocationOwnership`` rows still resolve correctly without it.
    """
    profile = RoomProfileFactory()
    ship.building.entry_room = profile
    ship.building.save(update_fields=["entry_room"])
    return profile


class IsShipOwnerPrerequisiteTests(TestCase):
    def setUp(self) -> None:
        from actions.prerequisites import IsShipOwnerPrerequisite

        self.prereq = IsShipOwnerPrerequisite()
        self.owner_sheet = CharacterSheetFactory()
        self.owner_character = self.owner_sheet.character
        self.owner_persona = self.owner_sheet.primary_persona
        self.ship = ShipDetailsFactory(building__owner_persona=self.owner_persona)
        self.entry_room = _attach_entry_room(self.ship)
        self.owner_character.location = self.entry_room.objectdb
        self.owner_character.save()

    def test_denies_a_non_owner(self) -> None:
        intruder_sheet = CharacterSheetFactory()
        intruder = intruder_sheet.character
        intruder.location = self.entry_room.objectdb
        intruder.save()

        met, reason = self.prereq.is_met(intruder, context={"kwargs": {}})

        self.assertFalse(met)
        self.assertTrue(reason)

    def test_allows_the_direct_owner(self) -> None:
        met, _reason = self.prereq.is_met(self.owner_character, context={"kwargs": {}})

        self.assertTrue(met)

    def test_allows_a_member_of_the_owning_covenant(self) -> None:
        covenant = CovenantFactory()
        LocationOwnershipFactory(
            on_room=True,
            on_org=True,
            room_profile=self.entry_room,
            holder_organization=covenant.organization,
        )
        member_sheet = CharacterSheetFactory()
        member_persona = member_sheet.primary_persona
        OrganizationMembershipFactory(organization=covenant.organization, persona=member_persona)
        member_character = member_sheet.character
        member_character.location = self.entry_room.objectdb
        member_character.save()

        met, _reason = self.prereq.is_met(member_character, context={"kwargs": {}})

        self.assertTrue(met)

    def test_resolves_via_ship_kwarg_regardless_of_location(self) -> None:
        elsewhere = RoomProfileFactory()
        self.owner_character.location = elsewhere.objectdb
        self.owner_character.save()

        met, _reason = self.prereq.is_met(
            self.owner_character, context={"kwargs": {"ship": self.ship}}
        )

        self.assertTrue(met)

    def test_no_ship_here_denies(self) -> None:
        lost_sheet = CharacterSheetFactory()
        lost = lost_sheet.character
        lost.location = RoomProfileFactory().objectdb
        lost.save()

        met, reason = self.prereq.is_met(lost, context={"kwargs": {}})

        self.assertFalse(met)
        self.assertTrue(reason)


class CommissionShipActionTests(TestCase):
    def setUp(self) -> None:
        from actions.definitions.ships import CommissionShipAction

        self.action_cls = CommissionShipAction
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.ship_type = ShipTypeFactory()

    def test_commissions_a_ship_project(self) -> None:
        result = self.action_cls().run(
            actor=self.character, ship_type=self.ship_type, name="The Wavecutter"
        )

        self.assertTrue(result.success, result.message)
        project = Project.objects.get(kind=ProjectKind.SHIP_CONSTRUCTION)
        self.assertEqual(project.owner_persona, self.sheet.primary_persona)
        self.assertEqual(result.data["project_id"], project.pk)

    def test_requires_a_ship_type(self) -> None:
        result = self.action_cls().run(actor=self.character, ship_type=None, name="Nameless")

        self.assertFalse(result.success)

    def test_requires_a_name(self) -> None:
        result = self.action_cls().run(actor=self.character, ship_type=self.ship_type, name="")

        self.assertFalse(result.success)


class UpgradeShipActionTests(TestCase):
    def setUp(self) -> None:
        from actions.definitions.ships import UpgradeShipAction

        self.action_cls = UpgradeShipAction
        self.owner_sheet = CharacterSheetFactory()
        self.owner_character = self.owner_sheet.character
        self.owner_persona = self.owner_sheet.primary_persona
        self.ship = ShipDetailsFactory(building__owner_persona=self.owner_persona, handling_level=1)
        self.entry_room = _attach_entry_room(self.ship)
        self.owner_character.location = self.entry_room.objectdb
        self.owner_character.save()

    def test_owner_can_upgrade_handling(self) -> None:
        result = self.action_cls().run(
            actor=self.owner_character,
            ship=self.ship,
            stat=ShipUpgradeStat.HANDLING,
            target_level=3,
        )

        self.assertTrue(result.success, result.message)
        project = Project.objects.get(kind=ProjectKind.SHIP_UPGRADE)
        self.assertEqual(result.data["project_id"], project.pk)

    def test_non_owner_is_denied(self) -> None:
        intruder_sheet = CharacterSheetFactory()
        intruder = intruder_sheet.character
        intruder.location = self.entry_room.objectdb
        intruder.save()

        result = self.action_cls().run(
            actor=intruder, ship=self.ship, stat=ShipUpgradeStat.HANDLING, target_level=3
        )

        self.assertFalse(result.success)
        self.assertFalse(Project.objects.filter(kind=ProjectKind.SHIP_UPGRADE).exists())


class RepairShipActionTests(TestCase):
    def setUp(self) -> None:
        from actions.definitions.ships import RepairShipAction

        self.action_cls = RepairShipAction
        self.owner_sheet = CharacterSheetFactory()
        self.owner_character = self.owner_sheet.character
        self.owner_persona = self.owner_sheet.primary_persona
        self.ship = ShipDetailsFactory(
            building__owner_persona=self.owner_persona, needs_repair=True
        )
        self.entry_room = _attach_entry_room(self.ship)
        self.owner_character.location = self.entry_room.objectdb
        self.owner_character.save()

    def test_owner_can_repair(self) -> None:
        result = self.action_cls().run(actor=self.owner_character, ship=self.ship)

        self.assertTrue(result.success, result.message)
        project = Project.objects.get(kind=ProjectKind.SHIP_REPAIR)
        self.assertEqual(result.data["project_id"], project.pk)

    def test_non_owner_is_denied(self) -> None:
        intruder_sheet = CharacterSheetFactory()
        intruder = intruder_sheet.character
        intruder.location = self.entry_room.objectdb
        intruder.save()

        result = self.action_cls().run(actor=intruder, ship=self.ship)

        self.assertFalse(result.success)
        self.assertFalse(Project.objects.filter(kind=ProjectKind.SHIP_REPAIR).exists())


class ShipStatusActionTests(TestCase):
    def setUp(self) -> None:
        from actions.definitions.ships import ShipStatusAction

        self.action_cls = ShipStatusAction
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.ship = ShipDetailsFactory(needs_repair=True)
        self.entry_room = _attach_entry_room(self.ship)
        self.character.location = self.entry_room.objectdb
        self.character.save()

    def test_reports_effective_stats_and_repair_state(self) -> None:
        result = self.action_cls().run(actor=self.character)

        self.assertTrue(result.success, result.message)
        self.assertEqual(result.data["effective_handling"], self.ship.effective_handling())
        self.assertEqual(result.data["effective_armament"], self.ship.effective_armament())
        self.assertEqual(result.data["effective_hull"], self.ship.effective_hull())
        self.assertTrue(result.data["needs_repair"])

    def test_no_ship_here_fails_cleanly(self) -> None:
        lost_sheet = CharacterSheetFactory()
        lost = lost_sheet.character
        lost.location = RoomProfileFactory().objectdb
        lost.save()

        result = self.action_cls().run(actor=lost)

        self.assertFalse(result.success)
