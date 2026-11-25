"""The shared bonus valuation and the sheet's Bonuses band (#5206)."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import ModifierLane, ModifierSize
from world.checks.modifier_models import ModifierValue
from world.checks.modifier_values import load_value_table
from world.classes.factories import CharacterClassLevelFactory
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionEffectFactory,
    DistinctionFactory,
)
from world.forms.factories import FormTraitFactory
from world.mechanics.bonuses import bonus_groups_for_sheet
from world.mechanics.constants import AmountInput
from world.mechanics.factories import (
    CharacterModifierFactory,
    ModifierCategoryFactory,
    ModifierSourceFactory,
    ModifierTargetFactory,
)
from world.mechanics.services import (
    create_distinction_modifiers,
    get_modifier_breakdown,
    sheet_derived_reader,
    value_held_effects,
)
from world.mechanics.types import BonusRow, BonusSource, HeldEffect


def _grant(sheet, distinction, *, rank: int = 1, **held):
    """Hold ``distinction`` on ``sheet`` and write its modifier rows, as finalize does."""
    held_row = CharacterDistinctionFactory(
        character=sheet, distinction=distinction, rank=rank, **held
    )
    create_distinction_modifiers(held_row)
    return held_row


class SharedValuationMatchesBreakdownTests(TestCase):
    """``value_held_effects`` gives what ``get_modifier_breakdown`` gives a character."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(character=cls.sheet, level=3)
        cls.target = ModifierTargetFactory(name="bonus_valuation_target")
        flat = DistinctionFactory(name="Flat Card")
        cls.flat = DistinctionEffectFactory(distinction=flat, target=cls.target, value_per_rank=4)
        amp = DistinctionFactory(name="Amplifier Card")
        cls.amp = DistinctionEffectFactory(
            distinction=amp, target=cls.target, value_per_rank=2, amplifies_sources_by=3
        )
        shield = DistinctionFactory(name="Immunity Card")
        cls.shield = DistinctionEffectFactory(
            distinction=shield,
            target=cls.target,
            value_per_rank=1,
            grants_immunity_to_negative=True,
        )
        flaw = DistinctionFactory(name="Flaw Card")
        cls.flaw = DistinctionEffectFactory(distinction=flaw, target=cls.target, value_per_rank=-20)
        sized = DistinctionFactory(name="Sized Card", max_rank=3)
        cls.sized = DistinctionEffectFactory(
            distinction=sized,
            target=cls.target,
            value_per_rank=5,
            modifier_size=ModifierSize.MINOR,
        )
        derived = DistinctionFactory(name="Derived Card")
        cls.derived = DistinctionEffectFactory(
            distinction=derived,
            target=cls.target,
            value_per_rank=2,
            amount_input=AmountInput.CHARACTER_LEVEL,
            amount_per=1,
        )
        ModifierValue.objects.create(
            lane=ModifierLane.CHECK, level=3, size=ModifierSize.MINOR, value=11
        )
        for distinction, rank in (
            (flat, 1),
            (amp, 1),
            (shield, 1),
            (flaw, 1),
            (sized, 2),
            (derived, 1),
        ):
            _grant(cls.sheet, distinction, rank=rank)

    def test_shared_valuation_equals_breakdown(self) -> None:
        breakdown = get_modifier_breakdown(self.sheet, self.target, value_lane=ModifierLane.CHECK)
        held = [
            HeldEffect(effect=self.flat, rank=1, value=4),
            HeldEffect(effect=self.amp, rank=1, value=2),
            HeldEffect(effect=self.shield, rank=1, value=1),
            HeldEffect(effect=self.flaw, rank=1, value=-20),
            HeldEffect(effect=self.sized, rank=2, value=10),
            HeldEffect(effect=self.derived, rank=1, value=2),
        ]
        valuation = value_held_effects(
            held,
            level=3,
            value_table=load_value_table(ModifierLane.CHECK),
            derived_reader=sheet_derived_reader(self.sheet),
        )

        self.assertEqual(valuation.total, breakdown.total)
        self.assertEqual(valuation.has_immunity, breakdown.has_immunity)
        self.assertEqual(valuation.negatives_blocked, breakdown.negatives_blocked)
        by_name = {source.source_name: source for source in breakdown.sources}
        for source in valuation.sources:
            self.assertEqual(source, by_name[source.source_name])

    def test_each_rule_applies(self) -> None:
        """Hand-worked: amplifier +3 to every other source, the flaw blocked, the sized
        effect read from the table at level 3, the derived one 2 per level."""
        valuation = value_held_effects(
            [
                HeldEffect(effect=self.flat, rank=1, value=4),
                HeldEffect(effect=self.amp, rank=1, value=2),
                HeldEffect(effect=self.shield, rank=1, value=1),
                HeldEffect(effect=self.flaw, rank=1, value=-20),
                HeldEffect(effect=self.sized, rank=2, value=10),
                HeldEffect(effect=self.derived, rank=1, value=2),
            ],
            level=3,
            value_table=load_value_table(ModifierLane.CHECK),
            derived_reader=lambda _effect, per_step: per_step * 3,
        )

        finals = [source.final_value for source in valuation.sources]
        # flat 4+3, amp 2, shield 1+3, flaw -20+3 blocked, sized 11+3, derived 6+3.
        self.assertEqual(finals, [7, 2, 4, -17, 14, 9])
        self.assertEqual(valuation.total, 7 + 2 + 4 + 14 + 9)
        self.assertEqual(valuation.negatives_blocked, 1)


