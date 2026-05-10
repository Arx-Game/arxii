"""Tests for CharacterCovenantRoleHandler (Spec D §3.3)."""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    make_engaged_member,
)


class CharacterCovenantRoleHandlerTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.role_a = CovenantRoleFactory(name="Vanguard", slug="vanguard")
        cls.role_b = CovenantRoleFactory(name="Anchor", slug="anchor")
        cls.cov_a = CovenantFactory()
        cls.assignment = CharacterCovenantRoleFactory(
            character_sheet=cls.sheet,
            covenant=cls.cov_a,
            covenant_role=cls.role_a,
        )

    def test_currently_held_role_in(self) -> None:
        result = self.sheet.character.covenant_roles.currently_held_role_in(self.cov_a)
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
        self.assertIsNone(self.sheet.character.covenant_roles.currently_held_role_in(self.cov_a))

        # Restore so other tests in setUpTestData aren't affected.
        self.assignment.left_at = None
        self.assignment.save(update_fields=["left_at"])
        self.sheet.character.covenant_roles.invalidate()


class MaxCovenantLevelForRoleTests(TestCase):
    def test_returns_zero_when_no_rows(self) -> None:
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory()
        self.assertEqual(
            sheet.character.covenant_roles.max_covenant_level_for_role(role),
            0,
        )

    def test_returns_max_across_rows(self) -> None:
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        cov_a = CovenantFactory(covenant_type=CovenantType.DURANCE, level=3)
        cov_b = CovenantFactory(covenant_type=CovenantType.DURANCE, level=7)
        cov_c = CovenantFactory(covenant_type=CovenantType.DURANCE, level=5)
        for cov in (cov_a, cov_b, cov_c):
            CharacterCovenantRoleFactory(
                character_sheet=sheet,
                covenant=cov,
                covenant_role=role,
            )
        self.assertEqual(
            sheet.character.covenant_roles.max_covenant_level_for_role(role),
            7,
        )

    def test_includes_historical_rows(self) -> None:
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        cov = CovenantFactory(covenant_type=CovenantType.DURANCE, level=10)
        CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=cov,
            covenant_role=role,
            left_at=timezone.now(),  # historical
        )
        self.assertEqual(
            sheet.character.covenant_roles.max_covenant_level_for_role(role),
            10,
        )


class CurrentlyHeldRoleInTests(TestCase):
    def test_returns_none_when_no_rows(self) -> None:
        sheet = CharacterSheetFactory()
        cov = CovenantFactory()
        self.assertIsNone(sheet.character.covenant_roles.currently_held_role_in(cov))

    def test_returns_role_for_active_membership(self) -> None:
        sheet = CharacterSheetFactory()
        cov = CovenantFactory()
        role = CovenantRoleFactory(covenant_type=cov.covenant_type)
        CharacterCovenantRoleFactory(character_sheet=sheet, covenant=cov, covenant_role=role)
        self.assertEqual(
            sheet.character.covenant_roles.currently_held_role_in(cov),
            role,
        )

    def test_returns_none_for_ended_membership(self) -> None:
        sheet = CharacterSheetFactory()
        cov = CovenantFactory()
        role = CovenantRoleFactory(covenant_type=cov.covenant_type)
        CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=cov,
            covenant_role=role,
            left_at=timezone.now(),
        )
        self.assertIsNone(sheet.character.covenant_roles.currently_held_role_in(cov))

    def test_returns_none_when_active_in_other_covenant(self) -> None:
        sheet = CharacterSheetFactory()
        cov_a = CovenantFactory()
        cov_b = CovenantFactory()
        role = CovenantRoleFactory(covenant_type=cov_a.covenant_type)
        CharacterCovenantRoleFactory(character_sheet=sheet, covenant=cov_a, covenant_role=role)
        # Querying cov_b should return None.
        self.assertIsNone(sheet.character.covenant_roles.currently_held_role_in(cov_b))


class CurrentlyEngagedRolesTests(TestCase):
    def test_returns_empty_when_no_engaged(self) -> None:
        sheet = CharacterSheetFactory()
        # Active membership but engaged=False
        CharacterCovenantRoleFactory(character_sheet=sheet)
        self.assertEqual(
            list(sheet.character.covenant_roles.currently_engaged_roles()),
            [],
        )

    def test_returns_engaged_role(self) -> None:
        membership = make_engaged_member()
        self.assertEqual(
            list(membership.character_sheet.character.covenant_roles.currently_engaged_roles()),
            [membership.covenant_role],
        )

    def test_returns_multiple_engaged_across_types(self) -> None:
        sheet = CharacterSheetFactory()
        durance_m = make_engaged_member(character_sheet=sheet)
        # Cross-type engagement (Battle) does not un-engage Durance
        battle_cov = CovenantFactory(covenant_type=CovenantType.BATTLE)
        battle_role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        battle_m = CharacterCovenantRoleFactory(
            character_sheet=sheet, covenant=battle_cov, covenant_role=battle_role
        )
        from world.covenants.services import set_engaged_membership

        set_engaged_membership(membership=battle_m)
        engaged = list(sheet.character.covenant_roles.currently_engaged_roles())
        self.assertIn(durance_m.covenant_role, engaged)
        self.assertIn(battle_m.covenant_role, engaged)

    def test_excludes_engaged_with_left_at_set(self) -> None:
        # Defensive: an inconsistent row with engaged=True AND left_at NOT NULL
        # should not be returned by this method.
        sheet = CharacterSheetFactory()
        cov = CovenantFactory()
        role = CovenantRoleFactory(covenant_type=cov.covenant_type)
        CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=cov,
            covenant_role=role,
            engaged=True,
            left_at=timezone.now(),
        )
        self.assertEqual(
            list(sheet.character.covenant_roles.currently_engaged_roles()),
            [],
        )
