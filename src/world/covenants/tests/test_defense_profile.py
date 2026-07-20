"""Tests for CovenantRoleDefenseProfile (#2533, Layer 3)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from world.covenants.constants import DefenseStyle
from world.covenants.factories import (
    CovenantRoleDefenseProfileFactory,
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
)
from world.covenants.models import CovenantRoleDefenseProfile


class CovenantRoleDefenseProfileModelTests(TestCase):
    def test_factory_builds(self) -> None:
        profile = CovenantRoleDefenseProfileFactory(style=DefenseStyle.EVASION)
        self.assertEqual(profile.style, DefenseStyle.EVASION)
        self.assertEqual(profile.gear_additive_tenths, 10)
        self.assertIn(profile.covenant_role.name, str(profile))

    def test_one_profile_per_role(self) -> None:
        role = CovenantRoleFactory()
        CovenantRoleDefenseProfile.objects.create(covenant_role=role, style=DefenseStyle.GEAR_SOAK)
        with self.assertRaises(IntegrityError):
            CovenantRoleDefenseProfile.objects.create(
                covenant_role=role, style=DefenseStyle.BARRIER
            )

    def test_accessible_via_role_defense_profile(self) -> None:
        role = CovenantRoleFactory()
        self.assertFalse(hasattr(role, "defense_profile"))
        profile = CovenantRoleDefenseProfileFactory(covenant_role=role, style=DefenseStyle.BARRIER)
        role.refresh_from_db()
        self.assertEqual(role.defense_profile, profile)

    def test_subrole_row_is_valid(self) -> None:
        """Sub-role defense profiles carry no model-level restriction (#2533).

        Replacement-vs-extension semantics belong to Task 3's resolution
        helper, not to this model's clean().
        """
        sub_role = SubroleCovenantRoleFactory()
        sub_role.full_clean()  # sub-role itself is a valid CovenantRole row

        profile = CovenantRoleDefenseProfileFactory(
            covenant_role=sub_role, style=DefenseStyle.EVASION, gear_additive_tenths=0
        )
        profile.full_clean()  # no restriction on defense profiles for sub-roles
        self.assertEqual(profile.covenant_role_id, sub_role.pk)
        self.assertEqual(profile.gear_additive_tenths, 0)

    def test_gear_additive_tenths_rejects_negative(self) -> None:
        role = CovenantRoleFactory()
        profile = CovenantRoleDefenseProfile(
            covenant_role=role,
            style=DefenseStyle.GEAR_SOAK,
            gear_additive_tenths=-1,
        )
        with self.assertRaises(ValidationError):
            profile.full_clean()
