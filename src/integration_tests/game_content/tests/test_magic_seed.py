"""Tests for seed_magic_config() — Task 1.1, seed_canonical_rituals() — Task 1.2,
and seed_thread_pull_catalog() — Task 1.3.

Verifies:
1. All 5 singletons + IntensityTier rows + MishapPoolTier are created with
   expected values on the first call (Task 1.1).
2. A second call produces zero new DB writes (idempotent) (Task 1.1).
3. Staff edits to existing rows survive a re-run (get_or_create, not update_or_create) (Task 1.1).
4. Canonical rituals are created with correct names (Task 1.2).
5. Ritual seeding is idempotent and preserves edits (Task 1.2).
6. ThreadPullCost + ThreadPullEffect catalog rows are created correctly (Task 1.3).
7. Thread pull catalog seeding is idempotent (Task 1.3).
8. Staff edits to ThreadPullEffect survive a re-run (Task 1.3).
"""

from django.test import TestCase

from integration_tests.game_content.magic import (
    MagicConfigResult,
    RitualSeedResult,
    ThreadPullCatalogResult,
    seed_canonical_rituals,
    seed_magic_config,
    seed_thread_pull_catalog,
)


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


class TestSeedCanonicalRituals(TestCase):
    """Task 1.2: seed_canonical_rituals() creates idempotent ritual rows."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.result: RitualSeedResult = seed_canonical_rituals()

    def test_creation(self) -> None:
        from world.magic.models import Ritual

        self.assertEqual(Ritual.objects.count(), 2)
        imbuing = Ritual.objects.get(name="Rite of Imbuing")
        atonement = Ritual.objects.get(name="Rite of Atonement")
        self.assertIsNotNone(imbuing)
        self.assertIsNotNone(atonement)
        self.assertEqual(self.result.rite_of_imbuing.name, "Rite of Imbuing")
        self.assertEqual(self.result.rite_of_atonement.name, "Rite of Atonement")

    def test_idempotency(self) -> None:
        from world.magic.models import Ritual

        first = seed_canonical_rituals()
        second = seed_canonical_rituals()

        self.assertEqual(Ritual.objects.count(), 2)
        self.assertEqual(first.rite_of_imbuing.pk, second.rite_of_imbuing.pk)
        self.assertEqual(first.rite_of_atonement.pk, second.rite_of_atonement.pk)

    def test_edit_preserved_on_rerun(self) -> None:
        from world.magic.models import Ritual

        seed_canonical_rituals()

        # Simulate a staff edit via bulk update (bypasses identity map)
        Ritual.objects.filter(name="Rite of Imbuing").update(description="custom description")

        # Re-run the seed — must not overwrite the staff edit
        seed_canonical_rituals()

        # Use .values() to bypass SharedMemoryModel identity-map cache and
        # read directly from the DB.
        db_value = Ritual.objects.filter(name="Rite of Imbuing").values("description").get()
        self.assertEqual(
            db_value["description"],
            "custom description",
            "seed_canonical_rituals() must not overwrite existing rows (get_or_create semantics)",
        )


# ---------------------------------------------------------------------------
# Task 1.3 — seed_thread_pull_catalog()
# ---------------------------------------------------------------------------


class TestSeedThreadPullCatalogCreation(TestCase):
    """First-call assertions: correct rows exist with expected values."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.result: ThreadPullCatalogResult = seed_thread_pull_catalog()

    def test_pull_costs_created(self) -> None:
        from world.magic.models.threads import ThreadPullCost

        self.assertEqual(ThreadPullCost.objects.count(), 3)
        tier1 = ThreadPullCost.objects.get(tier=1)
        tier2 = ThreadPullCost.objects.get(tier=2)
        tier3 = ThreadPullCost.objects.get(tier=3)

        self.assertEqual(tier1.resonance_cost, 1)
        self.assertEqual(tier1.anima_per_thread, 1)
        self.assertEqual(tier1.label, "soft")

        self.assertEqual(tier2.resonance_cost, 3)
        self.assertEqual(tier2.anima_per_thread, 2)
        self.assertEqual(tier2.label, "medium")

        self.assertEqual(tier3.resonance_cost, 6)
        self.assertEqual(tier3.anima_per_thread, 3)
        self.assertEqual(tier3.label, "hard")

        self.assertIn(1, self.result.pull_costs)
        self.assertIn(2, self.result.pull_costs)
        self.assertIn(3, self.result.pull_costs)

    def test_pull_effects_created(self) -> None:
        from world.magic.constants import EffectKind
        from world.magic.models.threads import ThreadPullEffect

        self.assertEqual(ThreadPullEffect.objects.count(), 4)

        self.assertIn(EffectKind.FLAT_BONUS, self.result.pull_effects)
        self.assertIn(EffectKind.INTENSITY_BUMP, self.result.pull_effects)
        self.assertIn(EffectKind.VITAL_BONUS, self.result.pull_effects)
        self.assertIn(EffectKind.CAPABILITY_GRANT, self.result.pull_effects)

        flat = self.result.pull_effects[EffectKind.FLAT_BONUS]
        self.assertEqual(flat.tier, 1)
        self.assertEqual(flat.flat_bonus_amount, 2)

        bump = self.result.pull_effects[EffectKind.INTENSITY_BUMP]
        self.assertEqual(bump.tier, 2)
        self.assertEqual(bump.intensity_bump_amount, 1)

        vital = self.result.pull_effects[EffectKind.VITAL_BONUS]
        self.assertEqual(vital.tier, 0)
        self.assertEqual(vital.vital_bonus_amount, 5)
        from world.magic.constants import VitalBonusTarget

        self.assertEqual(vital.vital_target, VitalBonusTarget.MAX_HEALTH)

        cap_grant = self.result.pull_effects[EffectKind.CAPABILITY_GRANT]
        self.assertEqual(cap_grant.tier, 3)
        self.assertEqual(cap_grant.min_thread_level, 5)
        self.assertIsNotNone(cap_grant.capability_grant)
        self.assertEqual(cap_grant.capability_grant.name, "endurance")

    def test_canonical_resonance_authored(self) -> None:
        from world.magic.models import Affinity, Resonance

        self.assertEqual(Resonance.objects.filter(name="Tideborne").count(), 1)
        self.assertEqual(Affinity.objects.filter(name="Primal (Tideborne)").count(), 1)
        self.assertEqual(self.result.canonical_resonance.name, "Tideborne")
        self.assertEqual(self.result.canonical_resonance.affinity.name, "Primal (Tideborne)")


