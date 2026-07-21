"""Tests for the shared post-CG distinction acquisition seam (#2037)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.exceptions import DistinctionExclusionError
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionEffectFactory,
    DistinctionFactory,
)
from world.distinctions.models import CharacterDistinction
from world.distinctions.services import grant_distinction
from world.distinctions.types import DistinctionOrigin
from world.magic.factories import DistinctionResonanceGrantFactory, ResonanceFactory
from world.magic.models import CharacterResonance
from world.mechanics.factories import ModifierTargetFactory
from world.mechanics.models import CharacterModifier
from world.mechanics.services import create_distinction_modifiers


class GrantDistinctionNewGrantTests(TestCase):
    """A character who does not yet hold the distinction."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.target = ModifierTargetFactory(name="Allure")
        cls.distinction = DistinctionFactory(name="Silver Tongue", max_rank=3)
        DistinctionEffectFactory(distinction=cls.distinction, target=cls.target, value_per_rank=5)
        cls.resonance = ResonanceFactory()
        DistinctionResonanceGrantFactory(
            distinction=cls.distinction, resonance=cls.resonance, flat_amount_per_rank=10
        )

    def test_new_grant_mints_at_rank_1_with_origin(self) -> None:
        cd = grant_distinction(self.sheet, self.distinction, origin=DistinctionOrigin.GM_AWARD)

        self.assertEqual(cd.rank, 1)
        self.assertEqual(cd.origin, DistinctionOrigin.GM_AWARD)
        self.assertEqual(cd.character_id, self.sheet.character_id)
        self.assertTrue(
            CharacterDistinction.objects.filter(
                character=self.sheet, distinction=self.distinction
            ).exists()
        )

    def test_new_grant_fires_modifier_cascade(self) -> None:
        grant_distinction(self.sheet, self.distinction, origin=DistinctionOrigin.GM_AWARD)

        self.assertEqual(
            CharacterModifier.objects.filter(character=self.sheet, target=self.target).count(),
            1,
        )

    def test_new_grant_fires_resonance_seed_cascade(self) -> None:
        grant_distinction(self.sheet, self.distinction, origin=DistinctionOrigin.GM_AWARD)

        cr = CharacterResonance.objects.get(character_sheet=self.sheet, resonance=self.resonance)
        self.assertEqual(cr.lifetime_earned, 10)

    def test_explicit_rank_on_new_grant_sets_that_rank(self) -> None:
        cd = grant_distinction(
            self.sheet, self.distinction, origin=DistinctionOrigin.GM_AWARD, rank=2
        )

        self.assertEqual(cd.rank, 2)


