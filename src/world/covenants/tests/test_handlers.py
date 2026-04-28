"""Tests for CharacterCovenantRoleHandler (Spec D §3.3)."""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.factories import CharacterCovenantRoleFactory, CovenantRoleFactory


class CharacterCovenantRoleHandlerTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.role_a = CovenantRoleFactory(name="Vanguard", slug="vanguard")
        cls.role_b = CovenantRoleFactory(name="Anchor", slug="anchor")
        cls.assignment = CharacterCovenantRoleFactory(
            character_sheet=cls.sheet,
            covenant_role=cls.role_a,
        )

    def test_currently_held(self) -> None:
        result = self.sheet.character.covenant_roles.currently_held()
        self.assertEqual(result, self.role_a)

    def test_has_ever_held_active_role(self) -> None:
        result = self.sheet.character.covenant_roles.has_ever_held(self.role_a)
        self.assertTrue(result)

    def test_has_never_held(self) -> None:
        result = self.sheet.character.covenant_roles.has_ever_held(self.role_b)
        self.assertFalse(result)

    def test_has_ever_held_after_role_ended(self) -> None:
        # Mark the assignment as ended and invalidate the cache.
        self.assignment.left_at = timezone.now()
        self.assignment.save(update_fields=["left_at"])
        self.sheet.character.covenant_roles.invalidate()

        self.assertTrue(self.sheet.character.covenant_roles.has_ever_held(self.role_a))
        self.assertIsNone(self.sheet.character.covenant_roles.currently_held())

        # Restore so other tests in setUpTestData aren't affected.
        self.assignment.left_at = None
        self.assignment.save(update_fields=["left_at"])
        self.sheet.character.covenant_roles.invalidate()
