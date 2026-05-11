"""Tests for covenant models."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType, RoleArchetype
from world.covenants.factories import CovenantRoleFactory
from world.covenants.models import Covenant, CovenantRole, GearArchetypeCompatibility
from world.items.constants import GearArchetype


class CovenantRoleTests(TestCase):
    """Tests for CovenantRole model."""

    def test_create(self) -> None:
        role = CovenantRole.objects.create(
            name="Vanguard",
            slug="vanguard",
            covenant_type=CovenantType.DURANCE,
            archetype=RoleArchetype.SWORD,
            speed_rank=1,
        )
        self.assertEqual(role.name, "Vanguard")
        self.assertEqual(role.speed_rank, 1)

    def test_str(self) -> None:
        role = CovenantRoleFactory(name="Sentinel", covenant_type=CovenantType.DURANCE)
        self.assertEqual(str(role), "Sentinel (Covenant of the Durance)")

    def test_unique_slug(self) -> None:
        CovenantRoleFactory(slug="vanguard-unique")
        with self.assertRaises(IntegrityError):
            CovenantRole.objects.create(
                name="Duplicate",
                slug="vanguard-unique",
                archetype=RoleArchetype.SWORD,
                speed_rank=2,
            )

    def test_unique_name_per_type(self) -> None:
        """Same name in different covenant types is fine; same type is not."""
        CovenantRole.objects.create(
            name="Vanguard",
            slug="vanguard-durance",
            covenant_type=CovenantType.DURANCE,
            archetype=RoleArchetype.SWORD,
            speed_rank=1,
        )
        # Same name, different type — OK
        CovenantRole.objects.create(
            name="Vanguard",
            slug="vanguard-battle",
            covenant_type=CovenantType.BATTLE,
            archetype=RoleArchetype.SWORD,
            speed_rank=2,
        )
        # Same name, same type — constraint violation
        with self.assertRaises(IntegrityError):
            CovenantRole.objects.create(
                name="Vanguard",
                slug="vanguard-durance-2",
                covenant_type=CovenantType.DURANCE,
                archetype=RoleArchetype.SHIELD,
                speed_rank=3,
            )

    def test_factory_smoke(self) -> None:
        role = CovenantRoleFactory()
        self.assertIsNotNone(role.pk)
        self.assertEqual(role.covenant_type, CovenantType.DURANCE)


class GearArchetypeCompatibilityTests(TestCase):
    def test_create(self) -> None:
        role = CovenantRoleFactory()
        row = GearArchetypeCompatibility.objects.create(
            covenant_role=role,
            gear_archetype=GearArchetype.HEAVY_ARMOR,
        )
        self.assertEqual(row.covenant_role, role)

    def test_unique_role_archetype(self) -> None:
        role = CovenantRoleFactory()
        GearArchetypeCompatibility.objects.create(
            covenant_role=role,
            gear_archetype=GearArchetype.HEAVY_ARMOR,
        )
        with self.assertRaises(IntegrityError):
            GearArchetypeCompatibility.objects.create(
                covenant_role=role,
                gear_archetype=GearArchetype.HEAVY_ARMOR,
            )


class CharacterCovenantRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.role = CovenantRoleFactory()
        cls.covenant = Covenant.objects.create(
            name="Test Cov",
            covenant_type=CovenantType.DURANCE,
            sworn_objective="Test objective.",
        )

    def test_create_active(self) -> None:
        from world.covenants.models import CharacterCovenantRole

        row = CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant_role=self.role,
            covenant=self.covenant,
        )
        self.assertIsNone(row.left_at)
        self.assertIsNotNone(row.joined_at)

    def test_one_active_role_per_pair(self) -> None:
        from world.covenants.models import CharacterCovenantRole

        CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant_role=self.role,
            covenant=self.covenant,
        )
        # Active row already exists for this (character, covenant); must fail
        with self.assertRaises(IntegrityError):
            CharacterCovenantRole.objects.create(
                character_sheet=self.sheet,
                covenant_role=self.role,
                covenant=self.covenant,
            )

    def test_historical_assignments_allowed_after_left_at_set(self) -> None:
        from world.covenants.models import CharacterCovenantRole

        first = CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant_role=self.role,
            covenant=self.covenant,
        )
        first.left_at = timezone.now()
        first.save(update_fields=["left_at"])
        # Now a fresh active row should be allowed
        CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant_role=self.role,
            covenant=self.covenant,
        )
        self.assertEqual(
            CharacterCovenantRole.objects.filter(
                character_sheet=self.sheet,
                covenant_role=self.role,
            ).count(),
            2,
        )


class CharacterCovenantRoleConstraintTests(TestCase):
    """Active-uniqueness and clean() coverage for the engagement model."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.cov_a = Covenant.objects.create(
            name="Cov A",
            covenant_type=CovenantType.DURANCE,
            sworn_objective="A.",
        )
        cls.cov_b = Covenant.objects.create(
            name="Cov B",
            covenant_type=CovenantType.DURANCE,
            sworn_objective="B.",
        )
        cls.cov_battle = Covenant.objects.create(
            name="Cov Battle",
            covenant_type=CovenantType.BATTLE,
            sworn_objective="Battle.",
        )
        cls.role_vanguard = CovenantRoleFactory(
            covenant_type=CovenantType.DURANCE,
            archetype=RoleArchetype.SWORD,
        )
        cls.role_sword_battle = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            archetype=RoleArchetype.SWORD,
        )
        cls.sheet = CharacterSheetFactory()

    def test_one_active_role_per_covenant(self) -> None:
        """Two active rows in the same covenant for one character is rejected."""
        from world.covenants.models import CharacterCovenantRole

        CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant=self.cov_a,
            covenant_role=self.role_vanguard,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CharacterCovenantRole.objects.create(
                    character_sheet=self.sheet,
                    covenant=self.cov_a,
                    covenant_role=self.role_vanguard,
                )

    def test_same_role_in_different_covenants_allowed(self) -> None:
        """Vanguard in covenant A AND Vanguard in covenant B is permitted."""
        from world.covenants.models import CharacterCovenantRole

        CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant=self.cov_a,
            covenant_role=self.role_vanguard,
        )
        # Should not raise.
        CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant=self.cov_b,
            covenant_role=self.role_vanguard,
        )

    def test_clean_rejects_engaged_with_left_at(self) -> None:
        from world.covenants.models import CharacterCovenantRole

        ccr = CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant=self.cov_a,
            covenant_role=self.role_vanguard,
            engaged=True,
            left_at=timezone.now(),
        )
        with self.assertRaises(ValidationError):
            ccr.full_clean()

    def test_clean_rejects_two_engaged_same_type(self) -> None:
        from world.covenants.models import CharacterCovenantRole

        CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant=self.cov_a,
            covenant_role=self.role_vanguard,
            engaged=True,
        )
        ccr2 = CharacterCovenantRole(
            character_sheet=self.sheet,
            covenant=self.cov_b,
            covenant_role=self.role_vanguard,
            engaged=True,
        )
        with self.assertRaises(ValidationError):
            ccr2.full_clean()

    def test_clean_permits_engaged_across_types(self) -> None:
        from world.covenants.models import CharacterCovenantRole

        CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant=self.cov_a,
            covenant_role=self.role_vanguard,
            engaged=True,
        )
        ccr2 = CharacterCovenantRole(
            character_sheet=self.sheet,
            covenant=self.cov_battle,
            covenant_role=self.role_sword_battle,
            engaged=True,
        )
        # Should not raise — different covenant types.
        ccr2.full_clean()


