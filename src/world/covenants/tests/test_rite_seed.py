"""Tests for Task 8: Renew the Oath rite seed (factory + wire helper).
Tests for Task 10: scaling default package + role/level bands.

Verifies that:
- CovenantRiteFactory builds a well-formed CovenantRite with the correct
  service function path, ritual name, and UNTIL_END_OF_COMBAT condition.
- wire_covenant_rite_content() is idempotent: two calls yield exactly one
  Ritual row and one CovenantRite row.
- wire_covenant_rite_content() seeds the default package with real
  ConditionModifierEffect rows and role packages across two level bands.
"""

from __future__ import annotations

from django.test import TestCase

from world.conditions.constants import DurationType
from world.conditions.models import ConditionModifierEffect
from world.covenants.factories import CovenantRiteFactory, wire_covenant_rite_content
from world.covenants.models import CovenantRite
from world.magic.models import Ritual


class CovenantRiteFactoryTests(TestCase):
    """CovenantRiteFactory smoke tests."""

    def test_ritual_service_function_path(self) -> None:
        """The backing ritual must dispatch to perform_covenant_rite."""
        rite = CovenantRiteFactory()
        self.assertEqual(
            rite.ritual.service_function_path,
            "world.covenants.services.perform_covenant_rite",
        )

    def test_ritual_name(self) -> None:
        """The backing ritual must be named 'Renew the Oath'."""
        rite = CovenantRiteFactory()
        self.assertEqual(rite.ritual.name, "Renew the Oath")

    def test_granted_condition_duration_type(self) -> None:
        """granted_condition must default to UNTIL_END_OF_COMBAT duration."""
        rite = CovenantRiteFactory()
        self.assertEqual(
            rite.granted_condition.default_duration_type,
            DurationType.UNTIL_END_OF_COMBAT,
        )

    def test_gate_fields(self) -> None:
        """min_covenant_level, min_members_present, base_severity defaults."""
        rite = CovenantRiteFactory()
        self.assertEqual(rite.min_covenant_level, 2)
        self.assertEqual(rite.min_members_present, 2)
        self.assertEqual(rite.base_severity, 2)
        self.assertEqual(rite.severity_per_extra_participant, 1)
        self.assertIsNone(rite.max_severity)

    def test_covenant_type_is_durance(self) -> None:
        """Reference rite scopes to DURANCE covenant type."""
        from world.covenants.constants import CovenantType

        rite = CovenantRiteFactory()
        self.assertEqual(rite.covenant_type, CovenantType.DURANCE)


class WireCovenantRiteContentIdempotencyTests(TestCase):
    """wire_covenant_rite_content() must be idempotent."""

    def test_single_call_creates_ritual_and_rite(self) -> None:
        """One call produces exactly one Ritual and one CovenantRite."""
        wire_covenant_rite_content()
        self.assertEqual(Ritual.objects.filter(name="Renew the Oath").count(), 1)
        self.assertEqual(CovenantRite.objects.filter(ritual__name="Renew the Oath").count(), 1)

    def test_double_call_does_not_duplicate(self) -> None:
        """Two calls still yield exactly one Ritual and one CovenantRite."""
        wire_covenant_rite_content()
        wire_covenant_rite_content()
        self.assertEqual(Ritual.objects.filter(name="Renew the Oath").count(), 1)
        self.assertEqual(CovenantRite.objects.filter(ritual__name="Renew the Oath").count(), 1)

    def test_returns_covenant_rite(self) -> None:
        """wire_covenant_rite_content returns the CovenantRite instance."""
        result = wire_covenant_rite_content()
        self.assertIsInstance(result, CovenantRite)
        self.assertEqual(result.ritual.name, "Renew the Oath")


class WireCovenantRiteContentPackagesTests(TestCase):
    """Task 10: wire_covenant_rite_content seeds scaling default + role/level bands."""

    def test_default_package_has_scaling_modifier_effects(self) -> None:
        """granted_condition has ConditionModifierEffect rows, all scales_with_severity."""
        rite = wire_covenant_rite_content()
        default_effects = ConditionModifierEffect.objects.filter(condition=rite.granted_condition)
        self.assertTrue(default_effects.exists(), "Default condition must have modifier effects.")
        self.assertTrue(
            all(e.scales_with_severity for e in default_effects),
            "All default modifier effects must scale with severity.",
        )

    def test_default_package_covers_resolve_cluster(self) -> None:
        """granted_condition covers willpower, composure, and stability."""
        rite = wire_covenant_rite_content()
        effect_stat_names = set(
            ConditionModifierEffect.objects.filter(condition=rite.granted_condition).values_list(
                "modifier_target__name", flat=True
            )
        )
        self.assertIn("willpower", effect_stat_names)
        self.assertIn("composure", effect_stat_names)
        self.assertIn("stability", effect_stat_names)

    def test_role_packages_level_1_bands_exist(self) -> None:
        """At least one role package at min_covenant_level=1 is present."""
        rite = wire_covenant_rite_content()
        self.assertTrue(
            rite.role_packages.filter(min_covenant_level=1).exists(),
            "At least one level-1 role package must be seeded.",
        )

    def test_role_packages_higher_level_band_exists(self) -> None:
        """At least one role package at min_covenant_level >= 2 is present (Fury II at 4)."""
        rite = wire_covenant_rite_content()
        self.assertTrue(
            rite.role_packages.filter(min_covenant_level__gte=2).exists(),
            "At least one higher-level role package (e.g. level 4 Sword) must be seeded.",
        )

    def test_sword_has_two_level_bands(self) -> None:
        """Sword role has packages at level 1 (Fury I) and level 4 (Fury II)."""
        rite = wire_covenant_rite_content()
        sword_pkgs = rite.role_packages.filter(covenant_role__slug="sword-vanguard").values_list(
            "min_covenant_level", flat=True
        )
        self.assertIn(1, list(sword_pkgs), "Sword must have a level-1 band (Oathbound Fury I).")
        self.assertIn(4, list(sword_pkgs), "Sword must have a level-4 band (Oathbound Fury II).")

    def test_role_package_conditions_have_scaling_effects(self) -> None:
        """Every role-package ConditionTemplate has at least one scaling modifier effect."""
        rite = wire_covenant_rite_content()
        for pkg in rite.role_packages.select_related("condition_template"):
            effects = ConditionModifierEffect.objects.filter(condition=pkg.condition_template)
            self.assertTrue(
                effects.exists(),
                f"Package '{pkg.condition_template.name}' must have modifier effects.",
            )
            self.assertTrue(
                all(e.scales_with_severity for e in effects),
                f"All effects in '{pkg.condition_template.name}' must scale with severity.",
            )

    def test_idempotency_does_not_duplicate_role_packages(self) -> None:
        """Two calls to wire_covenant_rite_content produce the same number of role packages."""
        rite = wire_covenant_rite_content()
        count_after_first = rite.role_packages.count()
        wire_covenant_rite_content()
        self.assertEqual(
            rite.role_packages.count(),
            count_after_first,
            "Second call must not duplicate role packages.",
        )

    def test_idempotency_does_not_duplicate_modifier_effects(self) -> None:
        """Two calls produce the same number of ConditionModifierEffect rows on the default."""
        rite = wire_covenant_rite_content()
        count_after_first = ConditionModifierEffect.objects.filter(
            condition=rite.granted_condition
        ).count()
        wire_covenant_rite_content()
        self.assertEqual(
            ConditionModifierEffect.objects.filter(condition=rite.granted_condition).count(),
            count_after_first,
            "Second call must not duplicate default-condition modifier effects.",
        )
