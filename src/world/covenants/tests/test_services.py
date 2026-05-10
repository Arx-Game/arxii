"""Tests for covenant service functions (Tasks 22–23)."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    GearArchetypeCompatibilityFactory,
)
from world.covenants.models import CharacterCovenantRole
from world.covenants.services import (
    add_member,
    assign_covenant_role,
    change_role,
    create_covenant,
    dissolve_covenant,
    end_covenant_role,
    is_gear_compatible,
)
from world.items.constants import GearArchetype


class CreateCovenantTests(TestCase):
    def test_creates_covenant_with_founder_membership(self) -> None:
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        cov = create_covenant(
            name="Founders",
            covenant_type=CovenantType.DURANCE,
            sworn_objective="Forge bonds.",
            founder_character_sheet=sheet,
            founder_role=role,
        )
        self.assertEqual(cov.covenant_type, CovenantType.DURANCE)
        membership = CharacterCovenantRole.objects.get(character_sheet=sheet, covenant=cov)
        self.assertEqual(membership.covenant_role, role)
        self.assertIsNone(membership.left_at)
        self.assertFalse(membership.engaged)


class AddMemberTests(TestCase):
    def test_creates_active_membership(self) -> None:
        cov = CovenantFactory()
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=cov.covenant_type)
        membership = add_member(covenant=cov, character_sheet=sheet, role=role)
        self.assertIsNone(membership.left_at)
        self.assertEqual(membership.covenant, cov)

    def test_duplicate_active_raises_integrity_error(self) -> None:
        cov = CovenantFactory()
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=cov.covenant_type)
        add_member(covenant=cov, character_sheet=sheet, role=role)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                add_member(covenant=cov, character_sheet=sheet, role=role)


class ChangeRoleTests(TestCase):
    def test_closes_old_creates_new(self) -> None:
        cov = CovenantFactory()
        sheet = CharacterSheetFactory()
        old_role = CovenantRoleFactory(covenant_type=cov.covenant_type)
        new_role = CovenantRoleFactory(covenant_type=cov.covenant_type)
        membership = CharacterCovenantRoleFactory(
            character_sheet=sheet, covenant=cov, covenant_role=old_role
        )
        new_membership = change_role(membership=membership, new_role=new_role)

        membership.refresh_from_db()
        self.assertIsNotNone(membership.left_at)
        self.assertFalse(membership.engaged)

        self.assertIsNone(new_membership.left_at)
        self.assertEqual(new_membership.covenant_role, new_role)
        self.assertFalse(new_membership.engaged)  # explicit re-engagement required


class DissolveCovenantTests(TestCase):
    def test_ends_all_memberships_and_unengages(self) -> None:
        cov = CovenantFactory()
        s1 = CharacterSheetFactory()
        s2 = CharacterSheetFactory()
        role = CovenantRoleFactory(covenant_type=cov.covenant_type)
        m1 = CharacterCovenantRoleFactory(character_sheet=s1, covenant=cov, covenant_role=role)
        m2 = CharacterCovenantRoleFactory(character_sheet=s2, covenant=cov, covenant_role=role)
        # Set m1 engaged directly (no service yet)
        m1.engaged = True
        m1.save(update_fields=["engaged"])

        dissolve_covenant(covenant=cov)

        cov.refresh_from_db()
        self.assertIsNotNone(cov.dissolved_at)
        for m in (m1, m2):
            m.refresh_from_db()
            self.assertIsNotNone(m.left_at)
            self.assertFalse(m.engaged)

    def test_idempotent(self) -> None:
        cov = CovenantFactory()
        dissolve_covenant(covenant=cov)
        cov.refresh_from_db()
        first_dissolved_at = cov.dissolved_at
        dissolve_covenant(covenant=cov)
        cov.refresh_from_db()
        self.assertEqual(cov.dissolved_at, first_dissolved_at)


class AssignCovenantRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.cov = CovenantFactory()
        cls.role = CovenantRoleFactory(slug="vanguard", covenant_type=cls.cov.covenant_type)

    def test_assign_creates_active_row(self) -> None:
        assignment = assign_covenant_role(
            character_sheet=self.sheet, covenant=self.cov, covenant_role=self.role
        )
        self.assertIsNone(assignment.left_at)
        self.assertEqual(assignment.character_sheet, self.sheet)
        self.assertEqual(assignment.covenant_role, self.role)

    def test_assign_invalidates_handler(self) -> None:
        # Warm the cache before assigning.
        _ = self.sheet.character.covenant_roles.currently_held()

        new_cov = CovenantFactory()
        new_role = CovenantRoleFactory(slug="anchor", covenant_type=new_cov.covenant_type)
        assign_covenant_role(character_sheet=self.sheet, covenant=new_cov, covenant_role=new_role)

        # currently_held should reflect the new assignment, not stale cache.
        self.assertEqual(self.sheet.character.covenant_roles.currently_held(), new_role)

    def test_assign_duplicate_active_raises_integrity_error(self) -> None:
        # Create an active assignment first.
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet, covenant=self.cov, covenant_role=self.role
        )

        with self.assertRaises(IntegrityError):
            assign_covenant_role(
                character_sheet=self.sheet, covenant=self.cov, covenant_role=self.role
            )


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
