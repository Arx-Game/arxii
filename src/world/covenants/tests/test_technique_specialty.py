"""Tests for CovenantRoleTechniqueSpecialty (#2443).

Layer 2 of the vow-power model: per-vow finer-technique specialty rows keyed
by ``(covenant_role, function)``. Unlike the SWORD/SHIELD/CROWN blend weights
(primary-role-only), specialty rows are valid on BOTH primary roles and
sub-roles — a sub-role may carry its own rows that ADD on top of anything
inherited from the parent role, so there is no all-zero-weights-style
clean() restriction here.
"""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CovenantRoleFactory,
    CovenantRoleTechniqueSpecialtyFactory,
    SubroleCovenantRoleFactory,
)
from world.covenants.models import CovenantRoleTechniqueSpecialty
from world.magic.constants import TechniqueFunction


class CovenantRoleTechniqueSpecialtyModelTests(TestCase):
    def test_str_uses_role_name_and_function_display(self) -> None:
        specialty = CovenantRoleTechniqueSpecialtyFactory(
            covenant_role__name="Vanguard",
            function=TechniqueFunction.WEAKEN,
            multiplier_tenths=15,
        )
        self.assertEqual(str(specialty), "Vanguard + Weaken: ×1.5")

    def test_default_multiplier_tenths_is_ten(self) -> None:
        specialty = CovenantRoleTechniqueSpecialtyFactory()
        self.assertEqual(specialty.multiplier_tenths, 10)

    def test_multiple_specialties_per_role(self) -> None:
        """A role may carry several function specialties."""
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1)
        CovenantRoleTechniqueSpecialtyFactory(covenant_role=role, function=TechniqueFunction.WEAKEN)
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=role, function=TechniqueFunction.DAMAGE_BUFF_SELF
        )

        self.assertEqual(role.technique_specialties.count(), 2)
        functions = set(role.technique_specialties.values_list("function", flat=True))
        self.assertEqual(functions, {TechniqueFunction.WEAKEN, TechniqueFunction.DAMAGE_BUFF_SELF})

    def test_unique_function_per_role(self) -> None:
        """The same function cannot be attached twice to the same role."""
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1)
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=role, function=TechniqueFunction.BARRIER
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            CovenantRoleTechniqueSpecialty.objects.create(
                covenant_role=role, function=TechniqueFunction.BARRIER
            )

    def test_same_function_allowed_on_different_roles(self) -> None:
        """Uniqueness is scoped per-role, not global."""
        first = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1)
        second = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1)
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=first, function=TechniqueFunction.BARRIER
        )
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=second, function=TechniqueFunction.BARRIER
        )

        self.assertEqual(
            CovenantRoleTechniqueSpecialty.objects.filter(
                function=TechniqueFunction.BARRIER
            ).count(),
            2,
        )

    def test_cascade_deletes_with_covenant_role(self) -> None:
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1)
        CovenantRoleTechniqueSpecialtyFactory(covenant_role=role, function=TechniqueFunction.CHARM)

        role.delete()

        self.assertEqual(CovenantRoleTechniqueSpecialty.objects.count(), 0)

    def test_valid_on_primary_role(self) -> None:
        """A specialty row on a primary role's full_clean() passes."""
        role = CovenantRoleFactory(
            covenant_type=CovenantType.DURANCE, sword_weight=1, crown_weight=0
        )
        role.full_clean()  # sanity: primary role itself is valid

        specialty = CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=role, function=TechniqueFunction.MOBILITY
        )
        specialty.full_clean()

    def test_valid_on_sub_role(self) -> None:
        """A specialty row on a valid sub-role full_clean()s cleanly.

        Sub-role: parent+resonance set, unlock_thread_level>0, zero blend
        weights. Proves specialty rows are not restricted to primary roles.
        """
        parent = CovenantRoleFactory(covenant_type=CovenantType.DURANCE, sword_weight=1)
        sub_role = SubroleCovenantRoleFactory(
            parent_role=parent,
            unlock_thread_level=3,
        )
        sub_role.full_clean()  # sanity: the sub-role itself is valid

        specialty = CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=sub_role, function=TechniqueFunction.PERCEPTION
        )
        specialty.full_clean()
