"""Tests for CovenantRole sub-role fields: clean() validation and unique constraint."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
)
from world.covenants.models import CovenantRole
from world.magic.factories import ResonanceFactory


class SubroleCleanValidationTests(TestCase):
    """Test clean() rules for CovenantRole sub-role fields."""

    def test_parent_role_only_is_invalid(self) -> None:
        """parent_role set but resonance null → invalid (XOR rule)."""
        parent = CovenantRoleFactory()
        role = CovenantRoleFactory.build(
            parent_role=parent,
            resonance=None,
            unlock_thread_level=3,
            covenant_type=parent.covenant_type,
            sword_weight=0,
            shield_weight=0,
            crown_weight=0,
        )
        with self.assertRaises(ValidationError):
            role.full_clean()

    def test_resonance_only_is_invalid(self) -> None:
        """resonance set but parent_role null → invalid (XOR rule)."""
        resonance = ResonanceFactory()
        role = CovenantRoleFactory.build(
            parent_role=None,
            resonance=resonance,
            unlock_thread_level=3,
        )
        with self.assertRaises(ValidationError):
            role.full_clean()

    def test_primary_role_is_valid(self) -> None:
        """Both parent_role and resonance null → valid primary role."""
        role = CovenantRoleFactory.build(
            parent_role=None,
            resonance=None,
            unlock_thread_level=0,
        )
        role.full_clean()  # should not raise

    def test_sub_role_is_valid(self) -> None:
        """Both parent_role and resonance set with unlock_thread_level > 0 → valid."""
        parent = CovenantRoleFactory()
        resonance = ResonanceFactory()
        role = CovenantRoleFactory.build(
            parent_role=parent,
            resonance=resonance,
            unlock_thread_level=3,
            covenant_type=parent.covenant_type,
            sword_weight=0,
            shield_weight=0,
            crown_weight=0,
        )
        role.full_clean()  # should not raise

    def test_unlock_thread_level_nonzero_on_primary_role_is_invalid(self) -> None:
        """Primary role (no parent_role/resonance) with unlock_thread_level > 0 → invalid."""
        role = CovenantRoleFactory.build(
            parent_role=None,
            resonance=None,
            unlock_thread_level=3,
        )
        with self.assertRaises(ValidationError) as ctx:
            role.full_clean()
        self.assertIn("unlock_thread_level", ctx.exception.message_dict)

    def test_sub_role_unlock_thread_level_zero_is_invalid(self) -> None:
        """Sub-role (both FKs set) with unlock_thread_level=0 → invalid."""
        parent = CovenantRoleFactory()
        resonance = ResonanceFactory()
        role = CovenantRoleFactory.build(
            parent_role=parent,
            resonance=resonance,
            unlock_thread_level=0,
            covenant_type=parent.covenant_type,
            sword_weight=0,
            shield_weight=0,
            crown_weight=0,
        )
        with self.assertRaises(ValidationError) as ctx:
            role.full_clean()
        self.assertIn("unlock_thread_level", ctx.exception.message_dict)

    def test_covenant_type_must_match_parent(self) -> None:
        """Sub-role covenant_type differs from parent → invalid."""
        parent = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        resonance = ResonanceFactory()
        role = CovenantRoleFactory.build(
            parent_role=parent,
            resonance=resonance,
            unlock_thread_level=3,
            covenant_type=CovenantType.BATTLE,
            sword_weight=0,
            shield_weight=0,
            crown_weight=0,
        )
        with self.assertRaises(ValidationError) as ctx:
            role.full_clean()
        self.assertIn("covenant_type", ctx.exception.message_dict)

    def test_sub_role_blend_weights_are_rejected(self) -> None:
        """Sub-role setting any blend weight → invalid (#2529: blend lives on parent only)."""
        parent = CovenantRoleFactory()
        resonance = ResonanceFactory()
        role = CovenantRoleFactory.build(
            parent_role=parent,
            resonance=resonance,
            unlock_thread_level=3,
            covenant_type=parent.covenant_type,
            sword_weight=1,
            shield_weight=0,
            crown_weight=0,
        )
        with self.assertRaises(ValidationError) as ctx:
            role.full_clean()
        self.assertIn("sword_weight", ctx.exception.message_dict)

    def test_single_depth_inheritance_enforced(self) -> None:
        """parent_role itself already has a parent_role → sub-sub-role forbidden."""
        grandparent = CovenantRoleFactory()
        parent = SubroleCovenantRoleFactory(
            parent_role=grandparent,
            covenant_type=grandparent.covenant_type,
        )
        resonance = ResonanceFactory()
        role = CovenantRoleFactory.build(
            parent_role=parent,
            resonance=resonance,
            unlock_thread_level=3,
            covenant_type=parent.covenant_type,
            sword_weight=0,
            shield_weight=0,
            crown_weight=0,
        )
        with self.assertRaises(ValidationError) as ctx:
            role.full_clean()
        self.assertIn("parent_role", ctx.exception.message_dict)


class SubroleUniqueConstraintTests(TestCase):
    """Test unique constraint on (parent_role, resonance, unlock_thread_level) for sub-roles."""

    def test_unique_per_parent_resonance_level(self) -> None:
        """Duplicate (parent_role, resonance, unlock_thread_level) → IntegrityError."""
        parent = CovenantRoleFactory()
        resonance = ResonanceFactory()
        SubroleCovenantRoleFactory(
            parent_role=parent,
            resonance=resonance,
            unlock_thread_level=3,
            covenant_type=parent.covenant_type,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            CovenantRole.objects.create(
                name="Different Name",
                slug="different-slug",
                covenant_type=parent.covenant_type,
                speed_rank=parent.speed_rank,
                parent_role=parent,
                resonance=resonance,
                unlock_thread_level=3,
            )

    def test_different_unlock_level_coexists(self) -> None:
        """Same (parent, resonance) but different unlock_thread_level → both OK."""
        parent = CovenantRoleFactory()
        resonance = ResonanceFactory()
        SubroleCovenantRoleFactory(
            parent_role=parent,
            resonance=resonance,
            unlock_thread_level=3,
            covenant_type=parent.covenant_type,
        )
        # Different level should not conflict
        higher_tier = CovenantRole.objects.create(
            name="Higher Tier",
            slug="higher-tier",
            covenant_type=parent.covenant_type,
            speed_rank=parent.speed_rank,
            parent_role=parent,
            resonance=resonance,
            unlock_thread_level=6,
        )
        self.assertEqual(higher_tier.unlock_thread_level, 6)

    def test_primary_roles_unaffected_by_partial_constraint(self) -> None:
        """Two primary roles (both parent_role=null) should not collide via the partial constraint.

        The constraint is WHERE parent_role IS NOT NULL, so primary roles are excluded.
        """
        role_a = CovenantRoleFactory(
            name="Role A",
            slug="role-a",
            covenant_type=CovenantType.DURANCE,
        )
        role_b = CovenantRoleFactory(
            name="Role B",
            slug="role-b",
            covenant_type=CovenantType.DURANCE,
        )
        # Both are primary roles — partial constraint (WHERE parent_role IS NOT NULL) excludes them
        self.assertIsNone(role_a.parent_role_id)
        self.assertIsNone(role_b.parent_role_id)
        # Both exist without IntegrityError
        self.assertEqual(CovenantRole.objects.filter(pk__in=[role_a.pk, role_b.pk]).count(), 2)
