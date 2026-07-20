"""Tests for the SWORD/SHIELD/CROWN combat-identity blend on CovenantRole (#2529).

Covers the replacement of the single ``archetype`` enum with three weighted
axes (``sword_weight``/``shield_weight``/``crown_weight``), the validation
rules that keep the blend authored on primary roles only, ``blend_weight_for``'s
sub-role-reads-parent delegation, and the ``CovenantRoleActionScaling`` unique
constraint (the ``(covenant_role, action_key)``-keyed replacement for the old
archetype-keyed ``ArchetypeActionScaling``).
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.covenants.constants import RoleArchetype
from world.covenants.factories import (
    CovenantRoleActionScalingFactory,
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
)
from world.covenants.models import CovenantRoleActionScaling
from world.magic.factories import ResonanceFactory


class BlendWeightValidationTests(TestCase):
    """Primary-role clean() validation for the three blend weight fields."""

    def test_primary_role_weights_summing_to_one_passes_full_clean(self) -> None:
        role = CovenantRoleFactory.build(
            sword_weight=Decimal("0.5"),
            shield_weight=Decimal("0.3"),
            crown_weight=Decimal("0.2"),
        )
        role.full_clean()  # must not raise

    def test_primary_role_weights_summing_to_half_raises(self) -> None:
        role = CovenantRoleFactory.build(
            sword_weight=Decimal("0.5"),
            shield_weight=0,
            crown_weight=0,
        )
        with self.assertRaises(ValidationError) as ctx:
            role.full_clean()
        self.assertIn("sword_weight", ctx.exception.message_dict)

    def test_primary_role_weight_over_one_raises(self) -> None:
        role = CovenantRoleFactory.build(
            sword_weight=Decimal("1.2"),
            shield_weight=0,
            crown_weight=0,
        )
        with self.assertRaises(ValidationError) as ctx:
            role.full_clean()
        self.assertIn("sword_weight", ctx.exception.message_dict)

    def test_primary_role_negative_weight_raises(self) -> None:
        role = CovenantRoleFactory.build(
            sword_weight=Decimal("-0.5"),
            shield_weight=Decimal("1.5"),
            crown_weight=0,
        )
        with self.assertRaises(ValidationError) as ctx:
            role.full_clean()
        self.assertIn("sword_weight", ctx.exception.message_dict)

    def test_sub_role_with_nonzero_weight_raises(self) -> None:
        parent = CovenantRoleFactory()
        role = SubroleCovenantRoleFactory.build(
            parent_role=parent,
            resonance=ResonanceFactory(),
            covenant_type=parent.covenant_type,
            sword_weight=Decimal("0.1"),
        )
        with self.assertRaises(ValidationError) as ctx:
            role.full_clean()
        self.assertIn("sword_weight", ctx.exception.message_dict)

    def test_sub_role_with_zero_weights_passes(self) -> None:
        parent = CovenantRoleFactory()
        role = SubroleCovenantRoleFactory.build(
            parent_role=parent,
            resonance=ResonanceFactory(),
            covenant_type=parent.covenant_type,
        )
        role.full_clean()  # must not raise


class BlendWeightForTests(TestCase):
    """``CovenantRole.blend_weight_for`` — primary reads own weight, sub-role reads parent's."""

    def test_primary_role_returns_own_weight_per_axis(self) -> None:
        role = CovenantRoleFactory(
            sword_weight=Decimal("0.5"),
            shield_weight=Decimal("0.3"),
            crown_weight=Decimal("0.2"),
        )
        self.assertEqual(role.blend_weight_for(RoleArchetype.SWORD), Decimal("0.5"))
        self.assertEqual(role.blend_weight_for(RoleArchetype.SHIELD), Decimal("0.3"))
        self.assertEqual(role.blend_weight_for(RoleArchetype.CROWN), Decimal("0.2"))

    def test_sub_role_delegates_to_parent_weight_per_axis(self) -> None:
        parent = CovenantRoleFactory(
            sword_weight=Decimal("0.5"),
            shield_weight=Decimal("0.3"),
            crown_weight=Decimal("0.2"),
        )
        subrole = SubroleCovenantRoleFactory(
            parent_role=parent,
            covenant_type=parent.covenant_type,
        )
        self.assertEqual(subrole.blend_weight_for(RoleArchetype.SWORD), Decimal("0.5"))
        self.assertEqual(subrole.blend_weight_for(RoleArchetype.SHIELD), Decimal("0.3"))
        self.assertEqual(subrole.blend_weight_for(RoleArchetype.CROWN), Decimal("0.2"))

    def test_unknown_axis_returns_zero(self) -> None:
        role = CovenantRoleFactory(crown_weight=1)
        self.assertEqual(role.blend_weight_for("not-an-axis"), Decimal(0))


class CovenantRoleActionScalingTests(TestCase):
    """CovenantRoleActionScaling unique constraint on (covenant_role, action_key)."""

    def test_unique_per_covenant_role_and_action_key(self) -> None:
        role = CovenantRoleFactory()
        CovenantRoleActionScaling.objects.create(
            covenant_role=role,
            action_key="combat_interpose",
            thread_level_multiplier=Decimal("0.10"),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            CovenantRoleActionScaling.objects.create(
                covenant_role=role,
                action_key="combat_interpose",
                thread_level_multiplier=Decimal("0.20"),
            )

    def test_same_action_key_different_role_allowed(self) -> None:
        role_a = CovenantRoleFactory()
        role_b = CovenantRoleFactory()
        CovenantRoleActionScalingFactory(covenant_role=role_a, action_key="combat_rally")
        # Should not raise — different covenant_role, same action_key.
        CovenantRoleActionScalingFactory(covenant_role=role_b, action_key="combat_rally")

    def test_str(self) -> None:
        row = CovenantRoleActionScalingFactory(
            action_key="combat_interpose",
            thread_level_multiplier=Decimal("0.10"),
        )
        self.assertIn("combat_interpose", str(row))
        self.assertIn(row.covenant_role.name, str(row))
