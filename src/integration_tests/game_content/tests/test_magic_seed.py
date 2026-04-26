"""Tests for seed_magic_config() — Task 1.1, seed_canonical_rituals() — Task 1.2,
seed_thread_pull_catalog() — Task 1.3, and seed_cantrip_starter_catalog() — Task 1.8.

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
"""

from django.test import TestCase

from integration_tests.game_content.magic import (
    CantripStarterCatalogResult,
    MagicConfigResult,
    RitualSeedResult,
    ThreadPullCatalogResult,
    seed_canonical_rituals,
    seed_cantrip_starter_catalog,
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
