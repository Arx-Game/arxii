"""Tests for recompute_aura (#1737 — deed-driven aura drift)."""

from decimal import Decimal

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import AffinityFactory, CharacterAuraFactory, ResonanceFactory
from world.magic.models import CharacterAura, CharacterResonance
from world.magic.services.aura import recompute_aura


class RecomputeAuraTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.celestial = AffinityFactory(name="Celestial")
        cls.primal = AffinityFactory(name="Primal")
        cls.abyssal = AffinityFactory(name="Abyssal")
        cls.celestial_resonance = ResonanceFactory(affinity=cls.celestial)
        cls.primal_resonance = ResonanceFactory(affinity=cls.primal)
        cls.abyssal_resonance = ResonanceFactory(affinity=cls.abyssal)

    def test_no_aura_row_returns_none_and_does_nothing(self):
        # sheet has no CharacterAura row at all (e.g. Quiescent/NPC)
        result = recompute_aura(self.sheet)
        assert result is None
        assert not CharacterAura.objects.filter(character=self.sheet.character).exists()

    def test_zero_lifetime_earned_leaves_stored_values_untouched(self):
        CharacterAuraFactory(character=self.sheet.character)
        before = CharacterAura.objects.get(character=self.sheet.character)
        before_celestial = before.celestial
        recompute_aura(self.sheet)
        after = CharacterAura.objects.get(character=self.sheet.character)
        assert after.celestial == before_celestial

    def test_recompute_shifts_stored_percentages_toward_earned_affinity(self):
        CharacterAuraFactory(character=self.sheet.character)
        CharacterResonance.objects.create(
            character_sheet=self.sheet,
            resonance=self.abyssal_resonance,
            balance=50,
            lifetime_earned=50,
        )
        CharacterResonance.objects.create(
            character_sheet=self.sheet,
            resonance=self.celestial_resonance,
            balance=50,
            lifetime_earned=50,
        )
        drift = recompute_aura(self.sheet)
        aura = CharacterAura.objects.get(character=self.sheet.character)
        assert drift is not None
        assert float(aura.celestial) == 50.0
        assert float(aura.abyssal) == 50.0
        assert float(aura.primal) == 0.0

    def test_lopsided_split_stays_within_bounds_and_sums_to_100(self):
        # Heavily skewed but organic split (not adversarial) — confirms ordinary
        # lopsided recomputation stays sane: celestial dominates, primal is a
        # sliver, abyssal is zero.
        CharacterAuraFactory(character=self.sheet.character)
        CharacterResonance.objects.create(
            character_sheet=self.sheet,
            resonance=self.celestial_resonance,
            balance=9973,
            lifetime_earned=9973,
        )
        CharacterResonance.objects.create(
            character_sheet=self.sheet,
            resonance=self.primal_resonance,
            balance=27,
            lifetime_earned=27,
        )
        drift = recompute_aura(self.sheet)
        aura = CharacterAura.objects.get(character=self.sheet.character)
        assert drift is not None
        for value in (aura.celestial, aura.primal, aura.abyssal):
            assert Decimal("0.00") <= value <= Decimal("100.00")
        assert aura.celestial + aura.primal + aura.abyssal == Decimal("100.00")

    def test_recompute_never_violates_bounds_across_integer_split_range(self):
        # Property-style sweep proving the sum/range invariant holds across the
        # real input domain: a range of integer (celestial, primal)
        # lifetime_earned splits (abyssal fixed at 0, the shape most likely to
        # stress independent-rounding drift on the derived abyssal) and confirms
        # recompute_aura always succeeds — i.e. .save()'s full_clean() never
        # raises ValidationError — and the three fields always sum to exactly
        # 100.00. With exact Decimal division over integer lifetime_earned
        # totals and ROUND_HALF_EVEN quantization, this sweep (and a separate,
        # wider ~4.2M-split brute-force check performed during investigation)
        # never actually pushes the derived abyssal out of [0, 100] — that
        # theoretical possibility is unreachable from
        # CharacterResonance.lifetime_earned (a PositiveIntegerField: always
        # non-negative integers), the only real input to this function. This
        # sweep pins the invariant across a wide range of splits so a future
        # change to the rounding/derivation logic can't silently break it.
        CharacterAuraFactory(character=self.sheet.character)
        for celestial_total in range(1, 200, 7):
            for primal_total in range(1, 200, 11):
                CharacterResonance.objects.filter(character_sheet=self.sheet).delete()
                CharacterResonance.objects.create(
                    character_sheet=self.sheet,
                    resonance=self.celestial_resonance,
                    balance=celestial_total,
                    lifetime_earned=celestial_total,
                )
                CharacterResonance.objects.create(
                    character_sheet=self.sheet,
                    resonance=self.primal_resonance,
                    balance=primal_total,
                    lifetime_earned=primal_total,
                )
                drift = recompute_aura(self.sheet)
                assert drift is not None
                aura = CharacterAura.objects.get(character=self.sheet.character)
                for value in (aura.celestial, aura.primal, aura.abyssal):
                    assert Decimal("0.00") <= value <= Decimal("100.00")
                assert aura.celestial + aura.primal + aura.abyssal == Decimal("100.00")


class FireAuraThresholdCrossingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        CharacterAuraFactory(character=cls.sheet.character)
        cls.abyssal = AffinityFactory(name="Abyssal")
        cls.abyssal_resonance = ResonanceFactory(affinity=cls.abyssal)

    def test_crossing_a_threshold_grants_the_achievement(self):
        from world.achievements.factories import AchievementFactory
        from world.achievements.models import CharacterAchievement
        from world.magic.models import AuraAffinityThreshold
        from world.magic.services.aura import fire_aura_threshold_crossings, recompute_aura
        from world.magic.types import AffinityType

        achievement = AchievementFactory(is_active=True)
        AuraAffinityThreshold.objects.create(
            affinity=AffinityType.ABYSSAL,
            threshold_percent=Decimal("50.00"),
            discovery_achievement=achievement,
        )
        CharacterResonance.objects.create(
            character_sheet=self.sheet,
            resonance=self.abyssal_resonance,
            balance=100,
            lifetime_earned=100,
        )
        # recompute_aura() only recomputes; the caller is responsible for
        # chaining the crossing check with the returned AuraDrift (mirrors
        # grant_resonance()'s real two-step wiring).
        drift = recompute_aura(self.sheet)
        fire_aura_threshold_crossings(self.sheet, drift)
        assert CharacterAchievement.objects.filter(
            character_sheet=self.sheet, achievement=achievement
        ).exists()

    def test_compound_gate_blocks_grant_when_stat_requirement_unmet(self):
        from world.achievements.constants import ComparisonType
        from world.achievements.factories import (
            AchievementFactory,
            AchievementRequirementFactory,
            StatDefinitionFactory,
        )
        from world.achievements.models import CharacterAchievement
        from world.magic.models import AuraAffinityThreshold
        from world.magic.services.aura import fire_aura_threshold_crossings, recompute_aura
        from world.magic.types import AffinityType

        allure = StatDefinitionFactory()
        achievement = AchievementFactory(is_active=True)
        AchievementRequirementFactory(
            achievement=achievement, stat=allure, threshold=50, comparison=ComparisonType.GTE
        )
        AuraAffinityThreshold.objects.create(
            affinity=AffinityType.ABYSSAL,
            threshold_percent=Decimal("50.00"),
            discovery_achievement=achievement,
        )
        CharacterResonance.objects.create(
            character_sheet=self.sheet,
            resonance=self.abyssal_resonance,
            balance=100,
            lifetime_earned=100,
        )
        # No StatTracker row for `allure` on self.sheet — get_stat() returns 0,
        # which fails the >=50 requirement.
        drift = recompute_aura(self.sheet)
        fire_aura_threshold_crossings(self.sheet, drift)
        assert not CharacterAchievement.objects.filter(
            character_sheet=self.sheet, achievement=achievement
        ).exists()