class CovenantModelTests(TestCase):
    def test_defaults_and_str(self) -> None:
        cov = Covenant.objects.create(
            name="Test Covenant",
            covenant_type=CovenantType.DURANCE,
            sworn_objective="To do the thing.",
        )
        self.assertEqual(cov.level, 1)
        self.assertIsNone(cov.dissolved_at)
        self.assertIsNotNone(cov.formed_at)
        self.assertIn("Test Covenant", str(cov))
        self.assertIn("active", str(cov))

    def test_dissolved_str(self) -> None:
        from django.utils import timezone

        cov = Covenant.objects.create(
            name="Dead Covenant",
            covenant_type=CovenantType.BATTLE,
            sworn_objective="Was a thing.",
            dissolved_at=timezone.now(),
        )
        self.assertIn("dissolved", str(cov))

    def test_blank_sworn_objective_rejected(self) -> None:
        # Empty sworn_objective should fail full_clean (TextField with blank=False).
        cov = Covenant(
            name="Empty",
            covenant_type=CovenantType.DURANCE,
            sworn_objective="",
        )
        with self.assertRaises(ValidationError):
            cov.full_clean()


class CovenantNameUniqueTests(TestCase):
    def test_duplicate_name_raises_integrity_error(self) -> None:
        from world.covenants.factories import CovenantFactory

        CovenantFactory(name="Sword of Aerith")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CovenantFactory(name="Sword of Aerith")
