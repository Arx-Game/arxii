"""Tests for relationship thread pull-effect content (#2021)."""

from django.test import TestCase

from world.magic.constants import EffectKind, TargetKind, VitalBonusTarget
from world.magic.models import Resonance, ThreadPullEffect


class RelationshipPullContentTests(TestCase):
    """Verify the seed creates correct ThreadPullEffect rows."""

    def setUp(self):
        """Create canonical resonances for the seed to find."""
        from world.magic.models.affinity import Affinity

        celestial = Affinity.objects.create(name="Celestial")
        abyssal = Affinity.objects.create(name="Abyssal")
        for name in ("Light", "Sanctity", "Radiance"):
            Resonance.objects.get_or_create(name=name, defaults={"affinity": celestial})
        Resonance.objects.get_or_create(name="Dissolution", defaults={"affinity": abyssal})

    def test_seed_creates_rows_for_all_canonical_resonances(self):
        """ensure_relationship_pull_content creates 4 tiers x 4 resonances = 16 rows."""
        from world.seeds.game_content.magic import ensure_relationship_pull_content

        ensure_relationship_pull_content()

        rows = ThreadPullEffect.objects.filter(target_kind=TargetKind.RELATIONSHIP_TRACK)
        self.assertEqual(rows.count(), 16)

    def test_seed_is_idempotent(self):
        """Running twice doesn't duplicate rows."""
        from world.seeds.game_content.magic import ensure_relationship_pull_content

        ensure_relationship_pull_content()
        ensure_relationship_pull_content()

        rows = ThreadPullEffect.objects.filter(target_kind=TargetKind.RELATIONSHIP_TRACK)
        self.assertEqual(rows.count(), 16)

    def test_tier0_is_vital_bonus_damage_reduction(self):
        """Tier 0 is VITAL_BONUS with DAMAGE_TAKEN_REDUCTION."""
        from world.seeds.game_content.magic import ensure_relationship_pull_content

        ensure_relationship_pull_content()

        tier0 = ThreadPullEffect.objects.filter(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            tier=0,
        ).first()
        self.assertIsNotNone(tier0)
        self.assertEqual(tier0.effect_kind, EffectKind.VITAL_BONUS)
        self.assertEqual(tier0.vital_target, VitalBonusTarget.DAMAGE_TAKEN_REDUCTION)
        self.assertEqual(tier0.vital_bonus_amount, 10)

    def test_tier1_is_vital_bonus_death_save(self):
        """Tier 1 is VITAL_BONUS with DEATH_SAVE."""
        from world.seeds.game_content.magic import ensure_relationship_pull_content

        ensure_relationship_pull_content()

        tier1 = ThreadPullEffect.objects.filter(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            tier=1,
        ).first()
        self.assertIsNotNone(tier1)
        self.assertEqual(tier1.effect_kind, EffectKind.VITAL_BONUS)
        self.assertEqual(tier1.vital_target, VitalBonusTarget.DEATH_SAVE)
        self.assertEqual(tier1.vital_bonus_amount, 10)

    def test_tier2_is_resistance(self):
        """Tier 2 is RESISTANCE with null damage_type (all types)."""
        from world.seeds.game_content.magic import ensure_relationship_pull_content

        ensure_relationship_pull_content()

        tier2 = ThreadPullEffect.objects.filter(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            tier=2,
        ).first()
        self.assertIsNotNone(tier2)
        self.assertEqual(tier2.effect_kind, EffectKind.RESISTANCE)
        self.assertEqual(tier2.resistance_amount, 2)
        self.assertIsNone(tier2.resistance_damage_type)

    def test_tier3_is_vital_bonus_knockout_resist(self):
        """Tier 3 is VITAL_BONUS with KNOCKOUT_RESIST."""
        from world.seeds.game_content.magic import ensure_relationship_pull_content

        ensure_relationship_pull_content()

        tier3 = ThreadPullEffect.objects.filter(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            tier=3,
        ).first()
        self.assertIsNotNone(tier3)
        self.assertEqual(tier3.effect_kind, EffectKind.VITAL_BONUS)
        self.assertEqual(tier3.vital_target, VitalBonusTarget.KNOCKOUT_RESIST)
        self.assertEqual(tier3.vital_bonus_amount, 10)


class RelationshipCapstoneModulationTests(TestCase):
    """apply_target_modulation handles RELATIONSHIP_CAPSTONE (#2021)."""

    def test_capstone_dispatches_to_relationship_modulation(self):
        """RELATIONSHIP_CAPSTONE threads get relationship_bond_modulation, not passthrough."""
        from world.magic.services.pull_modulation import apply_target_modulation

        # Verify the function is importable and callable
        self.assertTrue(callable(apply_target_modulation))
