from django.test import SimpleTestCase

from world.magic.constants import (
    THREADWEAVING_ITEM_TYPECLASSES,
    EffectKind,
    RitualExecutionKind,
    SoulTetherRole,
    TargetKind,
    VitalBonusTarget,
)


class TargetKindTests(SimpleTestCase):
    def test_six_target_kinds(self):
        self.assertEqual(
            set(TargetKind.values),
            {"TRAIT", "TECHNIQUE", "ITEM", "ROOM", "RELATIONSHIP_TRACK", "RELATIONSHIP_CAPSTONE"},
        )


class EffectKindTests(SimpleTestCase):
    def test_five_effect_kinds(self):
        self.assertEqual(
            set(EffectKind.values),
            {"FLAT_BONUS", "INTENSITY_BUMP", "VITAL_BONUS", "CAPABILITY_GRANT", "NARRATIVE_ONLY"},
        )


class VitalBonusTargetTests(SimpleTestCase):
    def test_two_launch_targets(self):
        self.assertEqual(
            set(VitalBonusTarget.values),
            {"MAX_HEALTH", "DAMAGE_TAKEN_REDUCTION"},
        )


class RitualExecutionKindTests(SimpleTestCase):
    def test_two_execution_kinds(self):
        self.assertEqual(set(RitualExecutionKind.values), {"SERVICE", "FLOW"})


class SoulTetherRoleTests(SimpleTestCase):
    def test_two_roles(self):
        self.assertEqual(set(SoulTetherRole.values), {"ABYSSAL", "SINEATER"})


class ItemTypeclassRegistryTests(SimpleTestCase):
    def test_registry_is_a_tuple_of_strings(self):
        self.assertIsInstance(THREADWEAVING_ITEM_TYPECLASSES, tuple)
        for path in THREADWEAVING_ITEM_TYPECLASSES:
            self.assertIsInstance(path, str)
            self.assertIn(".", path)  # at least namespaced
