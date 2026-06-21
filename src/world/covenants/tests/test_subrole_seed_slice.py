"""TDD tests for seed_resonance_subrole_slice — Task 6 proof slice.

Asserts the factory helper creates N sub-roles for a single parent role,
each with a distinct resonance, a discovery_achievement, a codex_entry,
and at least one CovenantRoleBonus row.
"""

from django.test import TestCase

from world.covenants.factories import (
    CovenantRoleFactory,
    seed_resonance_subrole_slice,
)
from world.covenants.models import CovenantRoleBonus


class SeedResonanceSubroleSliceTests(TestCase):
    """Tests for seed_resonance_subrole_slice helper."""

    def setUp(self) -> None:
        self.parent = CovenantRoleFactory()
        self.subroles = seed_resonance_subrole_slice(parent_role=self.parent)

    def test_creates_multiple_subroles(self) -> None:
        """Helper returns at least 2 sub-roles."""
        self.assertGreaterEqual(len(self.subroles), 2)

    def test_each_subrole_has_distinct_resonance(self) -> None:
        """All sub-roles have different resonances."""
        resonance_ids = [sr.resonance_id for sr in self.subroles]
        self.assertEqual(len(resonance_ids), len(set(resonance_ids)), "resonances must be distinct")

    def test_each_subrole_has_discovery_achievement(self) -> None:
        """Every sub-role has a discovery_achievement FK set."""
        for sr in self.subroles:
            self.assertIsNotNone(
                sr.discovery_achievement_id,
                f"Sub-role {sr} is missing discovery_achievement",
            )

    def test_each_subrole_has_codex_entry(self) -> None:
        """Every sub-role has a codex_entry FK set."""
        for sr in self.subroles:
            self.assertIsNotNone(
                sr.codex_entry_id,
                f"Sub-role {sr} is missing codex_entry",
            )

    def test_each_subrole_has_at_least_one_role_bonus(self) -> None:
        """Every sub-role has at least one CovenantRoleBonus row."""
        for sr in self.subroles:
            bonus_count = CovenantRoleBonus.objects.filter(covenant_role=sr).count()
            self.assertGreaterEqual(
                bonus_count,
                1,
                f"Sub-role {sr} has no CovenantRoleBonus rows",
            )

    def test_subroles_pass_full_clean(self) -> None:
        """All sub-roles satisfy the model's XOR/archetype/type invariants."""
        for sr in self.subroles:
            # Re-fetch so all FK caches are fresh
            sr.refresh_from_db()
            sr.full_clean()

    def test_works_without_explicit_parent(self) -> None:
        """Helper creates its own parent when parent_role is None."""
        result = seed_resonance_subrole_slice()
        self.assertGreaterEqual(len(result), 2)
        parent_ids = {sr.parent_role_id for sr in result}
        self.assertEqual(len(parent_ids), 1, "all sub-roles should share one auto-created parent")

    def test_called_twice_is_idempotent(self) -> None:
        """Calling the helper again with the same parent adds no duplicate sub-roles.

        The helper uses ResonanceFactory with django_get_or_create on name,
        so re-seeding the same parent uses get_or_create semantics and should
        not blow up the unique constraint on (parent_role, resonance, unlock_thread_level).
        """
        # Should not raise (unique constraint violation would panic here)
        second = seed_resonance_subrole_slice(parent_role=self.parent)
        self.assertGreaterEqual(len(second), 2)
