"""Idempotency tests for seed_items_dev() and seed_facet_thread_unlock().

Verifies:
1. seed_items_dev() creates ItemTemplate, TemplateSlot, GearArchetypeCompatibility,
   and CovenantRole rows with correct counts on first call.
2. A second call produces zero new DB writes (idempotent).
3. seed_facet_thread_unlock() creates exactly one ThreadWeavingUnlock for FACET kind.
4. A second call to seed_facet_thread_unlock() is a no-op.
"""

from django.test import TestCase

from integration_tests.game_content.items import (
    ItemsDevSeedResult,
    seed_items_dev,
)
from integration_tests.game_content.magic import (
    FacetThreadUnlockResult,
    seed_facet_thread_unlock,
)
from world.covenants.models import CovenantRole, GearArchetypeCompatibility
from world.items.models import ItemTemplate, TemplateSlot


class SeedItemsDevCreationTests(TestCase):
    """First-call assertions: expected rows exist after seed_items_dev()."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.result: ItemsDevSeedResult = seed_items_dev()

    def test_template_catalog_has_ten_templates(self) -> None:
        self.assertEqual(len(self.result.template_catalog.templates), 10)

    def test_all_templates_in_db(self) -> None:
        self.assertEqual(ItemTemplate.objects.count(), 10)

    def test_template_slots_created(self) -> None:
        """At least one slot per template; total > 10 (multi-slot templates exist)."""
        self.assertGreater(TemplateSlot.objects.count(), 10)

    def test_three_covenant_roles_created(self) -> None:
        self.assertEqual(CovenantRole.objects.count(), 3)

    def test_compatibility_matrix_has_eleven_rows(self) -> None:
        """Sword × 5, Shield × 3, Crown × 3 = 11 compat rows."""
        self.assertEqual(len(self.result.compatibility.compatibilities), 11)
        self.assertEqual(GearArchetypeCompatibility.objects.count(), 11)

    def test_sword_role_archetype(self) -> None:
        from world.covenants.constants import RoleArchetype

        self.assertEqual(self.result.compatibility.sword_role.archetype, RoleArchetype.SWORD)

    def test_shield_role_archetype(self) -> None:
        from world.covenants.constants import RoleArchetype

        self.assertEqual(self.result.compatibility.shield_role.archetype, RoleArchetype.SHIELD)

    def test_crown_role_archetype(self) -> None:
        from world.covenants.constants import RoleArchetype

        self.assertEqual(self.result.compatibility.crown_role.archetype, RoleArchetype.CROWN)

    def test_template_archetype_keys_match_constants(self) -> None:
        """templates dict keys are actual GearArchetype values (not label strings)."""
        from world.items.constants import GearArchetype

        expected_archetypes = {
            GearArchetype.HEAVY_ARMOR,
            GearArchetype.MEDIUM_ARMOR,
            GearArchetype.LIGHT_ARMOR,
            GearArchetype.ROBE,
            GearArchetype.MELEE_ONE_HAND,
            GearArchetype.MELEE_TWO_HAND,
            GearArchetype.SHIELD,
            GearArchetype.CLOTHING,
            GearArchetype.JEWELRY,
            GearArchetype.RANGED,
        }
        self.assertEqual(set(self.result.template_catalog.templates.keys()), expected_archetypes)


class SeedItemsDevIdempotencyTests(TestCase):
    """Second-call assertions: no duplicate rows created."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_items_dev()
        cls.template_count = ItemTemplate.objects.count()
        cls.slot_count = TemplateSlot.objects.count()
        cls.compat_count = GearArchetypeCompatibility.objects.count()
        cls.role_count = CovenantRole.objects.count()

    def test_double_call_templates_no_duplicates(self) -> None:
        seed_items_dev()
        self.assertEqual(ItemTemplate.objects.count(), self.template_count)

    def test_double_call_slots_no_duplicates(self) -> None:
        seed_items_dev()
        self.assertEqual(TemplateSlot.objects.count(), self.slot_count)

    def test_double_call_compat_no_duplicates(self) -> None:
        seed_items_dev()
        self.assertEqual(GearArchetypeCompatibility.objects.count(), self.compat_count)

    def test_double_call_roles_no_duplicates(self) -> None:
        seed_items_dev()
        self.assertEqual(CovenantRole.objects.count(), self.role_count)


class SeedFacetThreadUnlockCreationTests(TestCase):
    """First-call assertions for seed_facet_thread_unlock()."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.result: FacetThreadUnlockResult = seed_facet_thread_unlock()

    def test_unlock_created(self) -> None:
        from world.magic.constants import TargetKind
        from world.magic.models.weaving import ThreadWeavingUnlock

        self.assertEqual(
            ThreadWeavingUnlock.objects.filter(target_kind=TargetKind.FACET).count(),
            1,
        )

    def test_unlock_instance_returned(self) -> None:
        from world.magic.models.weaving import ThreadWeavingUnlock

        self.assertIsInstance(self.result.unlock, ThreadWeavingUnlock)

    def test_unlock_xp_cost(self) -> None:
        self.assertEqual(self.result.unlock.xp_cost, 50)

    def test_unlock_target_kind_is_facet(self) -> None:
        from world.magic.constants import TargetKind

        self.assertEqual(self.result.unlock.target_kind, TargetKind.FACET)

    def test_unlock_fks_are_null(self) -> None:
        """FACET unlock has no typed-FK qualifiers — all null."""
        unlock = self.result.unlock
        self.assertIsNone(unlock.unlock_trait_id)
        self.assertIsNone(unlock.unlock_gift_id)
        self.assertIsNone(unlock.unlock_room_property_id)
        self.assertIsNone(unlock.unlock_track_id)


class SeedFacetThreadUnlockIdempotencyTests(TestCase):
    """Second-call assertions: exactly one FACET unlock row at all times."""

    def test_double_call_is_noop(self) -> None:
        from world.magic.constants import TargetKind
        from world.magic.models.weaving import ThreadWeavingUnlock

        seed_facet_thread_unlock()
        first_count = ThreadWeavingUnlock.objects.filter(
            target_kind=TargetKind.FACET,
        ).count()

        seed_facet_thread_unlock()
        second_count = ThreadWeavingUnlock.objects.filter(
            target_kind=TargetKind.FACET,
        ).count()

        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 1)
