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


class GainSourceTests(SimpleTestCase):
    def test_gain_source_values(self) -> None:
        from world.magic.constants import GainSource

        self.assertEqual(GainSource.POSE_ENDORSEMENT, "POSE_ENDORSEMENT")
        self.assertEqual(GainSource.SCENE_ENTRY, "SCENE_ENTRY")
        self.assertEqual(GainSource.ROOM_RESIDENCE, "ROOM_RESIDENCE")
        self.assertEqual(GainSource.OUTFIT_TRICKLE, "OUTFIT_TRICKLE")
        self.assertEqual(GainSource.STAFF_GRANT, "STAFF_GRANT")

    def test_gain_source_label_present(self) -> None:
        from world.magic.constants import GainSource

        self.assertTrue(all(len(label) > 0 for _, label in GainSource.choices))
