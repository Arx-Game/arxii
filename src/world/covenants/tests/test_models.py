"""Tests for covenant models."""

from django.db import IntegrityError
from django.test import TestCase

from world.covenants.constants import CovenantType, RoleArchetype
from world.covenants.factories import CovenantRoleFactory
from world.covenants.models import CovenantRole, GearArchetypeCompatibility
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
        from world.character_sheets.factories import CharacterSheetFactory

        cls.sheet = CharacterSheetFactory()
        cls.role = CovenantRoleFactory()

    def test_create_active(self) -> None:
        from world.covenants.models import CharacterCovenantRole

        row = CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant_role=self.role,
        )
        self.assertIsNone(row.left_at)
        self.assertIsNotNone(row.joined_at)

    def test_one_active_role_per_pair(self) -> None:
        from world.covenants.models import CharacterCovenantRole

        CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant_role=self.role,
        )
        # Active row already exists; another active create must fail
        with self.assertRaises(IntegrityError):
            CharacterCovenantRole.objects.create(
                character_sheet=self.sheet,
                covenant_role=self.role,
            )

    def test_historical_assignments_allowed_after_left_at_set(self) -> None:
        from django.utils import timezone

        from world.covenants.models import CharacterCovenantRole

        first = CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant_role=self.role,
        )
        first.left_at = timezone.now()
        first.save(update_fields=["left_at"])
        # Now a fresh active row should be allowed
        CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant_role=self.role,
        )
        self.assertEqual(
            CharacterCovenantRole.objects.filter(
                character_sheet=self.sheet,
                covenant_role=self.role,
            ).count(),
            2,
        )
