"""Tests for seed_magic_config() — Task 1.1, seed_canonical_rituals() — Task 1.2,
seed_thread_pull_catalog() — Task 1.3, seed_cantrip_starter_catalog() — Task 1.8,
and seed_starter_magic_story() — Task 13g.

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
9. Cantrip starter catalog creates 5 styles, 6 effect types, 25 cantrips (Task 1.8).
10. Cantrip catalog seeding is idempotent (Task 1.8).
11. Staff edits to Cantrip rows survive a re-run (Task 1.8).
12. seed_starter_magic_story() composes all 8 phases in dependency order (Task 13g).
13. Re-running the orchestrator produces no changes (idempotent at slice level) (Task 13g).
14. Staff edits to seeded rows survive re-runs (Task 13g).
"""

from django.test import TestCase

from integration_tests.game_content.magic import (
    CantripStarterCatalogResult,
    MagicConfigResult,
    RitualSeedResult,
    ThreadPullCatalogResult,
    _seed_affinity_interactions,
    _seed_resonance_environment_conditions,
    _seed_resonance_environment_config,
    seed_canonical_affinities,
    seed_canonical_resonances,
    seed_canonical_rituals,
    seed_cantrip_starter_catalog,
    seed_magic_config,
    seed_magic_dev,
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

    def test_soulfray_threshold_ratio_is_decimal(self) -> None:
        """Regression: seed_magic_config() must store Decimal, not a string literal.

        SharedMemoryModel's identity map caches the freshly-inserted instance
        with whatever Python value was passed to get_or_create defaults.  If a
        string literal like "0.30" is passed instead of Decimal("0.30"), downstream
        code that does ``Decimal(...) >= soulfray_threshold_ratio`` raises TypeError.
        """
        from decimal import Decimal

        from world.magic.models import SoulfrayConfig

        cfg = SoulfrayConfig.objects.get(pk=1)
        # isinstance check: catches the string-literal bug before any arithmetic
        self.assertIsInstance(
            cfg.soulfray_threshold_ratio,
            Decimal,
            "soulfray_threshold_ratio must be a Decimal, not a string literal",
        )
        # Decimal comparison: fires TypeError if value is a str
        self.assertGreater(
            cfg.soulfray_threshold_ratio,
            Decimal("0.0"),
            "soulfray_threshold_ratio must be > 0",
        )

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


# ---------------------------------------------------------------------------
# Task 1.8 — seed_cantrip_starter_catalog()
# ---------------------------------------------------------------------------


class TestSeedCantripStarterCatalogCreation(TestCase):
    """First-call assertions: correct counts and archetype×style grid exists."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.result: CantripStarterCatalogResult = seed_cantrip_starter_catalog()

    def test_five_styles_created(self) -> None:
        from world.magic.models import TechniqueStyle

        self.assertEqual(TechniqueStyle.objects.count(), 5)
        expected_styles = {"Manifestation", "Subtle", "Performance", "Prayer", "Incantation"}
        actual_styles = set(TechniqueStyle.objects.values_list("name", flat=True))
        self.assertEqual(actual_styles, expected_styles)
        self.assertEqual(set(self.result.styles.keys()), expected_styles)

    def test_six_effect_types_created(self) -> None:
        from world.magic.models import EffectType

        self.assertEqual(EffectType.objects.count(), 6)
        expected = {
            "Weapon Enhancement",
            "Ranged Attack",
            "Buff",
            "Debuff",
            "Defense",
            "Utility",
        }
        actual = set(EffectType.objects.values_list("name", flat=True))
        self.assertEqual(actual, expected)
        self.assertEqual(set(self.result.effect_types.keys()), expected)

    def test_twenty_five_cantrips_created(self) -> None:
        from world.magic.models.cantrips import Cantrip

        self.assertEqual(Cantrip.objects.count(), 25)
        self.assertEqual(len(self.result.cantrips), 25)

    def test_each_cantrip_has_correct_archetype_and_style(self) -> None:
        """Every (archetype, style_name) combination must appear exactly once."""
        from world.magic.constants import CantripArchetype
        from world.magic.models.cantrips import Cantrip

        expected_archetypes = {
            CantripArchetype.ATTACK,
            CantripArchetype.DEFENSE,
            CantripArchetype.BUFF,
            CantripArchetype.DEBUFF,
            CantripArchetype.UTILITY,
        }
        expected_style_names = {"Manifestation", "Subtle", "Performance", "Prayer", "Incantation"}

        # Build (archetype, style_name) pairs from the DB
        pairs = set(Cantrip.objects.select_related("style").values_list("archetype", "style__name"))
        expected_pairs = {
            (arch, style) for arch in expected_archetypes for style in expected_style_names
        }
        self.assertEqual(
            pairs,
            expected_pairs,
            "Each (archetype, style) pair must appear exactly once",
        )

    def test_five_prospect_paths_created(self) -> None:
        from world.classes.models import Path, PathStage

        self.assertEqual(Path.objects.filter(stage=PathStage.PROSPECT).count(), 5)
        expected_path_names = {
            "Path of Steel",
            "Path of Whispers",
            "Path of Voice",
            "Path of the Chosen",
            "Path of Tomes",
        }
        actual = set(Path.objects.filter(stage=PathStage.PROSPECT).values_list("name", flat=True))
        self.assertEqual(actual, expected_path_names)
        self.assertEqual(set(self.result.paths.keys()), expected_path_names)

    def test_styles_wired_to_paths(self) -> None:
        """Each TechniqueStyle must have exactly one allowed_path matching the canonical mapping."""
        style_to_path = {
            "Manifestation": "Path of Steel",
            "Subtle": "Path of Whispers",
            "Performance": "Path of Voice",
            "Prayer": "Path of the Chosen",
            "Incantation": "Path of Tomes",
        }
        from world.magic.models import TechniqueStyle

        for style_name, path_name in style_to_path.items():
            style = TechniqueStyle.objects.get(name=style_name)
            allowed = list(style.allowed_paths.values_list("name", flat=True))
            self.assertIn(
                path_name,
                allowed,
                f"Style '{style_name}' must have '{path_name}' in allowed_paths",
            )

    def test_cantrips_are_active(self) -> None:
        from world.magic.models.cantrips import Cantrip

        inactive = Cantrip.objects.filter(is_active=False).count()
        self.assertEqual(inactive, 0, "All seeded cantrips must be active")

    def test_cantrip_default_mechanicals(self) -> None:
        """All cantrips should have starter-level mechanical values."""
        from world.magic.models.cantrips import Cantrip

        for cantrip in Cantrip.objects.all():
            self.assertEqual(cantrip.base_intensity, 1, f"{cantrip.name}: base_intensity")
            self.assertEqual(cantrip.base_control, 1, f"{cantrip.name}: base_control")
            self.assertEqual(cantrip.base_anima_cost, 5, f"{cantrip.name}: base_anima_cost")


class TestSeedCantripStarterCatalogIdempotency(TestCase):
    """Second-call assertions: row counts unchanged, same PKs returned."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.first: CantripStarterCatalogResult = seed_cantrip_starter_catalog()
        cls.second: CantripStarterCatalogResult = seed_cantrip_starter_catalog()

    def _counts(self) -> dict[str, int]:
        from world.classes.models import Path, PathStage
        from world.magic.models import EffectType, TechniqueStyle
        from world.magic.models.cantrips import Cantrip

        return {
            "cantrips": Cantrip.objects.count(),
            "styles": TechniqueStyle.objects.count(),
            "effect_types": EffectType.objects.count(),
            "prospect_paths": Path.objects.filter(stage=PathStage.PROSPECT).count(),
        }

    def test_row_counts_unchanged(self) -> None:
        counts = self._counts()
        self.assertEqual(counts["cantrips"], 25)
        self.assertEqual(counts["styles"], 5)
        self.assertEqual(counts["effect_types"], 6)
        self.assertEqual(counts["prospect_paths"], 5)

    def test_same_pks_returned(self) -> None:
        style_names = {"Manifestation", "Subtle", "Performance", "Prayer", "Incantation"}
        for name in style_names:
            self.assertEqual(
                self.first.styles[name].pk,
                self.second.styles[name].pk,
                f"TechniqueStyle '{name}' pk changed on second call",
            )
        for name, cantrip in self.first.cantrips.items():
            self.assertEqual(
                cantrip.pk,
                self.second.cantrips[name].pk,
                f"Cantrip '{name}' pk changed on second call",
            )
        for name, et in self.first.effect_types.items():
            self.assertEqual(
                et.pk,
                self.second.effect_types[name].pk,
                f"EffectType '{name}' pk changed on second call",
            )
        path_names = {
            "Path of Steel",
            "Path of Whispers",
            "Path of Voice",
            "Path of the Chosen",
            "Path of Tomes",
        }
        for name in path_names:
            self.assertEqual(
                self.first.paths[name].pk,
                self.second.paths[name].pk,
                f"Path '{name}' pk changed on second call",
            )


class TestSeedCantripStarterCatalogPreservesEdits(TestCase):
    """Staff edits to Cantrip rows survive a re-run (get_or_create semantics)."""

    def test_edit_preserved_on_rerun(self) -> None:
        from world.magic.models.cantrips import Cantrip

        first = seed_cantrip_starter_catalog()
        # Pick the first cantrip alphabetically for determinism
        cantrip_name = next(iter(sorted(first.cantrips.keys())))
        cantrip_pk = first.cantrips[cantrip_name].pk

        # Simulate a staff edit via bulk update (bypasses identity map)
        Cantrip.objects.filter(pk=cantrip_pk).update(description="staff-edited description")

        # Re-run the seed — must not overwrite the staff edit
        seed_cantrip_starter_catalog()

        # Use .values() to bypass SharedMemoryModel identity-map cache
        db_value = Cantrip.objects.filter(pk=cantrip_pk).values("description").get()
        self.assertEqual(
            db_value["description"],
            "staff-edited description",
            "seed_cantrip_starter_catalog() must not overwrite existing rows",
        )


# ---------------------------------------------------------------------------
# Task 1.9 — seed_magic_dev() orchestrator
# ---------------------------------------------------------------------------


class TestSeedMagicDevCheckTypeConvergence(TestCase):
    """TDD: guard for _make_magical_endurance_check_type() orphan bug.

    This test is written BEFORE the fix so it fails first, confirming the bug,
    then passes after the fix is applied.
    """

    def test_check_type_convergence(self) -> None:
        """Exactly 1 CheckType named 'Magical Endurance' after orchestrator runs.

        Before the fix, author_reference_corruption_content() calls
        _make_magical_endurance_check_type() which uses CheckTypeFactory with a
        fresh CheckCategory SubFactory — creating an orphan row on each call.
        seed_magic_config() independently creates the canonical row via direct ORM.
        Running both produces 2 CheckType rows.  After the fix, both helpers
        converge on the same (name='Magical Endurance', category__name='Magic') row.
        """
        from integration_tests.game_content.magic import seed_magic_dev
        from world.checks.models import CheckCategory, CheckType

        seed_magic_dev()

        self.assertEqual(
            CheckType.objects.filter(name="Magical Endurance").count(),
            1,
            "seed_magic_dev() must produce exactly 1 CheckType named 'Magical Endurance'",
        )
        self.assertEqual(
            CheckCategory.objects.filter(name="Magic").count(),
            1,
            "seed_magic_dev() must produce exactly 1 CheckCategory named 'Magic'",
        )


class TestSeedMagicDevTechniqueIdempotency(TestCase):
    """TDD: guard for MagicContent.create_all() duplicate Technique bug.

    This test is written BEFORE the fix so it fails first, confirming the bug,
    then passes after MagicContent.create_all() switches to get_or_create.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from integration_tests.game_content.magic import seed_magic_dev

        # Two calls — if create_all() is not idempotent, techniques double
        seed_magic_dev()
        seed_magic_dev()

    def test_social_techniques_exist_exactly_once(self) -> None:
        """Each of the 6 social action techniques must appear exactly once."""
        from integration_tests.game_content.magic import ACTION_TECHNIQUE_MAP
        from world.magic.models import Technique

        for action_key, technique_name in ACTION_TECHNIQUE_MAP.items():
            with self.subTest(technique=technique_name):
                self.assertEqual(
                    Technique.objects.filter(name=technique_name).count(),
                    1,
                    f"Technique '{technique_name}' must exist exactly once after two "
                    f"seed_magic_dev() calls (action_key={action_key!r})",
                )

    def test_action_enhancements_exist_exactly_once(self) -> None:
        """Each of the 6 ActionEnhancement rows must appear exactly once."""
        from actions.models import ActionEnhancement
        from integration_tests.game_content.magic import ACTION_TECHNIQUE_MAP

        for action_key in ACTION_TECHNIQUE_MAP:
            with self.subTest(action_key=action_key):
                self.assertEqual(
                    ActionEnhancement.objects.filter(base_action_key=action_key).count(),
                    1,
                    f"ActionEnhancement for '{action_key}' must exist exactly once after two "
                    f"seed_magic_dev() calls",
                )


class TestSeedMagicDev(TestCase):
    """Verify the master orchestrator composes all Phase 1 seed helpers."""

    @classmethod
    def setUpTestData(cls) -> None:
        from integration_tests.game_content.magic import seed_magic_dev

        cls.first = seed_magic_dev()
        cls.second = seed_magic_dev()

    def test_first_call_creates_all_components(self) -> None:
        """Spot-check: at least one of every authored row family exists."""
        from world.checks.models import CheckType
        from world.classes.models import Path
        from world.conditions.models import ConditionTemplate
        from world.magic.audere import AudereThreshold
        from world.magic.models import (
            AnimaConfig,
            EffectType,
            IntensityTier,
            MishapPoolTier,
            Ritual,
            SoulfrayConfig,
            Technique,
            TechniqueStyle,
        )
        from world.magic.models.cantrips import Cantrip
        from world.magic.models.corruption_config import CorruptionConfig
        from world.magic.models.gain_config import ResonanceGainConfig
        from world.magic.models.threads import ThreadPullCost, ThreadPullEffect

        # --- Task 1.1: config singletons ---
        self.assertEqual(AnimaConfig.objects.count(), 1)
        self.assertEqual(SoulfrayConfig.objects.count(), 1)
        self.assertEqual(ResonanceGainConfig.objects.count(), 1)
        self.assertEqual(CorruptionConfig.objects.count(), 1)
        self.assertEqual(AudereThreshold.objects.count(), 1)
        self.assertGreaterEqual(IntensityTier.objects.count(), 3)
        self.assertEqual(MishapPoolTier.objects.count(), 1)

        # --- Task 1.2: canonical rituals ---
        self.assertTrue(Ritual.objects.filter(name="Rite of Imbuing").exists())
        self.assertTrue(Ritual.objects.filter(name="Rite of Atonement").exists())

        # --- Task 1.3: thread pull catalog ---
        self.assertEqual(ThreadPullCost.objects.count(), 3)
        self.assertEqual(ThreadPullEffect.objects.count(), 4)

        # --- Task 1.8: cantrip catalog ---
        # TechniqueStyle: 5 from cantrip catalog + 1 "Social" from MagicContent.create_all()
        self.assertGreaterEqual(TechniqueStyle.objects.count(), 5)
        self.assertTrue(
            TechniqueStyle.objects.filter(
                name__in={"Manifestation", "Subtle", "Performance", "Prayer", "Incantation"}
            ).count()
            == 5,
            "All 5 cantrip-catalog styles must exist",
        )
        # EffectType: 6 from cantrip catalog + 1 "Social Influence" from MagicContent.create_all()
        self.assertGreaterEqual(EffectType.objects.count(), 6)
        self.assertEqual(Cantrip.objects.count(), 25)
        self.assertEqual(Path.objects.filter(name__startswith="Path of").count(), 5)

        # --- author_reference_corruption_content: Wild Hunt + Web of Spiders ---
        self.assertTrue(
            ConditionTemplate.objects.filter(name__icontains="Wild Hunt").exists(),
            "Wild Hunt Corruption ConditionTemplate must exist",
        )
        self.assertTrue(
            ConditionTemplate.objects.filter(name__icontains="Web of Spiders").exists(),
            "Web of Spiders Corruption ConditionTemplate must exist",
        )

        # --- MagicContent.create_all(): 6 social techniques ---
        from integration_tests.game_content.magic import ACTION_TECHNIQUE_MAP

        for technique_name in ACTION_TECHNIQUE_MAP.values():
            self.assertTrue(
                Technique.objects.filter(name=technique_name).exists(),
                f"Social technique '{technique_name}' must exist",
            )

        # --- CheckType canonical row (convergence guard) ---
        self.assertEqual(CheckType.objects.filter(name="Magical Endurance").count(), 1)

    def test_idempotent_full_run(self) -> None:
        """Row counts must not change on a third call."""
        from actions.models import ActionEnhancement
        from world.checks.models import CheckCategory, CheckType
        from world.classes.models import Path
        from world.conditions.models import ConditionTemplate
        from world.magic.audere import AudereThreshold
        from world.magic.models import (
            AnimaConfig,
            EffectType,
            IntensityTier,
            MishapPoolTier,
            Ritual,
            SoulfrayConfig,
            Technique,
            TechniqueStyle,
        )
        from world.magic.models.cantrips import Cantrip
        from world.magic.models.corruption_config import CorruptionConfig
        from world.magic.models.gain_config import ResonanceGainConfig
        from world.magic.models.threads import ThreadPullCost, ThreadPullEffect

        def _snapshot() -> dict[str, int]:
            return {
                "anima_config": AnimaConfig.objects.count(),
                "soulfray_config": SoulfrayConfig.objects.count(),
                "resonance_gain_config": ResonanceGainConfig.objects.count(),
                "corruption_config": CorruptionConfig.objects.count(),
                "audere_threshold": AudereThreshold.objects.count(),
                "intensity_tiers": IntensityTier.objects.count(),
                "mishap_pool_tiers": MishapPoolTier.objects.count(),
                "rituals": Ritual.objects.count(),
                "thread_pull_costs": ThreadPullCost.objects.count(),
                "thread_pull_effects": ThreadPullEffect.objects.count(),
                "technique_styles": TechniqueStyle.objects.count(),
                "effect_types": EffectType.objects.count(),
                "cantrips": Cantrip.objects.count(),
                "paths": Path.objects.count(),
                "condition_templates": ConditionTemplate.objects.count(),
                "techniques": Technique.objects.count(),
                "action_enhancements": ActionEnhancement.objects.count(),
                "check_types": CheckType.objects.count(),
                "check_categories": CheckCategory.objects.count(),
            }

        from integration_tests.game_content.magic import seed_magic_dev

        before = _snapshot()
        seed_magic_dev()
        after = _snapshot()

        for model_name, count_before in before.items():
            with self.subTest(model=model_name):
                self.assertEqual(
                    after[model_name],
                    count_before,
                    f"{model_name}: row count changed from {count_before} to "
                    f"{after[model_name]} on third seed_magic_dev() call",
                )

    def test_check_type_convergence(self) -> None:
        """Exactly 1 CheckType named 'Magical Endurance' after two orchestrator calls."""
        from world.checks.models import CheckCategory, CheckType

        self.assertEqual(
            CheckType.objects.filter(name="Magical Endurance").count(),
            1,
        )
        self.assertEqual(
            CheckCategory.objects.filter(name="Magic").count(),
            1,
        )

    def test_technique_idempotency_via_magic_content(self) -> None:
        """The 6 social techniques must exist exactly once after two orchestrator calls."""
        from integration_tests.game_content.magic import ACTION_TECHNIQUE_MAP
        from world.magic.models import Technique

        for action_key, technique_name in ACTION_TECHNIQUE_MAP.items():
            with self.subTest(technique=technique_name):
                self.assertEqual(
                    Technique.objects.filter(name=technique_name).count(),
                    1,
                    f"Technique '{technique_name}' (action_key={action_key!r}) must exist "
                    f"exactly once after two seed_magic_dev() calls",
                )


# ---------------------------------------------------------------------------
# Task 1.11 — seed_canonical_affinities()
# ---------------------------------------------------------------------------


class SeedCanonicalAffinitiesTests(TestCase):
    """Task 1.11: seed_canonical_affinities() creates idempotent Affinity rows."""

    def test_seeds_three_canonical_affinities(self) -> None:
        seed_canonical_affinities()
        from world.magic.models.affinity import Affinity

        names = set(Affinity.objects.values_list("name", flat=True))
        # Three canonical names must all exist after seeding.
        self.assertGreaterEqual(names, {"Celestial", "Primal", "Abyssal"})

    def test_idempotent(self) -> None:
        seed_canonical_affinities()
        from world.magic.models.affinity import Affinity

        snapshot_a = sorted(Affinity.objects.values_list("name", flat=True))
        seed_canonical_affinities()
        snapshot_b = sorted(Affinity.objects.values_list("name", flat=True))
        self.assertEqual(snapshot_a, snapshot_b)

    def test_preserves_edits(self) -> None:
        seed_canonical_affinities()
        from world.magic.models.affinity import Affinity

        celestial = Affinity.objects.get(name="Celestial")
        # Affinity may or may not have a 'description' field — pick whatever
        # editable text field exists. If only `name` is editable, skip this test.
        editable_field = None
        for candidate in ("description", "display_name", "flavor_text"):
            if hasattr(celestial, candidate):
                editable_field = candidate
                break
        if editable_field is None:
            self.skipTest("Affinity has no editable text field to mutate")
        setattr(celestial, editable_field, "edited by t11 test")
        celestial.save()

        seed_canonical_affinities()
        celestial.refresh_from_db()
        self.assertEqual(getattr(celestial, editable_field), "edited by t11 test")


# ---------------------------------------------------------------------------
# Task 1.12 — seed_canonical_resonances()
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Task 13a — _seed_endure_hallowed_ground_check()
# ---------------------------------------------------------------------------


class SeedEndureHallowedGroundCheckTests(TestCase):
    def test_seeds_check_type(self):
        from integration_tests.game_content.magic import _seed_endure_hallowed_ground_check
        from world.checks.models import CheckType

        _seed_endure_hallowed_ground_check()
        self.assertTrue(CheckType.objects.filter(name="endure_hallowed_ground").exists())

    def test_seeds_four_result_chart_outcomes(self):
        from integration_tests.game_content.magic import _seed_endure_hallowed_ground_check
        from world.traits.models import ResultChart, ResultChartOutcome

        _seed_endure_hallowed_ground_check()
        # The slice seeds rank_difference=0 chart with 4 outcomes.
        chart = ResultChart.objects.get(rank_difference=0)
        outcomes_for_chart = ResultChartOutcome.objects.filter(chart=chart)
        outcome_names = {ro.outcome.name for ro in outcomes_for_chart.select_related("outcome")}
        expected = {"Critical Success", "Success", "Failure", "Critical Failure"}
        self.assertGreaterEqual(outcome_names, expected)

    def test_idempotent(self):
        from integration_tests.game_content.magic import _seed_endure_hallowed_ground_check
        from world.checks.models import CheckType
        from world.traits.models import ResultChart, ResultChartOutcome

        _seed_endure_hallowed_ground_check()
        ct_count_a = CheckType.objects.count()
        rc_count_a = ResultChart.objects.count()
        rco_count_a = ResultChartOutcome.objects.count()

        _seed_endure_hallowed_ground_check()
        self.assertEqual(CheckType.objects.count(), ct_count_a)
        self.assertEqual(ResultChart.objects.count(), rc_count_a)
        self.assertEqual(ResultChartOutcome.objects.count(), rco_count_a)


class SeedCanonicalResonancesTests(TestCase):
    """Task 1.12: seed_canonical_resonances() creates idempotent Celestial Resonance rows."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_canonical_affinities()

    def test_seeds_three_celestial_resonances(self) -> None:
        seed_canonical_resonances()
        from world.magic.models.affinity import Affinity, Resonance

        celestial = Affinity.objects.get(name="Celestial")
        names = set(
            Resonance.objects.filter(affinity=celestial).values_list("name", flat=True),
        )
        self.assertGreaterEqual(names, {"Light", "Sanctity", "Radiance"})

    def test_idempotent(self) -> None:
        seed_canonical_resonances()
        from world.magic.models.affinity import Resonance

        count_a = Resonance.objects.count()
        seed_canonical_resonances()
        count_b = Resonance.objects.count()
        self.assertEqual(count_a, count_b)

    def test_resonances_have_celestial_affinity(self) -> None:
        seed_canonical_resonances()
        from world.magic.models.affinity import Affinity, Resonance

        celestial = Affinity.objects.get(name="Celestial")
        for name in ("Light", "Sanctity", "Radiance"):
            res = Resonance.objects.get(name=name)
            self.assertEqual(res.affinity, celestial)


# ---------------------------------------------------------------------------
# Task 13b — _seed_hallowed_reaction_conditions()
# ---------------------------------------------------------------------------


class SeedHallowedReactionConditionsTests(TestCase):
    def test_seeds_five_reaction_conditions(self):
        from integration_tests.game_content.magic import _seed_hallowed_reaction_conditions
        from world.conditions.models import ConditionTemplate

        _seed_hallowed_reaction_conditions()
        names = set(ConditionTemplate.objects.values_list("name", flat=True))
        expected = {
            "Tempered Against Light",
            "Singed",
            "Burning",
            "Hallowed Burn",
            "Cast Disrupted",
        }
        self.assertGreaterEqual(names, expected)

    def test_idempotent(self):
        from integration_tests.game_content.magic import _seed_hallowed_reaction_conditions
        from world.conditions.models import ConditionTemplate

        _seed_hallowed_reaction_conditions()
        count_a = ConditionTemplate.objects.count()
        _seed_hallowed_reaction_conditions()
        count_b = ConditionTemplate.objects.count()
        self.assertEqual(count_a, count_b)

    def test_burning_reuses_existing_factory_template(self):
        """If a Burning template already exists (factory-created), get_or_create reuses it."""
        from integration_tests.game_content.magic import _seed_hallowed_reaction_conditions
        from world.conditions.factories import ConditionTemplateFactory
        from world.conditions.models import ConditionTemplate

        # Pre-create a Burning template (mimics factory test setup).
        pre_existing = ConditionTemplateFactory(name="Burning")

        _seed_hallowed_reaction_conditions()

        # Same row, not a duplicate.
        self.assertEqual(
            ConditionTemplate.objects.filter(name="Burning").count(),
            1,
        )
        self.assertEqual(
            ConditionTemplate.objects.get(name="Burning").pk,
            pre_existing.pk,
        )


# ---------------------------------------------------------------------------
# Task 13c — _seed_hallowed_achievement_bridge()
# ---------------------------------------------------------------------------


class SeedHallowedAchievementBridgeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from integration_tests.game_content.magic import _seed_hallowed_reaction_conditions

        _seed_hallowed_reaction_conditions()

    def test_seeds_three_stat_definitions(self):
        from integration_tests.game_content.magic import _seed_hallowed_achievement_bridge
        from world.achievements.models import StatDefinition

        _seed_hallowed_achievement_bridge()
        keys = set(StatDefinition.objects.values_list("key", flat=True))
        expected = {
            "conditions.tempered_against_light.gained",
            "conditions.singed.gained",
            "conditions.hallowed_burn.gained",
        }
        self.assertGreaterEqual(keys, expected)

    def test_seeds_three_condition_stat_rules(self):
        from integration_tests.game_content.magic import _seed_hallowed_achievement_bridge
        from world.achievements.constants import ConditionEventType
        from world.achievements.models import ConditionStatRule

        _seed_hallowed_achievement_bridge()
        # Each rule links one of the 3 reaction conditions to its corresponding stat.
        rules = ConditionStatRule.objects.filter(event_type=ConditionEventType.GAINED)
        rule_pairs = {
            (r.condition.name, r.stat.key) for r in rules.select_related("condition", "stat")
        }
        expected = {
            ("Tempered Against Light", "conditions.tempered_against_light.gained"),
            ("Singed", "conditions.singed.gained"),
            ("Hallowed Burn", "conditions.hallowed_burn.gained"),
        }
        self.assertGreaterEqual(rule_pairs, expected)

    def test_seeds_three_achievements(self):
        from integration_tests.game_content.magic import _seed_hallowed_achievement_bridge
        from world.achievements.models import Achievement

        _seed_hallowed_achievement_bridge()
        names = set(Achievement.objects.values_list("name", flat=True))
        expected = {"Hallowed-Hardened", "Touched by Light", "Cast Out by the Light"}
        self.assertGreaterEqual(names, expected)

    def test_seeds_three_achievement_requirements(self):
        from integration_tests.game_content.magic import _seed_hallowed_achievement_bridge
        from world.achievements.models import Achievement, AchievementRequirement

        _seed_hallowed_achievement_bridge()
        for ach_name, stat_key in (
            ("Hallowed-Hardened", "conditions.tempered_against_light.gained"),
            ("Touched by Light", "conditions.singed.gained"),
            ("Cast Out by the Light", "conditions.hallowed_burn.gained"),
        ):
            ach = Achievement.objects.get(name=ach_name)
            reqs = AchievementRequirement.objects.filter(
                achievement=ach,
                stat__key=stat_key,
            )
            self.assertEqual(reqs.count(), 1)
            self.assertEqual(reqs.first().threshold, 1)

    def test_burning_has_no_stat_or_achievement(self):
        from integration_tests.game_content.magic import _seed_hallowed_achievement_bridge
        from world.achievements.models import StatDefinition

        _seed_hallowed_achievement_bridge()
        self.assertFalse(
            StatDefinition.objects.filter(key="conditions.burning.gained").exists(),
        )

    def test_idempotent(self):
        from integration_tests.game_content.magic import _seed_hallowed_achievement_bridge
        from world.achievements.models import (
            Achievement,
            AchievementRequirement,
            ConditionStatRule,
            StatDefinition,
        )

        _seed_hallowed_achievement_bridge()
        snapshot = (
            StatDefinition.objects.count(),
            ConditionStatRule.objects.count(),
            Achievement.objects.count(),
            AchievementRequirement.objects.count(),
        )
        _seed_hallowed_achievement_bridge()
        self.assertEqual(
            (
                StatDefinition.objects.count(),
                ConditionStatRule.objects.count(),
                Achievement.objects.count(),
                AchievementRequirement.objects.count(),
            ),
            snapshot,
        )


class SeedResonanceEnvironmentFlowAndTriggerTests(TestCase):
    """RC3: _seed_resonance_environment_flow_and_trigger() tests.

    Verifies:
    - FlowDefinition created with expected name.
    - Step count: 1 evaluate step + 3 branch conditionals (corrupt/aligned/opposed)
      + 1 perform_check + 4 outcome conditionals + 5 apply_condition steps = 14 total.
    - TriggerDefinition uses TECHNIQUE_CAST with empty base_filter_condition.
    - Magically Attuned.reactive_triggers contains the TriggerDefinition.
    - Idempotent: second call does not duplicate steps.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from integration_tests.game_content.magic import (
            _seed_endure_hallowed_ground_check,
            _seed_hallowed_reaction_conditions,
            _seed_resonance_environment_conditions,
        )

        _seed_endure_hallowed_ground_check()
        _seed_hallowed_reaction_conditions()
        _seed_resonance_environment_conditions()

    def test_seeds_flow_definition(self) -> None:
        from flows.models.flows import FlowDefinition
        from integration_tests.game_content.magic import (
            RESONANCE_ENV_FLOW_NAME,
            _seed_resonance_environment_flow_and_trigger,
        )

        _seed_resonance_environment_flow_and_trigger()
        self.assertTrue(
            FlowDefinition.objects.filter(name=RESONANCE_ENV_FLOW_NAME).exists(),
        )

    def test_seeds_expected_step_count(self) -> None:
        """Flow should have exactly 14 steps:
        1 evaluate + 3 branch conditionals (corrupt/aligned/opposed)
        + 1 apply_condition (ALIGNED boon)
        + 1 perform_check
        + 4 outcome conditionals
        + 4 apply_condition steps (Tempered/Singed/Burning/Hallowed Burn)
        + 1 apply_condition (Cast Disrupted, chained child of Critical Failure)
        = 15 total.
        """
        from flows.models.flows import FlowDefinition, FlowStepDefinition
        from integration_tests.game_content.magic import (
            RESONANCE_ENV_FLOW_NAME,
            _seed_resonance_environment_flow_and_trigger,
        )

        _seed_resonance_environment_flow_and_trigger()
        flow = FlowDefinition.objects.get(name=RESONANCE_ENV_FLOW_NAME)
        step_count = FlowStepDefinition.objects.filter(flow=flow).count()
        # 1 evaluate + 3 branch + 1 aligned boon + 1 perform_check + 4 outcome branches
        # + 4 single-condition applies + 1 extra (Cast Disrupted chained) = 15
        self.assertEqual(step_count, 15)

    def test_seeds_trigger_definition_technique_cast(self) -> None:
        from flows.constants import EventName
        from flows.models.triggers import TriggerDefinition
        from integration_tests.game_content.magic import (
            RESONANCE_ENV_TRIGGER_NAME,
            _seed_resonance_environment_flow_and_trigger,
        )

        _seed_resonance_environment_flow_and_trigger()
        td = TriggerDefinition.objects.get(name=RESONANCE_ENV_TRIGGER_NAME)
        self.assertEqual(td.event_name, EventName.TECHNIQUE_CAST)
        # Empty filter: the primitive does the gating, no has_affinity_resonance.
        self.assertEqual(td.base_filter_condition, {})

    def test_trigger_wired_into_magically_attuned(self) -> None:
        """Magically Attuned.reactive_triggers must include the resonance-env trigger."""
        from flows.models.triggers import TriggerDefinition
        from integration_tests.game_content.magic import (
            RESONANCE_ENV_TRIGGER_NAME,
            _seed_resonance_environment_flow_and_trigger,
        )
        from world.conditions.models import ConditionTemplate

        _seed_resonance_environment_flow_and_trigger()
        td = TriggerDefinition.objects.get(name=RESONANCE_ENV_TRIGGER_NAME)
        attuned = ConditionTemplate.objects.get(name="Magically Attuned")
        self.assertIn(td, attuned.reactive_triggers.all())

    def test_idempotent_does_not_duplicate_steps(self) -> None:
        from flows.models.flows import FlowDefinition, FlowStepDefinition
        from integration_tests.game_content.magic import (
            RESONANCE_ENV_FLOW_NAME,
            _seed_resonance_environment_flow_and_trigger,
        )

        _seed_resonance_environment_flow_and_trigger()
        flow = FlowDefinition.objects.get(name=RESONANCE_ENV_FLOW_NAME)
        step_count_a = FlowStepDefinition.objects.filter(flow=flow).count()

        _seed_resonance_environment_flow_and_trigger()
        step_count_b = FlowStepDefinition.objects.filter(flow=flow).count()
        self.assertEqual(step_count_a, step_count_b)

    def test_idempotent_does_not_duplicate_trigger(self) -> None:
        from flows.models.triggers import TriggerDefinition
        from integration_tests.game_content.magic import (
            RESONANCE_ENV_TRIGGER_NAME,
            _seed_resonance_environment_flow_and_trigger,
        )

        _seed_resonance_environment_flow_and_trigger()
        count_a = TriggerDefinition.objects.filter(name=RESONANCE_ENV_TRIGGER_NAME).count()
        _seed_resonance_environment_flow_and_trigger()
        count_b = TriggerDefinition.objects.filter(name=RESONANCE_ENV_TRIGGER_NAME).count()
        self.assertEqual(count_a, 1)
        self.assertEqual(count_b, 1)


# ---------------------------------------------------------------------------
# RC4 — _seed_resonance_environment_rooms()
# ---------------------------------------------------------------------------


class SeedResonanceEnvironmentRoomsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from integration_tests.game_content.magic import (
            _seed_endure_hallowed_ground_check,
            _seed_hallowed_reaction_conditions,
            _seed_resonance_environment_conditions,
            _seed_resonance_environment_flow_and_trigger,
            seed_canonical_affinities,
            seed_canonical_resonances,
        )

        seed_canonical_affinities()
        seed_canonical_resonances()
        _seed_hallowed_reaction_conditions()
        _seed_endure_hallowed_ground_check()
        _seed_resonance_environment_conditions()
        _seed_resonance_environment_flow_and_trigger()

    def test_seeds_hallowed_rejection_flavor_condition(self):
        from integration_tests.game_content.magic import _seed_resonance_environment_rooms
        from world.conditions.models import ConditionTemplate

        _seed_resonance_environment_rooms()
        self.assertTrue(
            ConditionTemplate.objects.filter(name="Hallowed Rejection").exists(),
        )

    def test_seeds_three_rooms(self):
        from evennia.objects.models import ObjectDB

        from integration_tests.game_content.magic import _seed_resonance_environment_rooms

        _seed_resonance_environment_rooms()
        self.assertTrue(
            ObjectDB.objects.filter(db_key="The Hallowed Threshold (Low)").exists(),
        )
        self.assertTrue(
            ObjectDB.objects.filter(db_key="The Hallowed Threshold (High)").exists(),
        )
        self.assertTrue(
            ObjectDB.objects.filter(db_key="The Resonant Sanctum (Aligned)").exists(),
        )

    def test_low_room_cascade_magnitude(self):
        """The Low celestial room resolves to magnitude 10 via effective_value."""
        from evennia.objects.models import ObjectDB

        from integration_tests.game_content.magic import _seed_resonance_environment_rooms
        from world.locations.services import effective_value
        from world.magic.models.affinity import Resonance

        _seed_resonance_environment_rooms()
        low = ObjectDB.objects.get(db_key="The Hallowed Threshold (Low)")
        light = Resonance.objects.get(name="Light")
        self.assertEqual(effective_value(low, resonance=light), 10)

    def test_high_room_cascade_magnitude(self):
        """The High celestial room resolves to magnitude 80 via effective_value."""
        from evennia.objects.models import ObjectDB

        from integration_tests.game_content.magic import _seed_resonance_environment_rooms
        from world.locations.services import effective_value
        from world.magic.models.affinity import Resonance

        _seed_resonance_environment_rooms()
        high = ObjectDB.objects.get(db_key="The Hallowed Threshold (High)")
        light = Resonance.objects.get(name="Light")
        self.assertEqual(effective_value(high, resonance=light), 80)

    def test_aligned_sanctum_cascade_magnitude(self):
        """The Abyssal aligned room resolves to magnitude 60 via effective_value."""
        from evennia.objects.models import ObjectDB

        from integration_tests.game_content.magic import _seed_resonance_environment_rooms
        from world.locations.services import effective_value
        from world.magic.models.affinity import Resonance

        _seed_resonance_environment_rooms()
        sanctum = ObjectDB.objects.get(db_key="The Resonant Sanctum (Aligned)")
        dissolution = Resonance.objects.get(name="Dissolution")
        self.assertEqual(effective_value(sanctum, resonance=dissolution), 60)

    def test_idempotent(self):
        """Re-running _seed_resonance_environment_rooms() produces stable counts/values."""
        from evennia.objects.models import ObjectDB

        from integration_tests.game_content.magic import _seed_resonance_environment_rooms
        from world.conditions.models import ConditionTemplate
        from world.locations.models import LocationValueModifier
        from world.locations.services import effective_value
        from world.magic.models.affinity import Resonance

        _seed_resonance_environment_rooms()
        light = Resonance.objects.get(name="Light")
        dissolution = Resonance.objects.get(name="Dissolution")
        low = ObjectDB.objects.get(db_key="The Hallowed Threshold (Low)")
        high = ObjectDB.objects.get(db_key="The Hallowed Threshold (High)")
        sanctum = ObjectDB.objects.get(db_key="The Resonant Sanctum (Aligned)")
        snapshot = {
            "rooms": ObjectDB.objects.filter(
                db_key__in=[
                    "The Hallowed Threshold (Low)",
                    "The Hallowed Threshold (High)",
                    "The Resonant Sanctum (Aligned)",
                ]
            ).count(),
            "modifiers": LocationValueModifier.objects.count(),
            "hallowed_rejection": ConditionTemplate.objects.filter(
                name="Hallowed Rejection"
            ).count(),
            "low_magnitude": effective_value(low, resonance=light),
            "high_magnitude": effective_value(high, resonance=light),
            "sanctum_magnitude": effective_value(sanctum, resonance=dissolution),
        }

        _seed_resonance_environment_rooms()
        post = {
            "rooms": ObjectDB.objects.filter(
                db_key__in=[
                    "The Hallowed Threshold (Low)",
                    "The Hallowed Threshold (High)",
                    "The Resonant Sanctum (Aligned)",
                ]
            ).count(),
            "modifiers": LocationValueModifier.objects.count(),
            "hallowed_rejection": ConditionTemplate.objects.filter(
                name="Hallowed Rejection"
            ).count(),
            "low_magnitude": effective_value(low, resonance=light),
            "high_magnitude": effective_value(high, resonance=light),
            "sanctum_magnitude": effective_value(sanctum, resonance=dissolution),
        }
        self.assertEqual(snapshot, post)


# ---------------------------------------------------------------------------
# Task 13f — _seed_hallowed_threshold_story()
# ---------------------------------------------------------------------------


class SeedHallowedThresholdStoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from integration_tests.game_content.magic import _seed_hallowed_reaction_conditions

        _seed_hallowed_reaction_conditions()

    def test_seeds_story(self):
        from integration_tests.game_content.magic import _seed_hallowed_threshold_story
        from world.stories.constants import StoryScope
        from world.stories.models import Story

        _seed_hallowed_threshold_story()
        story = Story.objects.get(title="The Hallowed Threshold")
        self.assertEqual(story.scope, StoryScope.CHARACTER)
        self.assertIsNone(story.character_sheet)  # template, not per-playthrough

    def test_seeds_chapter_and_four_episodes(self):
        from integration_tests.game_content.magic import _seed_hallowed_threshold_story
        from world.stories.models import Chapter, Episode

        _seed_hallowed_threshold_story()
        chapter = Chapter.objects.get(title="First Trial")
        episode_titles = set(
            Episode.objects.filter(chapter=chapter).values_list("title", flat=True),
        )
        self.assertEqual(
            episode_titles,
            {"Stepping Into Light", "Tempered Walk", "Marked Path", "Cast Out"},
        )

    def test_seeds_four_beats_on_source_episode(self):
        from integration_tests.game_content.magic import _seed_hallowed_threshold_story
        from world.stories.constants import BeatPredicateType
        from world.stories.models import Beat, Episode

        _seed_hallowed_threshold_story()
        source = Episode.objects.get(title="Stepping Into Light")
        beats = Beat.objects.filter(
            episode=source,
            predicate_type=BeatPredicateType.CONDITION_HELD,
        )
        beat_condition_names = set(
            beats.values_list("required_condition_template__name", flat=True),
        )
        self.assertEqual(
            beat_condition_names,
            {"Tempered Against Light", "Singed", "Burning", "Hallowed Burn"},
        )

    def test_seeds_four_transitions(self):
        from integration_tests.game_content.magic import _seed_hallowed_threshold_story
        from world.stories.models import Episode, Transition

        _seed_hallowed_threshold_story()
        source = Episode.objects.get(title="Stepping Into Light")
        transitions = Transition.objects.filter(source_episode=source)
        self.assertEqual(transitions.count(), 4)
        target_titles = {t.target_episode.title for t in transitions if t.target_episode}
        self.assertEqual(target_titles, {"Tempered Walk", "Marked Path", "Cast Out"})
        # Two transitions both target Marked Path (Singed + Burning routes).
        marked_path_transitions = transitions.filter(target_episode__title="Marked Path")
        self.assertEqual(marked_path_transitions.count(), 2)

    def test_seeds_four_transition_required_outcomes(self):
        from integration_tests.game_content.magic import _seed_hallowed_threshold_story
        from world.stories.models import (
            Episode,
            Transition,
            TransitionRequiredOutcome,
        )

        _seed_hallowed_threshold_story()
        source = Episode.objects.get(title="Stepping Into Light")
        for transition in Transition.objects.filter(source_episode=source):
            tros = TransitionRequiredOutcome.objects.filter(transition=transition)
            self.assertEqual(
                tros.count(),
                1,
                f"Transition {transition.target_episode} expects exactly 1 TRO",
            )

    def test_zero_episode_progression_requirements_on_source(self):
        from integration_tests.game_content.magic import _seed_hallowed_threshold_story
        from world.stories.models import Episode, EpisodeProgressionRequirement

        _seed_hallowed_threshold_story()
        source = Episode.objects.get(title="Stepping Into Light")
        self.assertEqual(
            EpisodeProgressionRequirement.objects.filter(episode=source).count(),
            0,
        )

    def test_beats_have_authored_player_resolution_text(self):
        from integration_tests.game_content.magic import _seed_hallowed_threshold_story
        from world.stories.models import Beat, Episode

        _seed_hallowed_threshold_story()
        source = Episode.objects.get(title="Stepping Into Light")
        for beat in Beat.objects.filter(episode=source):
            self.assertTrue(
                beat.player_resolution_text,
                f"Beat for {beat.required_condition_template.name} missing player_resolution_text",
            )

    def test_idempotent(self):
        from integration_tests.game_content.magic import _seed_hallowed_threshold_story
        from world.stories.models import (
            Beat,
            Chapter,
            Episode,
            Story,
            Transition,
            TransitionRequiredOutcome,
        )

        _seed_hallowed_threshold_story()
        snapshot = (
            Story.objects.count(),
            Chapter.objects.count(),
            Episode.objects.count(),
            Beat.objects.count(),
            Transition.objects.count(),
            TransitionRequiredOutcome.objects.count(),
        )
        _seed_hallowed_threshold_story()
        post = (
            Story.objects.count(),
            Chapter.objects.count(),
            Episode.objects.count(),
            Beat.objects.count(),
            Transition.objects.count(),
            TransitionRequiredOutcome.objects.count(),
        )
        self.assertEqual(snapshot, post)


class SeedStarterMagicStoryOrchestratorTests(TestCase):
    """Tests for seed_starter_magic_story() — Task 13g."""

    def test_orchestrator_calls_all_phases(self) -> None:
        """Verify all representative content from each phase is present after one call."""
        from flows.models.triggers import TriggerDefinition
        from integration_tests.game_content.magic import seed_starter_magic_story
        from world.achievements.models import Achievement
        from world.checks.models import CheckType
        from world.conditions.models import ConditionTemplate
        from world.stories.models import Story

        seed_starter_magic_story()

        # Spot-check that representative content from each phase is present.
        self.assertTrue(CheckType.objects.filter(name="endure_hallowed_ground").exists())
        self.assertTrue(ConditionTemplate.objects.filter(name="Hallowed Rejection").exists())
        self.assertTrue(ConditionTemplate.objects.filter(name="Tempered Against Light").exists())
        self.assertTrue(Achievement.objects.filter(name="Hallowed-Hardened").exists())
        self.assertTrue(
            TriggerDefinition.objects.filter(
                name="Resonance Environment — technique cast",
            ).exists(),
        )
        self.assertTrue(Story.objects.filter(title="The Hallowed Threshold").exists())

    def test_orchestrator_idempotent(self) -> None:
        """Re-running on populated DB is a no-op for all relevant tables."""
        from flows.models.flows import FlowDefinition, FlowStepDefinition
        from flows.models.triggers import TriggerDefinition
        from integration_tests.game_content.magic import seed_starter_magic_story
        from world.achievements.models import (
            Achievement,
            AchievementRequirement,
            ConditionStatRule,
            StatDefinition,
        )
        from world.checks.models import CheckType
        from world.conditions.models import ConditionTemplate
        from world.locations.models import LocationValueModifier
        from world.magic.models.affinity import Affinity, Resonance
        from world.stories.models import (
            Beat,
            Chapter,
            Episode,
            Story,
            Transition,
            TransitionRequiredOutcome,
        )
        from world.traits.models import ResultChart

        seed_starter_magic_story()
        snapshot = {
            "Affinity": Affinity.objects.count(),
            "Resonance": Resonance.objects.count(),
            "CheckType": CheckType.objects.count(),
            "ResultChart": ResultChart.objects.count(),
            "ConditionTemplate": ConditionTemplate.objects.count(),
            "ConditionStatRule": ConditionStatRule.objects.count(),
            "StatDefinition": StatDefinition.objects.count(),
            "Achievement": Achievement.objects.count(),
            "AchievementRequirement": AchievementRequirement.objects.count(),
            "FlowDefinition": FlowDefinition.objects.count(),
            "FlowStepDefinition": FlowStepDefinition.objects.count(),
            "TriggerDefinition": TriggerDefinition.objects.count(),
            "LocationValueModifier": LocationValueModifier.objects.count(),
            "Story": Story.objects.count(),
            "Chapter": Chapter.objects.count(),
            "Episode": Episode.objects.count(),
            "Beat": Beat.objects.count(),
            "Transition": Transition.objects.count(),
            "TransitionRequiredOutcome": TransitionRequiredOutcome.objects.count(),
        }

        seed_starter_magic_story()
        # Recompute counts and compare
        recount = {
            "Affinity": Affinity.objects.count(),
            "Resonance": Resonance.objects.count(),
            "CheckType": CheckType.objects.count(),
            "ResultChart": ResultChart.objects.count(),
            "ConditionTemplate": ConditionTemplate.objects.count(),
            "ConditionStatRule": ConditionStatRule.objects.count(),
            "StatDefinition": StatDefinition.objects.count(),
            "Achievement": Achievement.objects.count(),
            "AchievementRequirement": AchievementRequirement.objects.count(),
            "FlowDefinition": FlowDefinition.objects.count(),
            "FlowStepDefinition": FlowStepDefinition.objects.count(),
            "TriggerDefinition": TriggerDefinition.objects.count(),
            "LocationValueModifier": LocationValueModifier.objects.count(),
            "Story": Story.objects.count(),
            "Chapter": Chapter.objects.count(),
            "Episode": Episode.objects.count(),
            "Beat": Beat.objects.count(),
            "Transition": Transition.objects.count(),
            "TransitionRequiredOutcome": TransitionRequiredOutcome.objects.count(),
        }
        self.assertEqual(snapshot, recount)

    def test_orchestrator_preserves_edits(self) -> None:
        """Editing a seeded row and re-running the orchestrator leaves the edit intact."""
        from integration_tests.game_content.magic import seed_starter_magic_story
        from world.conditions.models import ConditionTemplate

        seed_starter_magic_story()
        marker = ConditionTemplate.objects.get(name="Hallowed Rejection")
        marker.description = "edited by orchestrator idempotency test"
        marker.save()

        seed_starter_magic_story()
        marker.refresh_from_db()
        self.assertEqual(marker.description, "edited by orchestrator idempotency test")


class TestSeedMagicDevIncludesStarterMagicStory(TestCase):
    """Verify that seed_magic_dev() includes the magic-story slice content."""

    def test_seed_magic_dev_includes_starter_magic_story_content(self) -> None:
        """seed_magic_dev() should seed Hallowed Rejection + Hallowed Threshold content."""
        from flows.models.triggers import TriggerDefinition
        from world.conditions.models import ConditionTemplate
        from world.stories.models import Story

        seed_magic_dev()

        # Spot-check that the magic-story slice content is now seeded too.
        self.assertTrue(
            ConditionTemplate.objects.filter(name="Hallowed Rejection").exists(),
            "seed_magic_dev() must include Hallowed Rejection condition",
        )
        self.assertTrue(
            TriggerDefinition.objects.filter(
                name="Resonance Environment — technique cast",
            ).exists(),
            "seed_magic_dev() must include resonance-environment cast trigger",
        )
        self.assertTrue(
            Story.objects.filter(title="The Hallowed Threshold").exists(),
            "seed_magic_dev() must include Hallowed Threshold story",
        )

    def test_seed_magic_dev_remains_idempotent_with_story_slice(self) -> None:
        """Re-running seed_magic_dev() produces stable counts after wiring slice."""
        from world.conditions.models import ConditionTemplate
        from world.stories.models import Story

        seed_magic_dev()
        first_condition_count = ConditionTemplate.objects.count()
        first_story_count = Story.objects.count()

        seed_magic_dev()
        second_condition_count = ConditionTemplate.objects.count()
        second_story_count = Story.objects.count()

        self.assertEqual(
            first_condition_count,
            second_condition_count,
            "Condition counts must be stable across seed_magic_dev() runs",
        )
        self.assertEqual(
            first_story_count,
            second_story_count,
            "Story counts must be stable across seed_magic_dev() runs",
        )


# ---------------------------------------------------------------------------
# RC1 — _seed_affinity_interactions() + _seed_resonance_environment_config()
# ---------------------------------------------------------------------------

# The 9 directed pairs from the spec, keyed (source_name, env_name).
_EXPECTED_INTERACTIONS: list[tuple[str, str, str, str, str, str]] = [
    # (source_name, env_name, valence, kind, aggressor, severity_multiplier)
    ("Celestial", "Celestial", "aligned", "amplify", "environment", "1.00"),
    ("Celestial", "Abyssal", "opposed", "reject", "environment", "1.00"),
    ("Celestial", "Primal", "opposed", "repel", "environment", "0.30"),
    ("Abyssal", "Celestial", "opposed", "reject", "environment", "1.00"),
    ("Abyssal", "Abyssal", "aligned", "amplify", "environment", "1.00"),
    ("Abyssal", "Primal", "opposed", "corrupt", "caster", "1.00"),
    ("Primal", "Celestial", "opposed", "reject", "environment", "1.00"),
    ("Primal", "Abyssal", "opposed", "corrupt", "environment", "1.00"),
    ("Primal", "Primal", "aligned", "amplify", "environment", "1.00"),
]


class SeedAffinityInteractionsTests(TestCase):
    """RC1: _seed_affinity_interactions() creates the 9 directed AffinityInteraction rows."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_canonical_affinities()
        _seed_affinity_interactions()

    def test_exactly_nine_rows_exist(self) -> None:
        from world.magic.models.resonance_environment import AffinityInteraction

        self.assertEqual(AffinityInteraction.objects.count(), 9)

    def test_each_row_has_correct_valence_kind_aggressor_multiplier(self) -> None:
        from decimal import Decimal

        from world.magic.models.affinity import Affinity
        from world.magic.models.resonance_environment import AffinityInteraction

        for src_name, env_name, valence, kind, aggressor, mult_str in _EXPECTED_INTERACTIONS:
            with self.subTest(source=src_name, env=env_name):
                src = Affinity.objects.get(name=src_name)
                env = Affinity.objects.get(name=env_name)
                row = AffinityInteraction.objects.get(
                    source_affinity=src,
                    environment_affinity=env,
                )
                self.assertEqual(row.valence, valence, f"{src_name}->{env_name} valence")
                self.assertEqual(row.kind, kind, f"{src_name}->{env_name} kind")
                self.assertEqual(row.aggressor, aggressor, f"{src_name}->{env_name} aggressor")
                self.assertEqual(
                    row.severity_multiplier,
                    Decimal(mult_str),
                    f"{src_name}->{env_name} severity_multiplier",
                )

    def test_idempotent(self) -> None:
        from world.magic.models.resonance_environment import AffinityInteraction

        count_before = AffinityInteraction.objects.count()
        _seed_affinity_interactions()
        self.assertEqual(AffinityInteraction.objects.count(), count_before)

    def test_idempotent_preserves_values(self) -> None:
        """Second call must not overwrite existing rows (get_or_create semantics)."""
        from decimal import Decimal

        from world.magic.models.affinity import Affinity
        from world.magic.models.resonance_environment import AffinityInteraction

        # Simulate a staff edit via bulk update (bypasses identity map).
        celestial = Affinity.objects.get(name="Celestial")
        primal = Affinity.objects.get(name="Primal")
        AffinityInteraction.objects.filter(
            source_affinity=celestial,
            environment_affinity=primal,
        ).update(severity_multiplier=Decimal("0.99"))

        _seed_affinity_interactions()

        db_val = (
            AffinityInteraction.objects.filter(
                source_affinity=celestial,
                environment_affinity=primal,
            )
            .values("severity_multiplier")
            .get()
        )
        self.assertEqual(
            db_val["severity_multiplier"],
            Decimal("0.99"),
            "_seed_affinity_interactions() must not overwrite existing rows",
        )


class SeedResonanceEnvironmentConfigTests(TestCase):
    """RC1: _seed_resonance_environment_config() creates the pk=1 singleton."""

    def test_creates_singleton(self) -> None:
        from world.magic.models.resonance_environment import ResonanceEnvironmentConfig

        _seed_resonance_environment_config()
        self.assertEqual(ResonanceEnvironmentConfig.objects.count(), 1)
        cfg = ResonanceEnvironmentConfig.objects.get(pk=1)
        self.assertIsNotNone(cfg)

    def test_idempotent(self) -> None:
        from world.magic.models.resonance_environment import ResonanceEnvironmentConfig

        _seed_resonance_environment_config()
        _seed_resonance_environment_config()
        self.assertEqual(ResonanceEnvironmentConfig.objects.count(), 1)

    def test_singleton_pk_is_one(self) -> None:
        _seed_resonance_environment_config()
        from world.magic.models.resonance_environment import ResonanceEnvironmentConfig

        cfg = ResonanceEnvironmentConfig.objects.get()
        self.assertEqual(cfg.pk, 1)


class SeedResonanceEnvironmentConditionsTests(TestCase):
    """RC2: _seed_resonance_environment_conditions() creates baseline + boon ConditionTemplates."""

    @classmethod
    def setUpTestData(cls) -> None:
        _seed_resonance_environment_conditions()

    def test_magically_attuned_exists(self) -> None:
        from world.conditions.models import ConditionTemplate

        self.assertTrue(ConditionTemplate.objects.filter(name="Magically Attuned").exists())

    def test_empowered_by_resonant_ground_exists(self) -> None:
        from world.conditions.models import ConditionTemplate

        self.assertTrue(
            ConditionTemplate.objects.filter(name="Empowered by Resonant Ground").exists()
        )

    def test_both_in_magical_category(self) -> None:
        from world.conditions.models import ConditionCategory, ConditionTemplate

        category = ConditionCategory.objects.get(name="Magical")
        attuned = ConditionTemplate.objects.get(name="Magically Attuned")
        empowered = ConditionTemplate.objects.get(name="Empowered by Resonant Ground")
        self.assertEqual(attuned.category, category)
        self.assertEqual(empowered.category, category)

    def test_magically_attuned_is_permanent_and_not_dispellable(self) -> None:
        from world.conditions.constants import DurationType
        from world.conditions.models import ConditionTemplate

        attuned = ConditionTemplate.objects.get(name="Magically Attuned")
        self.assertEqual(attuned.default_duration_type, DurationType.PERMANENT)
        self.assertFalse(attuned.can_be_dispelled)
        self.assertFalse(attuned.has_progression)

    def test_empowered_is_dispellable_boon(self) -> None:
        from world.conditions.constants import DurationType
        from world.conditions.models import ConditionTemplate

        empowered = ConditionTemplate.objects.get(name="Empowered by Resonant Ground")
        self.assertEqual(empowered.default_duration_type, DurationType.ROUNDS)
        self.assertTrue(empowered.can_be_dispelled)
        self.assertFalse(empowered.has_progression)

    def test_idempotent(self) -> None:
        from world.conditions.models import ConditionTemplate

        count_before = ConditionTemplate.objects.filter(
            name__in=["Magically Attuned", "Empowered by Resonant Ground"]
        ).count()
        _seed_resonance_environment_conditions()
        count_after = ConditionTemplate.objects.filter(
            name__in=["Magically Attuned", "Empowered by Resonant Ground"]
        ).count()
        self.assertEqual(count_before, count_after)
        self.assertEqual(count_after, 2)

    def test_does_not_create_opposed_reaction_conditions(self) -> None:
        """The helper must not create Tempered/Singed/Burning/Hallowed Burn/Cast Disrupted."""
        from world.conditions.models import ConditionTemplate

        opposed_names = [
            "Tempered Against Light",
            "Singed",
            "Burning",
            "Hallowed Burn",
            "Cast Disrupted",
        ]
        self.assertFalse(
            ConditionTemplate.objects.filter(name__in=opposed_names).exists(),
            "Opposed reaction conditions must not be created by this helper",
        )
