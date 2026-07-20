"""Tests for covenant models."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CommandTier, CovenantType
from world.covenants.factories import (
    CovenantFactory,
    CovenantRankFactory,
    CovenantRoleFactory,
)
from world.covenants.models import (
    CharacterCovenantRole,
    Covenant,
    CovenantRank,
    CovenantRiteParticipant,
    CovenantRole,
    GearArchetypeCompatibility,
)
from world.items.constants import GearArchetype


class CovenantRoleTests(TestCase):
    """Tests for CovenantRole model."""

    def test_create(self) -> None:
        role = CovenantRole.objects.create(
            name="Vanguard",
            slug="vanguard",
            covenant_type=CovenantType.DURANCE,
            sword_weight=1,
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
                sword_weight=1,
                speed_rank=2,
            )

    def test_unique_name_per_type(self) -> None:
        """Same name in different covenant types is fine; same type is not."""
        CovenantRole.objects.create(
            name="Vanguard",
            slug="vanguard-durance",
            covenant_type=CovenantType.DURANCE,
            sword_weight=1,
            speed_rank=1,
        )
        # Same name, different type — OK
        CovenantRole.objects.create(
            name="Vanguard",
            slug="vanguard-battle",
            covenant_type=CovenantType.BATTLE,
            sword_weight=1,
            speed_rank=2,
        )
        # Same name, same type — constraint violation
        with self.assertRaises(IntegrityError):
            CovenantRole.objects.create(
                name="Vanguard",
                slug="vanguard-durance-2",
                covenant_type=CovenantType.DURANCE,
                shield_weight=1,
                speed_rank=3,
            )

    def test_factory_smoke(self) -> None:
        role = CovenantRoleFactory()
        self.assertIsNotNone(role.pk)
        self.assertEqual(role.covenant_type, CovenantType.DURANCE)

    def test_no_is_leadership_field(self) -> None:
        """CovenantRole must NOT have an is_leadership field after #1027."""
        role = CovenantRole()
        self.assertFalse(hasattr(role, "is_leadership"))

    def test_command_tier_defaults_to_none(self) -> None:
        role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        self.assertEqual(role.command_tier, CommandTier.NONE)
        self.assertFalse(role.is_champion_role)

    def test_command_tier_requires_battle_covenant_type(self) -> None:
        role = CovenantRoleFactory.build(
            covenant_type=CovenantType.DURANCE,
            command_tier=CommandTier.SUPREME,
        )
        with self.assertRaises(ValidationError):
            role.full_clean()

    def test_champion_role_requires_battle_covenant_type(self) -> None:
        role = CovenantRoleFactory.build(
            covenant_type=CovenantType.DURANCE,
            is_champion_role=True,
        )
        with self.assertRaises(ValidationError):
            role.full_clean()

    def test_command_tier_allowed_on_battle_covenant(self) -> None:
        role = CovenantRoleFactory.build(
            covenant_type=CovenantType.BATTLE,
            command_tier=CommandTier.SUPREME,
            slug="test-supreme-commander",
        )
        role.full_clean()  # must not raise


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
        cls.rank = CovenantRank.objects.create(covenant=cls.covenant, name="Member", tier=1)

    def test_create_active(self) -> None:
        from world.covenants.models import CharacterCovenantRole

        row = CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant_role=self.role,
            covenant=self.covenant,
            rank=self.rank,
        )
        self.assertIsNone(row.left_at)
        self.assertIsNotNone(row.joined_at)

    def test_one_active_role_per_pair(self) -> None:
        from world.covenants.models import CharacterCovenantRole

        CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant_role=self.role,
            covenant=self.covenant,
            rank=self.rank,
        )
        # Active row already exists for this (character, covenant); must fail
        with self.assertRaises(IntegrityError):
            CharacterCovenantRole.objects.create(
                character_sheet=self.sheet,
                covenant_role=self.role,
                covenant=self.covenant,
                rank=self.rank,
            )

    def test_historical_assignments_allowed_after_left_at_set(self) -> None:
        from world.covenants.models import CharacterCovenantRole

        first = CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant_role=self.role,
            covenant=self.covenant,
            rank=self.rank,
        )
        first.left_at = timezone.now()
        first.save(update_fields=["left_at"])
        # Now a fresh active row should be allowed
        CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant_role=self.role,
            covenant=self.covenant,
            rank=self.rank,
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
            sword_weight=1,
        )
        cls.role_sword_battle = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            sword_weight=1,
        )
        cls.sheet = CharacterSheetFactory()
        cls.rank_a = CovenantRank.objects.create(covenant=cls.cov_a, name="Member", tier=1)
        cls.rank_b = CovenantRank.objects.create(covenant=cls.cov_b, name="Member", tier=1)
        cls.rank_battle = CovenantRank.objects.create(
            covenant=cls.cov_battle, name="Member", tier=1
        )

    def test_one_active_role_per_covenant(self) -> None:
        """Two active rows in the same covenant for one character is rejected."""
        from world.covenants.models import CharacterCovenantRole

        CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant=self.cov_a,
            covenant_role=self.role_vanguard,
            rank=self.rank_a,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CharacterCovenantRole.objects.create(
                    character_sheet=self.sheet,
                    covenant=self.cov_a,
                    covenant_role=self.role_vanguard,
                    rank=self.rank_a,
                )

    def test_same_role_in_different_covenants_allowed(self) -> None:
        """Vanguard in covenant A AND Vanguard in covenant B is permitted."""
        from world.covenants.models import CharacterCovenantRole

        CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant=self.cov_a,
            covenant_role=self.role_vanguard,
            rank=self.rank_a,
        )
        # Should not raise.
        CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant=self.cov_b,
            covenant_role=self.role_vanguard,
            rank=self.rank_b,
        )

    def test_clean_rejects_engaged_with_left_at(self) -> None:
        from world.covenants.models import CharacterCovenantRole

        ccr = CharacterCovenantRole.objects.create(
            character_sheet=self.sheet,
            covenant=self.cov_a,
            covenant_role=self.role_vanguard,
            rank=self.rank_a,
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
            rank=self.rank_a,
            engaged=True,
        )
        ccr2 = CharacterCovenantRole(
            character_sheet=self.sheet,
            covenant=self.cov_b,
            covenant_role=self.role_vanguard,
            rank=self.rank_b,
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
            rank=self.rank_a,
            engaged=True,
        )
        ccr2 = CharacterCovenantRole(
            character_sheet=self.sheet,
            covenant=self.cov_battle,
            covenant_role=self.role_sword_battle,
            rank=self.rank_battle,
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


class CovenantRiteSeverityForTests(TestCase):
    """Unit tests for CovenantRite.severity_for() — no DB required."""

    def _make_rite(self) -> object:
        from world.covenants.models import CovenantRite

        return CovenantRite(
            min_members_present=2,
            base_severity=3,
            severity_per_extra_participant=2,
            max_severity=10,
        )

    def test_exactly_minimum_present(self) -> None:
        rite = self._make_rite()
        self.assertEqual(rite.severity_for(present_count=2), 3)

    def test_two_extras(self) -> None:
        rite = self._make_rite()
        self.assertEqual(rite.severity_for(present_count=4), 7)

    def test_capped_at_max_severity(self) -> None:
        rite = self._make_rite()
        self.assertEqual(rite.severity_for(present_count=10), 10)

    def test_below_minimum_floors_to_base(self) -> None:
        rite = self._make_rite()
        self.assertEqual(rite.severity_for(present_count=1), 3)

    def test_no_max_severity_uncapped(self) -> None:
        from world.covenants.models import CovenantRite

        rite = CovenantRite(
            min_members_present=2,
            base_severity=1,
            severity_per_extra_participant=5,
            max_severity=None,
        )
        self.assertEqual(rite.severity_for(present_count=12), 51)


class CovenantRiteInstanceTests(TestCase):
    """DB integration tests for CovenantRiteInstance."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.conditions.factories import ConditionTemplateFactory
        from world.covenants.factories import CovenantFactory
        from world.magic.factories import RitualFactory
        from world.scenes.factories import SceneFactory

        cls.covenant = CovenantFactory()
        cls.scene = SceneFactory()
        cls.ritual = RitualFactory()
        cls.condition_template = ConditionTemplateFactory()
        cls.sheet = CharacterSheetFactory()

    def _make_rite(self) -> object:
        from world.covenants.models import CovenantRite

        return CovenantRite.objects.create(
            ritual=self.ritual,
            granted_condition=self.condition_template,
            base_severity=2,
        )

    def test_create_instance_and_add_participant(self) -> None:
        from world.covenants.models import CovenantRiteInstance

        rite = self._make_rite()
        instance = CovenantRiteInstance.objects.create(
            rite=rite,
            covenant=self.covenant,
            scene=self.scene,
        )
        # Through-model: create the participant record directly.
        CovenantRiteParticipant.objects.create(
            instance=instance,
            character_sheet=self.sheet,
            granted_condition=self.condition_template,
        )

        self.assertEqual(instance.participants.count(), 1)
        self.assertIsNone(instance.completed_at)
        self.assertIsNone(instance.combat_encounter)
        self.assertIsNotNone(instance.fired_at)

    def test_rite_meta(self) -> None:
        rite = self._make_rite()
        self.assertEqual(rite._meta.verbose_name, "Covenant Rite")
        self.assertEqual(rite._meta.verbose_name_plural, "Covenant Rites")


class CovenantRankTests(TestCase):
    """Tests for CovenantRank model — unique constraints and factory."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.covenants.factories import CovenantFactory

        cls.covenant = CovenantFactory(name="Rank Test Covenant")

    def test_create_rank(self) -> None:
        rank = CovenantRank.objects.create(
            covenant=self.covenant,
            name="Magister",
            tier=1,
        )
        self.assertEqual(rank.name, "Magister")
        self.assertEqual(rank.tier, 1)
        self.assertFalse(rank.can_invite)
        self.assertFalse(rank.can_kick)
        self.assertFalse(rank.can_manage_ranks)

    def test_str(self) -> None:
        rank = CovenantRank.objects.create(
            covenant=self.covenant,
            name="Warden",
            tier=2,
        )
        self.assertIn("Warden", str(rank))
        self.assertIn("tier 2", str(rank))
        self.assertIn(self.covenant.name, str(rank))

    def test_unique_tier_per_covenant(self) -> None:
        CovenantRank.objects.create(covenant=self.covenant, name="Grand Master", tier=10)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CovenantRank.objects.create(covenant=self.covenant, name="Other", tier=10)

    def test_unique_name_per_covenant(self) -> None:
        CovenantRank.objects.create(covenant=self.covenant, name="Unique Name", tier=20)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CovenantRank.objects.create(covenant=self.covenant, name="Unique Name", tier=21)

    def test_same_tier_different_covenant_allowed(self) -> None:
        from world.covenants.factories import CovenantFactory

        other = CovenantFactory(name="Other Covenant For Rank")
        CovenantRank.objects.create(covenant=self.covenant, name="Alpha", tier=99)
        # Should not raise — same tier, different covenant.
        CovenantRank.objects.create(covenant=other, name="Alpha", tier=99)

    def test_factory(self) -> None:
        from world.covenants.factories import CovenantRankFactory

        rank = CovenantRankFactory()
        self.assertIsNotNone(rank.pk)
        self.assertFalse(rank.can_invite)
        self.assertFalse(rank.can_kick)
        self.assertFalse(rank.can_manage_ranks)

    def test_manager_variant_factory(self) -> None:
        from world.covenants.factories import CovenantManagerRankFactory

        rank = CovenantManagerRankFactory()
        self.assertTrue(rank.can_invite)
        self.assertTrue(rank.can_kick)
        self.assertTrue(rank.can_manage_ranks)

    def test_ordering(self) -> None:
        from world.covenants.factories import CovenantFactory

        cov = CovenantFactory(name="Ordered Covenant")
        CovenantRank.objects.create(covenant=cov, name="Bottom", tier=5)
        CovenantRank.objects.create(covenant=cov, name="Top", tier=1)
        ranks = list(CovenantRank.objects.filter(covenant=cov))
        self.assertEqual(ranks[0].tier, 1)
        self.assertEqual(ranks[1].tier, 5)


class CharacterCovenantRoleRankTests(TestCase):
    """Tests for CharacterCovenantRole.rank FK and the rank/covenant-match clean() check."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.covenants.factories import CovenantFactory, CovenantRankFactory

        cls.sheet = CharacterSheetFactory()
        cls.covenant = CovenantFactory(name="Rank Member Covenant")
        cls.other_covenant = CovenantFactory(name="Wrong Covenant For Rank")
        cls.role = CovenantRoleFactory()
        cls.rank = CovenantRankFactory(covenant=cls.covenant, tier=1)
        cls.wrong_rank = CovenantRankFactory(covenant=cls.other_covenant, tier=1)

    def test_membership_factory_has_rank(self) -> None:
        from world.covenants.factories import CharacterCovenantRoleFactory

        ccr = CharacterCovenantRoleFactory()
        self.assertIsNotNone(ccr.rank_id)
        # The factory must wire rank.covenant == membership.covenant.
        self.assertEqual(ccr.rank.covenant_id, ccr.covenant_id)

    def test_clean_rejects_rank_from_wrong_covenant(self) -> None:
        from world.covenants.models import CharacterCovenantRole

        ccr = CharacterCovenantRole(
            character_sheet=self.sheet,
            covenant=self.covenant,
            covenant_role=self.role,
            rank=self.wrong_rank,
        )
        with self.assertRaises(ValidationError) as ctx:
            ccr.full_clean()
        self.assertIn("rank", ctx.exception.message_dict)

    def test_clean_accepts_rank_from_correct_covenant(self) -> None:
        from world.covenants.models import CharacterCovenantRole

        ccr = CharacterCovenantRole(
            character_sheet=self.sheet,
            covenant=self.covenant,
            covenant_role=self.role,
            rank=self.rank,
        )
        # Should not raise ValidationError for the rank field.
        ccr.full_clean()


class CommandTierExclusivityTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.covenant = CovenantFactory(covenant_type=CovenantType.BATTLE)
        cls.supreme_role = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            command_tier=CommandTier.SUPREME,
            slug="supreme-commander",
        )
        cls.rank = CovenantRankFactory(covenant=cls.covenant)
        cls.sheet_a = CharacterSheetFactory()
        cls.sheet_b = CharacterSheetFactory()

    def test_second_engaged_supreme_in_same_covenant_rejected(self) -> None:
        CharacterCovenantRole.objects.create(
            character_sheet=self.sheet_a,
            covenant_role=self.supreme_role,
            covenant=self.covenant,
            rank=self.rank,
            engaged=True,
        )
        second = CharacterCovenantRole(
            character_sheet=self.sheet_b,
            covenant_role=self.supreme_role,
            covenant=self.covenant,
            rank=self.rank,
            engaged=True,
        )
        with self.assertRaises(ValidationError):
            second.full_clean()

    def test_subordinate_tier_is_not_exclusive(self) -> None:
        subordinate_role = CovenantRoleFactory(
            covenant_type=CovenantType.BATTLE,
            command_tier=CommandTier.SUBORDINATE,
            slug="subordinate-commander",
        )
        CharacterCovenantRole.objects.create(
            character_sheet=self.sheet_a,
            covenant_role=subordinate_role,
            covenant=self.covenant,
            rank=self.rank,
            engaged=True,
        )
        second = CharacterCovenantRole(
            character_sheet=self.sheet_b,
            covenant_role=subordinate_role,
            covenant=self.covenant,
            rank=self.rank,
            engaged=True,
        )
        second.full_clean()  # must not raise
