from django.test import SimpleTestCase

from world.magic.constants import (
    SHIP_VITAL_BONUS_TARGETS,
    EffectKind,
    RitualExecutionKind,
    SoulTetherRole,
    TargetKind,
    VitalBonusTarget,
)


class TargetKindTests(SimpleTestCase):
    def test_target_kinds(self):
        self.assertEqual(
            set(TargetKind.values),
            {
                "TRAIT",
                "TECHNIQUE",
                "FACET",
                "RELATIONSHIP_TRACK",
                "RELATIONSHIP_CAPSTONE",
                "COVENANT_ROLE",
                "GIFT",
                "MANTLE",
                "SANCTUM",
                "ORGANIZATION",
            },
        )


class EffectKindTests(SimpleTestCase):
    def test_effect_kinds(self) -> None:
        self.assertEqual(
            set(EffectKind.values),
            {
                "FLAT_BONUS",
                "INTENSITY_BUMP",
                "VITAL_BONUS",
                "CAPABILITY_GRANT",
                "NARRATIVE_ONLY",
                "CORRUPTION_RESISTANCE",
                "ASSUME_ALTERNATE_SELF",
                "RESISTANCE",
            },
        )


class VitalBonusTargetTests(SimpleTestCase):
    CHARACTER_TARGETS = {
        "MAX_HEALTH",
        "DAMAGE_TAKEN_REDUCTION",
        "DEATH_SAVE",
        "KNOCKOUT_RESIST",
        "PERMANENT_WOUND_RESIST",
    }
    SHIP_TARGETS = {"SHIP_HULL", "SHIP_HANDLING", "SHIP_ARMAMENT"}

    def test_vital_bonus_targets(self):
        self.assertEqual(
            set(VitalBonusTarget.values),
            self.CHARACTER_TARGETS | self.SHIP_TARGETS,
        )

    def test_ship_targets_are_partitioned_from_character_vitals(self) -> None:
        """``SHIP_VITAL_BONUS_TARGETS`` is exactly the non-character half (#2736).

        The ship targets name a *vessel's* stats and are read only by
        ``world/ships/sanctum_bonus.py``; every character-side reader must skip them.
        A new member added to this enum belongs in exactly one half, and the
        membership set is what ``passive_vital_bonuses`` gates on — so an addition
        that lands in neither would silently be treated as a character vital.
        """
        self.assertEqual(set(SHIP_VITAL_BONUS_TARGETS), self.SHIP_TARGETS)
        self.assertEqual(
            set(VitalBonusTarget.values) - set(SHIP_VITAL_BONUS_TARGETS),
            self.CHARACTER_TARGETS,
        )


class RitualExecutionKindTests(SimpleTestCase):
    def test_execution_kinds(self):
        self.assertEqual(
            set(RitualExecutionKind.values), {"SERVICE", "FLOW", "SCENE_ACTION", "CEREMONY"}
        )


class SoulTetherRoleTests(SimpleTestCase):
    def test_two_roles(self):
        self.assertEqual(set(SoulTetherRole.values), {"SINEATER", "SINNER"})


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