class GrantDistinctionRepeatGrantTests(TestCase):
    """A character who already holds the distinction."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.distinction = DistinctionFactory(name="Silver Tongue", max_rank=3)
        cls.target = ModifierTargetFactory(name="Allure")
        DistinctionEffectFactory(distinction=cls.distinction, target=cls.target, value_per_rank=5)
        cls.resonance = ResonanceFactory()
        DistinctionResonanceGrantFactory(
            distinction=cls.distinction, resonance=cls.resonance, flat_amount_per_rank=10
        )
        cls.existing = CharacterDistinctionFactory(
            character=cls.sheet,
            distinction=cls.distinction,
            rank=1,
            origin=DistinctionOrigin.CHARACTER_CREATION,
        )
        # The factory bypasses the CG-time cascade -- mirror it here so the
        # rank-up regression test below has a real rank-1 modifier + resonance
        # seed to recompute/top off (closes the stale-rank-regression blind
        # spot: #2037 Task 1 review).
        create_distinction_modifiers(cls.existing)

    def test_rank_up_recomputes_modifier_and_tops_off_resonance(self) -> None:
        """Ranking an EXISTING holder 1->2 must recompute stale modifiers/seeds.

        Regression guard: ``update_distinction_rank`` only touches
        ``CharacterModifier`` rows that already exist for this
        ``CharacterDistinction`` -- if the rank-up path ever stopped calling it
        (or called ``create_distinction_modifiers`` again instead), the modifier
        would either stay frozen at its rank-1 value or duplicate.
        """
        cd = grant_distinction(self.sheet, self.distinction, origin=DistinctionOrigin.GM_AWARD)

        self.assertEqual(cd.rank, 2)
        modifier = CharacterModifier.objects.get(character=self.sheet, target=self.target)
        self.assertEqual(modifier.value, 10)  # value_per_rank(5) * rank(2)

        cr = CharacterResonance.objects.get(character_sheet=self.sheet, resonance=self.resonance)
        self.assertEqual(cr.lifetime_earned, 20)  # flat_amount_per_rank(10) * rank(2)

    def test_repeat_grant_advances_exactly_one(self) -> None:
        cd = grant_distinction(self.sheet, self.distinction, origin=DistinctionOrigin.GM_AWARD)

        self.assertEqual(cd.pk, self.existing.pk)
        self.assertEqual(cd.rank, 2)

    def test_repeat_grant_preserves_original_origin(self) -> None:
        """Rank-up only touches rank — origin reflects the original acquisition."""
        cd = grant_distinction(self.sheet, self.distinction, origin=DistinctionOrigin.GM_AWARD)

        self.assertEqual(cd.origin, DistinctionOrigin.CHARACTER_CREATION)

    def test_at_max_rank_is_noop(self) -> None:
        self.existing.rank = 3
        self.existing.save(update_fields=["rank"])

        cd = grant_distinction(self.sheet, self.distinction, origin=DistinctionOrigin.GM_AWARD)

        self.assertEqual(cd.rank, 3)

    def test_explicit_rank_raises(self) -> None:
        cd = grant_distinction(
            self.sheet, self.distinction, origin=DistinctionOrigin.GM_AWARD, rank=3
        )

        self.assertEqual(cd.rank, 3)

    def test_explicit_rank_lower_than_current_is_noop(self) -> None:
        self.existing.rank = 2
        self.existing.save(update_fields=["rank"])

        cd = grant_distinction(
            self.sheet, self.distinction, origin=DistinctionOrigin.GM_AWARD, rank=1
        )

        self.assertEqual(cd.rank, 2)

    def test_explicit_rank_equal_to_current_is_noop(self) -> None:
        cd = grant_distinction(
            self.sheet, self.distinction, origin=DistinctionOrigin.GM_AWARD, rank=1
        )

        self.assertEqual(cd.rank, 1)


class GrantDistinctionExclusionTests(TestCase):
    """Mutual and variant exclusion enforcement (#2037 Decision 2)."""

    def test_mutual_exclusion_raises(self) -> None:
        sheet = CharacterSheetFactory()
        alpha = DistinctionFactory(name="Alpha")
        beta = DistinctionFactory(name="Beta")
        alpha.mutually_exclusive_with.add(beta)
        CharacterDistinctionFactory(character=sheet, distinction=alpha, rank=1)

        with self.assertRaises(DistinctionExclusionError) as ctx:
            grant_distinction(sheet, beta, origin=DistinctionOrigin.GM_AWARD)

        self.assertTrue(ctx.exception.user_message)

    def test_mutual_exclusion_is_symmetric(self) -> None:
        """The M2M is symmetrical — granting either side conflicts with the other."""
        sheet = CharacterSheetFactory()
        alpha = DistinctionFactory(name="Alpha")
        beta = DistinctionFactory(name="Beta")
        alpha.mutually_exclusive_with.add(beta)
        CharacterDistinctionFactory(character=sheet, distinction=beta, rank=1)

        with self.assertRaises(DistinctionExclusionError):
            grant_distinction(sheet, alpha, origin=DistinctionOrigin.GM_AWARD)

    def test_variant_exclusion_raises(self) -> None:
        sheet = CharacterSheetFactory()
        parent = DistinctionFactory(name="Noble Blood", variants_are_mutually_exclusive=True)
        variant_a = DistinctionFactory(name="Noble Blood (Valardin)", parent_distinction=parent)
        variant_b = DistinctionFactory(name="Noble Blood (Grayson)", parent_distinction=parent)
        CharacterDistinctionFactory(character=sheet, distinction=variant_a, rank=1)

        with self.assertRaises(DistinctionExclusionError) as ctx:
            grant_distinction(sheet, variant_b, origin=DistinctionOrigin.GM_AWARD)

        self.assertTrue(ctx.exception.user_message)

    def test_variant_exclusion_does_not_block_rank_up_of_the_held_variant(self) -> None:
        """Ranking up the already-held variant is not a self-conflict."""
        sheet = CharacterSheetFactory()
        parent = DistinctionFactory(name="Noble Blood", variants_are_mutually_exclusive=True)
        variant_a = DistinctionFactory(
            name="Noble Blood (Valardin)", parent_distinction=parent, max_rank=3
        )
        CharacterDistinctionFactory(character=sheet, distinction=variant_a, rank=1)

        cd = grant_distinction(sheet, variant_a, origin=DistinctionOrigin.GM_AWARD)

        self.assertEqual(cd.rank, 2)

    def test_no_conflict_when_variants_not_mutually_exclusive(self) -> None:
        sheet = CharacterSheetFactory()
        parent = DistinctionFactory(name="Hair Color", variants_are_mutually_exclusive=False)
        variant_a = DistinctionFactory(name="Hair (Red)", parent_distinction=parent)
        variant_b = DistinctionFactory(name="Hair (Black)", parent_distinction=parent)
        CharacterDistinctionFactory(character=sheet, distinction=variant_a, rank=1)

        cd = grant_distinction(sheet, variant_b, origin=DistinctionOrigin.GM_AWARD)

        self.assertEqual(cd.rank, 1)
