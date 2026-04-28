"""Tests for covenant service functions (Tasks 22–23)."""

from __future__ import annotations

from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantRoleFactory,
    GearArchetypeCompatibilityFactory,
)
from world.covenants.services import assign_covenant_role, end_covenant_role, is_gear_compatible
from world.items.constants import GearArchetype


class AssignCovenantRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.role = CovenantRoleFactory(slug="vanguard")

    def test_assign_creates_active_row(self) -> None:
        assignment = assign_covenant_role(character_sheet=self.sheet, covenant_role=self.role)
        self.assertIsNone(assignment.left_at)
        self.assertEqual(assignment.character_sheet, self.sheet)
        self.assertEqual(assignment.covenant_role, self.role)

    def test_assign_invalidates_handler(self) -> None:
        # Warm the cache before assigning.
        _ = self.sheet.character.covenant_roles.currently_held()

        new_role = CovenantRoleFactory(slug="anchor")
        assign_covenant_role(character_sheet=self.sheet, covenant_role=new_role)

        # currently_held should reflect the new assignment, not stale cache.
        self.assertEqual(self.sheet.character.covenant_roles.currently_held(), new_role)

    def test_assign_duplicate_active_raises_integrity_error(self) -> None:
        # Create an active assignment first.
        CharacterCovenantRoleFactory(character_sheet=self.sheet, covenant_role=self.role)

        with self.assertRaises(IntegrityError):
            assign_covenant_role(character_sheet=self.sheet, covenant_role=self.role)


class EndCovenantRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.role = CovenantRoleFactory(slug="shield-end")

    def test_end_sets_left_at(self) -> None:
        assignment = CharacterCovenantRoleFactory(
            character_sheet=self.sheet, covenant_role=self.role
        )
        end_covenant_role(assignment=assignment)
        self.assertIsNotNone(assignment.left_at)

    def test_end_is_idempotent(self) -> None:
        assignment = CharacterCovenantRoleFactory(
            character_sheet=self.sheet, covenant_role=self.role
        )
        end_covenant_role(assignment=assignment)
        first_left_at = assignment.left_at

        # Calling again should not modify left_at.
        end_covenant_role(assignment=assignment)
        self.assertEqual(assignment.left_at, first_left_at)

    def test_end_invalidates_handler(self) -> None:
        assignment = CharacterCovenantRoleFactory(
            character_sheet=self.sheet, covenant_role=self.role
        )
        # Warm the cache so currently_held returns role.
        self.assertEqual(self.sheet.character.covenant_roles.currently_held(), self.role)

        end_covenant_role(assignment=assignment)

        # After ending, currently_held should return None.
        self.assertIsNone(self.sheet.character.covenant_roles.currently_held())


class IsGearCompatibleTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.role = CovenantRoleFactory(slug="crown-gear")

    def test_is_gear_compatible_returns_true_when_row_exists(self) -> None:
        GearArchetypeCompatibilityFactory(
            covenant_role=self.role, gear_archetype=GearArchetype.HEAVY_ARMOR
        )
        self.assertTrue(is_gear_compatible(self.role, GearArchetype.HEAVY_ARMOR))

    def test_is_gear_compatible_returns_false_when_row_missing(self) -> None:
        self.assertFalse(is_gear_compatible(self.role, GearArchetype.LIGHT_ARMOR))