class TestSeedThreadPullCatalogIdempotency(TestCase):
    """Second-call assertions: row counts unchanged, same PKs returned."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.first: ThreadPullCatalogResult = seed_thread_pull_catalog()
        cls.second: ThreadPullCatalogResult = seed_thread_pull_catalog()

    def _counts(self) -> dict[str, int]:
        from world.conditions.models import CapabilityType
        from world.magic.models import Affinity, Resonance
        from world.magic.models.threads import ThreadPullCost, ThreadPullEffect

        return {
            "pull_costs": ThreadPullCost.objects.count(),
            "pull_effects": ThreadPullEffect.objects.count(),
            "resonances": Resonance.objects.count(),
            "affinities": Affinity.objects.count(),
            "capability_types": CapabilityType.objects.count(),
        }

    def test_row_counts_unchanged(self) -> None:
        counts = self._counts()
        self.assertEqual(counts["pull_costs"], 3)
        self.assertEqual(
            counts["pull_effects"],
            4,
            "seed_thread_pull_catalog() must not create extra ThreadPullEffect rows on second call",
        )
        self.assertEqual(
            counts["resonances"],
            1,
            "seed_thread_pull_catalog() must not create extra Resonance rows on second call",
        )
        self.assertEqual(
            counts["affinities"],
            1,
            "seed_thread_pull_catalog() must not create extra Affinity rows on second call",
        )
        self.assertEqual(
            counts["capability_types"],
            1,
            "seed_thread_pull_catalog() must not create extra CapabilityType rows on second call",
        )

    def test_same_pks_returned(self) -> None:
        from world.magic.constants import EffectKind

        self.assertEqual(
            self.first.canonical_resonance.pk,
            self.second.canonical_resonance.pk,
        )
        for tier in (1, 2, 3):
            self.assertEqual(
                self.first.pull_costs[tier].pk,
                self.second.pull_costs[tier].pk,
                f"ThreadPullCost tier {tier} pk changed on second call",
            )
        for effect_kind in (
            EffectKind.FLAT_BONUS,
            EffectKind.INTENSITY_BUMP,
            EffectKind.VITAL_BONUS,
            EffectKind.CAPABILITY_GRANT,
        ):
            self.assertEqual(
                self.first.pull_effects[effect_kind].pk,
                self.second.pull_effects[effect_kind].pk,
                f"ThreadPullEffect {effect_kind} pk changed on second call",
            )


class TestSeedThreadPullCatalogPreservesEdits(TestCase):
    """Staff edits to ThreadPullEffect survive a re-run (get_or_create semantics)."""

    def test_edit_preserved_on_rerun(self) -> None:
        from world.magic.constants import EffectKind
        from world.magic.models.threads import ThreadPullEffect

        first = seed_thread_pull_catalog()
        flat_pk = first.pull_effects[EffectKind.FLAT_BONUS].pk

        # Simulate a staff edit via bulk update (bypasses identity map)
        ThreadPullEffect.objects.filter(pk=flat_pk).update(flat_bonus_amount=99)

        # Re-run the seed — must not overwrite the staff edit
        seed_thread_pull_catalog()

        # Use .values() to bypass SharedMemoryModel identity-map cache and
        # read directly from the DB.
        db_value = ThreadPullEffect.objects.filter(pk=flat_pk).values("flat_bonus_amount").get()
        self.assertEqual(
            db_value["flat_bonus_amount"],
            99,
            "seed_thread_pull_catalog() must not overwrite existing rows (get_or_create semantics)",
        )
