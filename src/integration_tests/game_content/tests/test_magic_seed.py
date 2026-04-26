"""Tests for seed_magic_config() — Task 1.1.

Verifies:
1. All 5 singletons + IntensityTier rows + MishapPoolTier are created with
   expected values on the first call.
2. A second call produces zero new DB writes (idempotent).
3. Staff edits to existing rows survive a re-run (get_or_create, not update_or_create).
"""

from django.test import TestCase

from integration_tests.game_content.magic import MagicConfigResult, seed_magic_config


class TestSeedMagicConfigCreation(TestCase):
    """First-call assertions: correct rows exist with expected values."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.result: MagicConfigResult = seed_magic_config()

    def test_anima_config_created(self) -> None:
        from world.magic.models import AnimaConfig

        self.assertEqual(AnimaConfig.objects.count(), 1)
        cfg = AnimaConfig.objects.get(pk=1)
        self.assertEqual(cfg.daily_regen_percent, 5)
        self.assertEqual(cfg.daily_regen_blocking_property_key, "blocks_anima_regen")
        self.assertEqual(self.result.anima_config.pk, 1)

    def test_soulfray_config_created(self) -> None:
        from world.magic.models import SoulfrayConfig

        self.assertEqual(SoulfrayConfig.objects.count(), 1)
        cfg = SoulfrayConfig.objects.get(pk=1)
        self.assertIsNotNone(cfg.resilience_check_type)
        self.assertEqual(cfg.resilience_check_type.name, "Magical Endurance")
        self.assertEqual(self.result.soulfray_config.pk, 1)

    def test_resonance_gain_config_created(self) -> None:
        from world.magic.models.gain_config import ResonanceGainConfig

        self.assertEqual(ResonanceGainConfig.objects.count(), 1)
        self.assertEqual(self.result.resonance_gain_config.pk, 1)

    def test_corruption_config_created(self) -> None:
        from world.magic.models.corruption_config import CorruptionConfig

        self.assertEqual(CorruptionConfig.objects.count(), 1)
        self.assertEqual(self.result.corruption_config.pk, 1)

    def test_audere_threshold_created(self) -> None:
        from world.magic.audere import AudereThreshold

        self.assertEqual(AudereThreshold.objects.count(), 1)
        threshold = AudereThreshold.objects.get(pk=1)
        self.assertEqual(threshold.intensity_bonus, 20)
        self.assertEqual(threshold.anima_pool_bonus, 30)
        self.assertEqual(threshold.warp_multiplier, 2)
        # minimum_intensity_tier should be "Major"
        self.assertEqual(threshold.minimum_intensity_tier.name, "Major")
        # minimum_warp_stage should be "Ripping" (stage_order=3)
        self.assertEqual(threshold.minimum_warp_stage.name, "Ripping")
        self.assertEqual(self.result.audere_threshold.pk, 1)

    def test_intensity_tiers_created(self) -> None:
        from world.magic.models import IntensityTier

        self.assertEqual(IntensityTier.objects.count(), 3)
        minor = IntensityTier.objects.get(name="Minor")
        moderate = IntensityTier.objects.get(name="Moderate")
        major = IntensityTier.objects.get(name="Major")
        self.assertEqual(minor.threshold, 5)
        self.assertEqual(moderate.threshold, 10)
        self.assertEqual(major.threshold, 15)
        self.assertIn("Minor", self.result.intensity_tiers)
        self.assertIn("Moderate", self.result.intensity_tiers)
        self.assertIn("Major", self.result.intensity_tiers)

    def test_mishap_pool_tier_created(self) -> None:
        from world.magic.models import MishapPoolTier

        self.assertEqual(MishapPoolTier.objects.count(), 1)
        tier = MishapPoolTier.objects.get(min_deficit=1, max_deficit__isnull=True)
        self.assertIsNotNone(tier.consequence_pool)
        self.assertEqual(tier.consequence_pool.name, "Magic Mishap Pool (default)")
        self.assertEqual(self.result.mishap_pool_tier.pk, tier.pk)


class TestSeedMagicConfigIdempotency(TestCase):
    """Second-call assertions: row counts unchanged, same PKs returned."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.first: MagicConfigResult = seed_magic_config()
        cls.second: MagicConfigResult = seed_magic_config()

    def _counts(self) -> dict[str, int]:
        from world.checks.models import CheckCategory, CheckType
        from world.conditions.models import ConditionStage, ConditionTemplate
        from world.magic.audere import AudereThreshold
        from world.magic.models import AnimaConfig, IntensityTier, MishapPoolTier, SoulfrayConfig
        from world.magic.models.corruption_config import CorruptionConfig
        from world.magic.models.gain_config import ResonanceGainConfig

        return {
            "anima_config": AnimaConfig.objects.count(),
            "soulfray_config": SoulfrayConfig.objects.count(),
            "resonance_gain_config": ResonanceGainConfig.objects.count(),
            "corruption_config": CorruptionConfig.objects.count(),
            "audere_threshold": AudereThreshold.objects.count(),
            "intensity_tiers": IntensityTier.objects.count(),
            "mishap_pool_tiers": MishapPoolTier.objects.count(),
            "check_types": CheckType.objects.count(),
            "check_categories": CheckCategory.objects.count(),
            "condition_templates": ConditionTemplate.objects.count(),
            "condition_stages": ConditionStage.objects.count(),
        }

    def test_row_counts_unchanged(self) -> None:
        counts = self._counts()
        self.assertEqual(counts["anima_config"], 1)
        self.assertEqual(counts["soulfray_config"], 1)
        self.assertEqual(counts["resonance_gain_config"], 1)
        self.assertEqual(counts["corruption_config"], 1)
        self.assertEqual(counts["audere_threshold"], 1)
        self.assertEqual(counts["intensity_tiers"], 3)
        self.assertEqual(counts["mishap_pool_tiers"], 1)
        # Guard against orphan CheckType/CheckCategory rows leaking on re-run
        self.assertEqual(
            counts["check_types"],
            1,
            "seed_magic_config() must not create extra CheckType rows on second call",
        )
        self.assertEqual(
            counts["check_categories"],
            1,
            "seed_magic_config() must not create extra CheckCategory rows on second call",
        )
        # Guard against ConditionTemplate/ConditionStage leaking on re-run
        self.assertEqual(
            counts["condition_templates"],
            1,
            "seed_magic_config() must not create extra ConditionTemplate rows on second call",
        )
        self.assertEqual(
            counts["condition_stages"],
            5,
            "seed_magic_config() must not create extra ConditionStage rows on second call",
        )

    def test_same_pks_returned(self) -> None:
        self.assertEqual(self.first.anima_config.pk, self.second.anima_config.pk)
        self.assertEqual(self.first.soulfray_config.pk, self.second.soulfray_config.pk)
        self.assertEqual(self.first.resonance_gain_config.pk, self.second.resonance_gain_config.pk)
        self.assertEqual(self.first.corruption_config.pk, self.second.corruption_config.pk)
        self.assertEqual(self.first.audere_threshold.pk, self.second.audere_threshold.pk)
        self.assertEqual(self.first.mishap_pool_tier.pk, self.second.mishap_pool_tier.pk)

    def test_intensity_tier_pks_unchanged(self) -> None:
        for name in ("Minor", "Moderate", "Major"):
            self.assertEqual(
                self.first.intensity_tiers[name].pk,
                self.second.intensity_tiers[name].pk,
                f"IntensityTier '{name}' pk changed on second call",
            )


class TestSeedMagicConfigPreservesEdits(TestCase):
    """Staff edits to existing rows survive a re-run (get_or_create semantics)."""

    def test_edit_preserved_on_rerun(self) -> None:
        from world.magic.models import AnimaConfig

        seed_magic_config()

        # Simulate a staff edit via bulk update (bypasses identity map)
        AnimaConfig.objects.filter(pk=1).update(daily_regen_percent=15)

        # Re-run the seed — must not overwrite the staff edit
        seed_magic_config()

        # Use .values() to bypass SharedMemoryModel identity-map cache and
        # read directly from the DB.
        db_value = AnimaConfig.objects.filter(pk=1).values("daily_regen_percent").get()
        self.assertEqual(
            db_value["daily_regen_percent"],
            15,
            "seed_magic_config() must not overwrite existing rows (get_or_create semantics)",
        )