class BonusGroupsForSheetTests(TestCase):
    """``bonus_groups_for_sheet`` totals, names, groups and leaves out what it should."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.aspect = ModifierCategoryFactory(name="aspect", display_order=1)
        cls.roll = ModifierCategoryFactory(name="roll_modifier", display_order=2)
        cls.creation = ModifierCategoryFactory(name="character_creation", display_order=0)
        cls.martial = ModifierTargetFactory(
            category=cls.aspect, name="martial", display_order=1, description="Of war."
        )
        cls.warfare = ModifierTargetFactory(category=cls.aspect, name="warfare", display_order=0)
        cls.poise = ModifierTargetFactory(category=cls.roll, name="poise", display_order=0)
        cls.allure = ModifierTargetFactory(category=cls.roll, name="allure", display_order=1)
        cls.zeroed = ModifierTargetFactory(category=cls.roll, name="zeroed", display_order=2)
        cls.picks = ModifierTargetFactory(
            category=cls.creation, name="starting_technique_picks", spent_at_creation=True
        )

        soldier = DistinctionFactory(name="Example Soldier")
        DistinctionEffectFactory(distinction=soldier, target=cls.martial, value_per_rank=5)
        DistinctionEffectFactory(distinction=soldier, target=cls.warfare, value_per_rank=5)
        DistinctionEffectFactory(distinction=soldier, target=cls.picks, value_per_rank=2)
        DistinctionEffectFactory(distinction=soldier, target=cls.zeroed, value_per_rank=3)
        child = DistinctionFactory(name="Example Drillmaster's Child", max_rank=3)
        DistinctionEffectFactory(distinction=child, target=cls.martial, value_per_rank=5)
        stiff = DistinctionFactory(name="Example Stiff Manner")
        DistinctionEffectFactory(distinction=stiff, target=cls.poise, value_per_rank=-10)
        DistinctionEffectFactory(distinction=stiff, target=cls.zeroed, value_per_rank=-3)
        alluring = DistinctionFactory(name="Alluring", max_rank=3)
        DistinctionEffectFactory(distinction=alluring, target=cls.allure, value_per_rank=1)

        _grant(cls.sheet, soldier)
        _grant(cls.sheet, child, rank=2)
        _grant(cls.sheet, stiff)
        _grant(cls.sheet, alluring, rank=2, feature_trait=FormTraitFactory(name="hair_color"))
        _grant(cls.sheet, alluring, rank=3, feature_trait=FormTraitFactory(name="eye_color"))
        CharacterModifierFactory(
            character=cls.sheet,
            target=cls.allure,
            value=1,
            source=ModifierSourceFactory(residence_comfort=True),
        )

    def _rows(self) -> dict[str, BonusRow]:
        return {
            row.target_name: row
            for group in bonus_groups_for_sheet(self.sheet)
            for row in group.rows
        }

    def test_groups_and_rows_follow_display_order(self) -> None:
        groups = bonus_groups_for_sheet(self.sheet)

        self.assertEqual([g.heading for g in groups], ["Aspect", "Roll modifier"])
        self.assertEqual([r.label for r in groups[0].rows], ["warfare", "martial"])
        self.assertEqual([r.label for r in groups[1].rows], ["poise", "allure"])

    def test_two_cards_on_one_target_total_and_name_their_shares(self) -> None:
        martial = self._rows()["martial"]

        self.assertEqual(martial.total, 15)
        self.assertEqual(martial.definition, "Of war.")
        self.assertCountEqual(
            martial.sources,
            [
                BonusSource(label="Example Soldier", value=5),
                BonusSource(label="Example Drillmaster's Child (Rank 2)", value=10),
            ],
        )

    def test_negative_card(self) -> None:
        poise = self._rows()["poise"]

        self.assertEqual(poise.total, -10)
        self.assertEqual(poise.sources, (BonusSource(label="Example Stiff Manner", value=-10),))

    def test_card_on_two_features_and_home_comfort(self) -> None:
        allure = self._rows()["allure"]

        self.assertEqual(allure.total, 2 + 3 + 1)
        self.assertCountEqual(
            allure.sources,
            [
                BonusSource(label="Alluring on hair color (Rank 2)", value=2),
                BonusSource(label="Alluring on eye color (Rank 3)", value=3),
                BonusSource(label="Residence comfort", value=1),
            ],
        )

    def test_spent_at_creation_and_zero_totals_are_left_out(self) -> None:
        rows = self._rows()

        self.assertNotIn("starting_technique_picks", rows)
        self.assertNotIn("zeroed", rows)

    def test_immunity_row_is_kept_at_zero(self) -> None:
        sheet = CharacterSheetFactory()
        fear = ModifierTargetFactory(category=self.roll, name="fear")
        brave = DistinctionFactory(name="Brave")
        DistinctionEffectFactory(
            distinction=brave, target=fear, value_per_rank=0, grants_immunity_to_negative=True
        )
        _grant(sheet, brave)

        (group,) = bonus_groups_for_sheet(sheet)
        (row,) = group.rows

        self.assertEqual(row.total, 0)
        self.assertTrue(row.immune)

    def test_query_count_is_bounded(self) -> None:
        """One read of the rows and one of the rank sizes, however many targets."""
        with self.assertNumQueries(2):
            bonus_groups_for_sheet(self.sheet)
