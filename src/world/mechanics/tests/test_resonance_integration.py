"""Tests for distinction resonance integration (#1834 Task 5).

Historically, distinction effects targeting a resonance-category ModifierTarget wrote a
resonance-CATEGORY `CharacterModifier` row (asserted by this file's tests pre-#1834). That
reader (`get_aura_percentages`) was removed in #1836, making those rows write-only dead
data. This task stops writing them and instead wires
`reconcile_distinction_resonance_grants` (the `DistinctionResonanceGrant` sidecar) into
`create_distinction_modifiers`/`update_distinction_rank` — so a distinction's resonance
effect flows through the real currency mechanism (`CharacterResonance` +
`ResonanceGrant` ledger) instead of a dead `CharacterModifier` row. Non-resonance
distinction effects are unaffected and still materialize `CharacterModifier` rows exactly
as before.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionEffectFactory,
    DistinctionFactory,
)
from world.magic.constants import GainSource
from world.magic.factories import (
    AffinityFactory,
    DistinctionResonanceGrantFactory,
    ResonanceFactory,
)
from world.magic.models import CharacterResonance, ResonanceGrant
from world.mechanics.constants import RESONANCE_CATEGORY_NAME
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.models import CharacterModifier
from world.mechanics.services import (
    create_distinction_modifiers,
    delete_distinction_modifiers,
    update_distinction_rank,
)


def _resonance_modifier_total(character_sheet, resonance):
    """Sum CharacterModifier values for a specific resonance via its target."""
    return sum(
        m.value
        for m in CharacterModifier.objects.filter(
            character=character_sheet,
            target__category__name=RESONANCE_CATEGORY_NAME,
            target__target_resonance=resonance,
        )
    )


class DistinctionResonanceModifierSkippedTest(TestCase):
    """Resonance-CATEGORY distinction effects no longer write CharacterModifier rows."""

    @classmethod
    def setUpTestData(cls):
        cls.character_sheet = CharacterSheetFactory()
        cls.character = cls.character_sheet.character

        cls.abyssal = AffinityFactory(name="Abyssal")

        resonance_category = ModifierCategoryFactory(name=RESONANCE_CATEGORY_NAME)
        cls.serenity = ResonanceFactory(name="Serenity", affinity=cls.abyssal)
        cls.serenity_target = ModifierTargetFactory(
            name="Serenity", category=resonance_category, target_resonance=cls.serenity
        )

        # Non-resonance ModifierTarget for comparison.
        cls.allure = ModifierTargetFactory(name="Allure")

    def test_resonance_effect_creates_no_character_modifier(self):
        """A resonance-category-targeted effect creates no CharacterModifier row at all."""
        patient = DistinctionFactory(name="Patient", max_rank=3)
        DistinctionEffectFactory(
            distinction=patient,
            target=self.serenity_target,
            value_per_rank=10,
        )

        char_dist = CharacterDistinctionFactory(
            character=self.character_sheet,
            distinction=patient,
            rank=1,
        )
        create_distinction_modifiers(char_dist)

        self.assertEqual(_resonance_modifier_total(self.character_sheet, self.serenity), 0)
        self.assertFalse(
            CharacterModifier.objects.filter(
                character=self.character_sheet,
                target__category__name=RESONANCE_CATEGORY_NAME,
            ).exists()
        )

    def test_non_resonance_effect_still_creates_modifier(self):
        """Effects targeting non-resonance targets are unaffected — still create a modifier."""
        charming = DistinctionFactory(name="Charming")
        DistinctionEffectFactory(
            distinction=charming,
            target=self.allure,
            value_per_rank=5,
        )

        char_dist = CharacterDistinctionFactory(
            character=self.character_sheet,
            distinction=charming,
            rank=1,
        )
        modifiers = create_distinction_modifiers(char_dist)

        self.assertEqual(len(modifiers), 1)
        self.assertEqual(
            CharacterModifier.objects.filter(
                character=self.character_sheet,
                target=self.allure,
            ).count(),
            1,
        )
        self.assertFalse(
            CharacterModifier.objects.filter(
                character=self.character_sheet,
                target__category__name=RESONANCE_CATEGORY_NAME,
            ).exists()
        )

    def test_mixed_effects_only_skip_the_resonance_one(self):
        """A distinction with both a resonance and non-resonance effect only skips the former."""
        zen = DistinctionFactory(name="Zen Master", max_rank=3)
        DistinctionEffectFactory(
            distinction=zen,
            target=self.serenity_target,
            value_per_rank=5,
        )
        DistinctionEffectFactory(
            distinction=zen,
            target=self.allure,
            value_per_rank=8,
        )

        char_dist = CharacterDistinctionFactory(
            character=self.character_sheet,
            distinction=zen,
            rank=2,
        )
        modifiers = create_distinction_modifiers(char_dist)

        self.assertEqual(len(modifiers), 1)
        self.assertEqual(modifiers[0].target, self.allure)
        self.assertEqual(modifiers[0].value, 16)  # 8 * rank 2
        self.assertFalse(
            CharacterModifier.objects.filter(
                character=self.character_sheet,
                target__category__name=RESONANCE_CATEGORY_NAME,
            ).exists()
        )

    def test_delete_distinction_modifiers_unaffected(self):
        """delete_distinction_modifiers still cleans up the non-resonance modifier."""
        charming = DistinctionFactory(name="Charming2")
        DistinctionEffectFactory(
            distinction=charming,
            target=self.allure,
            value_per_rank=5,
        )
        char_dist = CharacterDistinctionFactory(
            character=self.character_sheet,
            distinction=charming,
            rank=1,
        )
        create_distinction_modifiers(char_dist)

        deleted_count = delete_distinction_modifiers(char_dist)

        self.assertEqual(deleted_count, 1)
        self.assertFalse(CharacterModifier.objects.filter(character=self.character_sheet).exists())


class DistinctionGrantReconcilesResonanceTest(TestCase):
    """Granting/ranking a CharacterDistinction reconciles its DistinctionResonanceGrant rows."""

    @classmethod
    def setUpTestData(cls):
        cls.character_sheet = CharacterSheetFactory()
        cls.character = cls.character_sheet.character
        cls.resonance = ResonanceFactory(name="Devotion")

    def test_create_distinction_modifiers_claims_and_seeds_resonance(self):
        """Granting a distinction with a DistinctionResonanceGrant claims + seeds resonance."""
        devoted = DistinctionFactory(name="Devoted", max_rank=3)
        DistinctionResonanceGrantFactory(
            distinction=devoted, resonance=self.resonance, flat_amount_per_rank=10
        )

        char_dist = CharacterDistinctionFactory(
            character=self.character_sheet,
            distinction=devoted,
            rank=2,
        )
        create_distinction_modifiers(char_dist)

        character_resonance = CharacterResonance.objects.get(
            character_sheet=self.character_sheet, resonance=self.resonance
        )
        self.assertEqual(character_resonance.lifetime_earned, 20)  # 10 * rank 2

        grants = ResonanceGrant.objects.filter(
            source=GainSource.DISTINCTION,
            source_character_distinction=char_dist,
            resonance=self.resonance,
        )
        self.assertEqual(grants.count(), 1)
        self.assertEqual(grants.first().amount, 20)

    def test_update_distinction_rank_tops_off_resonance_seed(self):
        """A rank change re-reconciles and tops off the flat seed to the new rank."""
        devoted = DistinctionFactory(name="Devoted2", max_rank=5)
        DistinctionResonanceGrantFactory(
            distinction=devoted, resonance=self.resonance, flat_amount_per_rank=10
        )

        char_dist = CharacterDistinctionFactory(
            character=self.character_sheet,
            distinction=devoted,
            rank=1,
        )
        create_distinction_modifiers(char_dist)
        character_resonance = CharacterResonance.objects.get(
            character_sheet=self.character_sheet, resonance=self.resonance
        )
        self.assertEqual(character_resonance.lifetime_earned, 10)

        char_dist.rank = 3
        char_dist.save(update_fields=["rank"])
        update_distinction_rank(char_dist)

        character_resonance.refresh_from_db()
        self.assertEqual(character_resonance.lifetime_earned, 30)
        grants = ResonanceGrant.objects.filter(
            source=GainSource.DISTINCTION,
            source_character_distinction=char_dist,
            resonance=self.resonance,
        )
        self.assertEqual(grants.count(), 2)  # initial seed + rank-up top-off

    def test_grant_without_resonance_grant_is_a_no_op(self):
        """A distinction with no DistinctionResonanceGrant row reconciles to nothing."""
        plain = DistinctionFactory(name="Plain")
        char_dist = CharacterDistinctionFactory(
            character=self.character_sheet,
            distinction=plain,
            rank=1,
        )

        create_distinction_modifiers(char_dist)

        self.assertFalse(
            CharacterResonance.objects.filter(character_sheet=self.character_sheet).exists()
        )
