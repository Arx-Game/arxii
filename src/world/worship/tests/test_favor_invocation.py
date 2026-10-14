"""Invoking favor (#4333 slice 1): favor targets, totals, earning rate, the invocation.

Numbers follow the issue's walkthrough B: base Daunting 75, Chosen ease 30, favor
eases 15 at 30 and 30 at 60, a floor of Trivial 15, and bonuses of +15 / +10 / +5 /
0 / 0 by outcome. The invocation roll is forced through ``force_check_outcome``;
everything else is the real service path.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import ModifierSourceKind
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionModifierEffectFactory,
    ConditionTemplateFactory,
)
from world.covenants.factories import CovenantRoleBonusFactory, make_engaged_member
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    CraftedItemRecipeFactory,
    CraftingRecipeModifierFactory,
    EquippedItemFactory,
    ItemInstanceFactory,
    QualityTierFactory,
)
from world.mechanics.constants import (
    FAVOR_EARNING_CATEGORY_NAME,
    FAVOR_INVOCATION_CATEGORY_NAME,
)
from world.mechanics.factories import CharacterModifierFactory
from world.mechanics.models import ModifierTarget
from world.traits.factories import CheckOutcomeFactory
from world.worship.constants import FavorAwardKind
from world.worship.exceptions import FavorInvocationRefused
from world.worship.factories import (
    DevotionConfigFactory,
    DevotionStandingFactory,
    FavorOutcomeAwardFactory,
    WorshipDeclarationFactory,
    WorshippedBeingFactory,
)
from world.worship.favor_services import (
    earning_rate,
    ensure_being_modifier_targets,
    favor_modifier_total,
)
from world.worship.invocation_services import (
    invocation_difficulty,
    invocation_options,
    invoke_favor,
)
from world.worship.models import DevotionStanding, FavorInvocation, PatronageValence
from world.worship.services import bump_devotion, get_chosen_favor_config


def _target(being, category_name: str) -> ModifierTarget:
    return ModifierTarget.objects.get(category__name=category_name, target_being=being)


def _any_target(category_name: str) -> ModifierTarget:
    return ModifierTarget.objects.get(category__name=category_name, target_being__isnull=True)


def _make_chosen(sheet, being, favor: int) -> DevotionStanding:
    return DevotionStandingFactory(
        character_sheet=sheet,
        being=being,
        favor=favor,
        valence=PatronageValence.DEVOTIONAL,
        established_at=timezone.now(),
    )


class FavorTargetTests(TestCase):
    def test_ensure_being_modifier_targets_idempotent(self) -> None:
        being = WorshippedBeingFactory(name="Ombrin")
        first = ensure_being_modifier_targets(being)
        second = ensure_being_modifier_targets(being)

        self.assertEqual([t.pk for t in first], [t.pk for t in second])
        self.assertEqual(
            [t.name for t in first], ["Ombrin favor invocation", "Ombrin favor earning"]
        )
        self.assertEqual(
            ModifierTarget.objects.filter(
                category__name__in=[FAVOR_INVOCATION_CATEGORY_NAME, FAVOR_EARNING_CATEGORY_NAME]
            ).count(),
            4,
        )

    def test_any_being_target_unique(self) -> None:
        ensure_being_modifier_targets(WorshippedBeingFactory())
        ensure_being_modifier_targets(WorshippedBeingFactory())

        for category_name in (FAVOR_INVOCATION_CATEGORY_NAME, FAVOR_EARNING_CATEGORY_NAME):
            self.assertEqual(
                ModifierTarget.objects.filter(
                    category__name=category_name, target_being__isnull=True
                ).count(),
                1,
            )

    def test_one_target_per_category_and_being(self) -> None:
        being = WorshippedBeingFactory()
        target = ensure_being_modifier_targets(being)[0]
        with self.assertRaises(IntegrityError), transaction.atomic():
            ModifierTarget.objects.create(
                category=target.category, name="A second one", target_being=being
            )

    def test_a_target_that_lost_its_being_is_linked_again(self) -> None:
        """A rolled-back release drops target_being and leaves the named targets."""
        being = WorshippedBeingFactory(name="Ombrin")
        first = ensure_being_modifier_targets(being)
        for target in first:
            target.target_being = None
            target.save(update_fields=["target_being"])

        again = ensure_being_modifier_targets(being)

        self.assertEqual([t.pk for t in again], [t.pk for t in first])
        self.assertEqual(ModifierTarget.objects.filter(target_being=being).count(), 2)

    def test_renamed_being_keeps_its_targets(self) -> None:
        being = WorshippedBeingFactory(name="Before")
        ensure_being_modifier_targets(being)
        being.name = "After"
        being.save()
        ensure_being_modifier_targets(being)
        self.assertEqual(ModifierTarget.objects.filter(target_being=being).count(), 2)


class FavorModifierTotalTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.being = WorshippedBeingFactory(name="Ombrin")
        cls.other = WorshippedBeingFactory(name="Wisket")
        ensure_being_modifier_targets(cls.being)
        ensure_being_modifier_targets(cls.other)
        cls.invocation = _target(cls.being, FAVOR_INVOCATION_CATEGORY_NAME)

    def setUp(self) -> None:
        self.character = CharacterFactory(db_key="FavorTotals")
        self.sheet = CharacterSheetFactory(character=self.character, primary_persona=False)

    def test_favor_modifier_total_all_sources(self) -> None:
        # A distinction effect against the being's own target.
        CharacterModifierFactory(
            character=self.sheet, value=15, source__distinction_effect__target=self.invocation
        )
        # A distinction effect against the "any being" target.
        CharacterModifierFactory(
            character=self.sheet,
            value=5,
            source__distinction_effect__target=_any_target(FAVOR_INVOCATION_CATEGORY_NAME),
        )
        # A condition effect.
        condition = ConditionTemplateFactory(name="Blessed by Ombrin")
        ConditionModifierEffectFactory(
            condition=condition, modifier_target=self.invocation, value=10
        )
        ConditionInstanceFactory(target=self.character, condition=condition)
        # A crafted, worn item.
        item = ItemInstanceFactory()
        crafted = CraftedItemRecipeFactory(
            item_instance=item, quality_tier=QualityTierFactory(stat_multiplier=Decimal("1.00"))
        )
        CraftingRecipeModifierFactory(
            recipe=crafted.recipe, target=self.invocation, base_value=3, quality_scale_factor=0
        )
        EquippedItemFactory(
            character=self.sheet,
            item_instance=item,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        self.character.equipped_items.invalidate()

        self.assertEqual(
            favor_modifier_total(self.sheet, self.being, FAVOR_INVOCATION_CATEGORY_NAME),
            15 + 5 + 10 + 3,
        )

    def test_covenant_role_counts_once(self) -> None:
        CharacterClassLevelFactory(
            character=self.sheet, character_class=CharacterClassFactory(), level=2
        )
        self.sheet.invalidate_class_level_cache()
        membership = make_engaged_member(character_sheet=self.sheet)
        self.character.covenant_roles.invalidate()
        CovenantRoleBonusFactory(
            covenant_role=membership.covenant_role,
            modifier_target=self.invocation,
            bonus_per_level=2,
        )
        # Two worn items: a per-item role bonus would count the role twice.
        for region in (BodyRegion.TORSO, BodyRegion.HEAD):
            EquippedItemFactory(
                character=self.sheet,
                item_instance=ItemInstanceFactory(),
                body_region=region,
                equipment_layer=EquipmentLayer.BASE,
            )
        self.character.equipped_items.invalidate()

        # level 2 x 2 per level, once.
        self.assertEqual(
            favor_modifier_total(self.sheet, self.being, FAVOR_INVOCATION_CATEGORY_NAME), 4
        )

    def test_favor_modifier_total_ignores_other_beings(self) -> None:
        CharacterModifierFactory(
            character=self.sheet,
            value=15,
            source__distinction_effect__target=_target(self.other, FAVOR_INVOCATION_CATEGORY_NAME),
        )
        CharacterModifierFactory(
            character=self.sheet,
            value=50,
            source__distinction_effect__target=_target(self.being, FAVOR_EARNING_CATEGORY_NAME),
        )
        self.assertEqual(
            favor_modifier_total(self.sheet, self.being, FAVOR_INVOCATION_CATEGORY_NAME), 0
        )


class EarningRateTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.being = WorshippedBeingFactory(name="Ombrin")
        ensure_being_modifier_targets(cls.being)

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()

    def test_earning_rate_sources(self) -> None:
        self.assertEqual(earning_rate(self.sheet, self.being), 100)

        _make_chosen(self.sheet, self.being, favor=0)
        self.assertEqual(earning_rate(self.sheet, self.being), 200)

        CharacterModifierFactory(
            character=self.sheet,
            value=50,
            source__distinction_effect__target=_target(self.being, FAVOR_EARNING_CATEGORY_NAME),
        )
        self.assertEqual(earning_rate(self.sheet, self.being), 250)

    def test_chosen_bonus_of_zero_restores_todays_rate(self) -> None:
        _make_chosen(self.sheet, self.being, favor=0)
        config = get_chosen_favor_config()
        config.earn_bonus_percent = 0
        config.save()
        self.assertEqual(earning_rate(self.sheet, self.being), 100)

    def test_bump_devotion_scales_positive_amounts(self) -> None:
        _make_chosen(self.sheet, self.being, favor=0)

        bump = bump_devotion(self.sheet, self.being, 3)

        self.assertEqual(bump.credited, 6)
        self.assertEqual(bump.standing.favor, 6)
        self.assertEqual(bump.standing.lifetime_favor, 6)
        # A negative amount is applied as given.
        self.assertEqual(bump_devotion(self.sheet, self.being, -2).standing.favor, 4)

    def test_existing_thresholds_at_scaled_favor(self) -> None:
        """A Chosen reaches the divine intervention threshold in half the base favor."""
        from world.worship.factories import DivineInterventionConfigFactory

        DivineInterventionConfigFactory(favor_threshold=10)
        _make_chosen(self.sheet, self.being, favor=0)

        standing = bump_devotion(self.sheet, self.being, 5).standing

        self.assertEqual(standing.favor, 10)


class InvocationTestBase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.crit = CheckOutcomeFactory(name="Critical Success", success_level=2)
        cls.success = CheckOutcomeFactory(name="Success", success_level=1)
        cls.partial = CheckOutcomeFactory(name="Partial Success", success_level=0)
        cls.failure = CheckOutcomeFactory(name="Failure", success_level=-1)
        cls.botch = CheckOutcomeFactory(name="Critical Failure", success_level=-2)
        cls.check_type = CheckTypeFactory(name="Invocation")
        cls.config = DevotionConfigFactory(invocation_check_type=cls.check_type)
        for outcome, amount in (
            (cls.crit, 15),
            (cls.success, 10),
            (cls.partial, 5),
            (cls.failure, 0),
            (cls.botch, 0),
        ):
            FavorOutcomeAwardFactory(
                config=cls.config,
                kind=FavorAwardKind.INVOCATION,
                outcome_tier=outcome,
                amount=amount,
            )
        cls.being = WorshippedBeingFactory(name="Ombrin")
        ensure_being_modifier_targets(cls.being)

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()

    def _invoke(self, outcome, **kwargs):
        with force_check_outcome(outcome) as capture:
            result = invoke_favor(self.sheet, self.being, actor_name="Ysmay Dunhollow", **kwargs)
        return result, capture


class InvocationDifficultyTests(InvocationTestBase):
    def test_invoke_favor_difficulty(self) -> None:
        # Walkthrough B: Ysmay, Ombrin's Chosen, favor 44: 75 - 30 - 15 = 30, Easy.
        _make_chosen(self.sheet, self.being, favor=44)
        difficulty = invocation_difficulty(self.sheet, self.being)
        self.assertEqual(difficulty.points, 30)
        self.assertEqual(difficulty.band, "easy")
        self.assertEqual(
            [(e.label, e.points) for e in difficulty.eases],
            [
                ("You are Ombrin's Chosen", 30),
                ("Favor 44 (30 or more)", 15),
                ("Favor invocation modifiers for Ombrin", 0),
            ],
        )

    def test_stranger_is_daunting(self) -> None:
        # Tobiah: favor 12, not Chosen, no modifier: Daunting 75.
        DevotionStandingFactory(character_sheet=self.sheet, being=self.being, favor=12)
        difficulty = invocation_difficulty(self.sheet, self.being)
        self.assertEqual((difficulty.points, difficulty.band), (75, "daunting"))

    def test_any_being_and_being_scoped_modifiers_ease(self) -> None:
        # Orla: favor 8, +15 favor invocation against the being: 60, Hard.
        DevotionStandingFactory(character_sheet=self.sheet, being=self.being, favor=8)
        CharacterModifierFactory(
            character=self.sheet,
            value=15,
            source__distinction_effect__target=_target(self.being, FAVOR_INVOCATION_CATEGORY_NAME),
        )
        self.assertEqual(invocation_difficulty(self.sheet, self.being).points, 60)
        CharacterModifierFactory(
            character=self.sheet,
            value=15,
            source__distinction_effect__target=_any_target(FAVOR_INVOCATION_CATEGORY_NAME),
        )
        self.assertEqual(invocation_difficulty(self.sheet, self.being).points, 45)

    def test_high_favor_ease_and_floor(self) -> None:
        _make_chosen(self.sheet, self.being, favor=60)
        # 75 - 30 - 30 = 15: Trivial.
        self.assertEqual(invocation_difficulty(self.sheet, self.being).points, 15)
        CharacterModifierFactory(
            character=self.sheet,
            value=30,
            source__distinction_effect__target=_target(self.being, FAVOR_INVOCATION_CATEGORY_NAME),
        )
        # Never below Trivial.
        self.assertEqual(invocation_difficulty(self.sheet, self.being).points, 15)


class InvokeFavorTests(InvocationTestBase):
    def test_invoke_favor_bonus_per_outcome(self) -> None:
        DevotionStandingFactory(character_sheet=self.sheet, being=self.being, favor=12)
        config = self.config
        config.invocations_per_week = 10
        config.save()
        expected = {
            self.crit: 15,
            self.success: 10,
            self.partial: 5,
            self.failure: 0,
            self.botch: 0,
        }
        for outcome, bonus in expected.items():
            result, _ = self._invoke(outcome)
            self.assertEqual(result.bonus, bonus, outcome.name)
            if bonus:
                self.assertEqual(result.contribution.value, bonus)
                self.assertEqual(result.contribution.source_kind, ModifierSourceKind.FAVOR)
                self.assertEqual(
                    result.contribution.source_label,
                    f"Ombrin's favor (invocation: {outcome.name})",
                )
            else:
                self.assertIsNone(result.contribution)

    def test_invocation_rolls_the_configured_check_at_the_difficulty(self) -> None:
        _make_chosen(self.sheet, self.being, favor=44)
        result, capture = self._invoke(self.success)
        self.assertEqual(capture.check_type, self.check_type)
        self.assertEqual(capture.target_difficulty, 30)
        self.assertEqual(result.difficulty.points, 30)

    def test_invoke_favor_check_type_override(self) -> None:
        DevotionStandingFactory(character_sheet=self.sheet, being=self.being, favor=5)
        override = CheckTypeFactory(name="River Calling")
        self.being.invocation_check_type = override
        self.being.save()
        try:
            _, capture = self._invoke(self.success)
        finally:
            self.being.invocation_check_type = None
            self.being.save()
        self.assertEqual(capture.check_type, override)

    def test_favor_is_unchanged_and_a_row_is_written(self) -> None:
        DevotionStandingFactory(character_sheet=self.sheet, being=self.being, favor=12)
        result, _ = self._invoke(self.success, player_line="  A hush falls.  ")

        standing = DevotionStanding.objects.get(character_sheet=self.sheet, being=self.being)
        self.assertEqual(standing.favor, 12)
        row = FavorInvocation.objects.get(character_sheet=self.sheet)
        self.assertEqual(row, result.invocation)
        self.assertEqual((row.outcome_tier, row.bonus), (self.success, 10))
        self.assertEqual(row.player_line, "A hush falls.")

    def test_invoke_favor_weekly_limit_counts_failures(self) -> None:
        DevotionStandingFactory(character_sheet=self.sheet, being=self.being, favor=12)
        for outcome in (self.failure, self.botch, self.success):
            self._invoke(outcome)
        with self.assertRaises(FavorInvocationRefused) as refused:
            self._invoke(self.success)
        self.assertEqual(
            refused.exception.user_message,
            "You have called on Ombrin 3 times this week already.",
        )
        self.assertEqual(FavorInvocation.objects.filter(character_sheet=self.sheet).count(), 3)

    def test_refused_without_favor_above_zero(self) -> None:
        DevotionStandingFactory(character_sheet=self.sheet, being=self.being, favor=0)
        with self.assertRaises(FavorInvocationRefused) as refused:
            self._invoke(self.success)
        self.assertEqual(
            refused.exception.user_message, "You have no favor with Ombrin to call on."
        )
        self.assertFalse(FavorInvocation.objects.exists())

    def test_refused_when_no_check_type_is_configured(self) -> None:
        DevotionStandingFactory(character_sheet=self.sheet, being=self.being, favor=5)
        config = self.config
        config.invocation_check_type = None
        config.save()
        with self.assertRaises(FavorInvocationRefused) as refused:
            self._invoke(self.success)
        self.assertEqual(
            refused.exception.user_message, "Calling on favor is not set up yet; tell staff."
        )

    def test_lines_name_the_being(self) -> None:
        DevotionStandingFactory(character_sheet=self.sheet, being=self.being, favor=5)
        result, _ = self._invoke(self.partial, player_line="[player line]")
        self.assertEqual(result.call_line, "Ysmay Dunhollow calls on Ombrin: [player line]")
        self.assertEqual(result.private_call_line, result.call_line)
        self.assertEqual(result.outcome_line, "Ysmay Dunhollow's invocation: Partial Success.")

        result, _ = self._invoke(self.partial)
        self.assertEqual(result.call_line, "Ysmay Dunhollow calls on Ombrin.")

    def test_secret_faith_room_line_omits_player_line(self) -> None:
        public = WorshippedBeingFactory(name="The Public One")
        WorshipDeclarationFactory(
            character_sheet=self.sheet, public_being=public, secret_being=self.being
        )
        DevotionStandingFactory(character_sheet=self.sheet, being=self.being, favor=8)

        result, _ = self._invoke(self.failure, player_line="[player line]")

        self.assertEqual(result.call_line, "Ysmay Dunhollow calls on something.")
        self.assertNotIn("[player line]", result.call_line)
        self.assertEqual(result.private_call_line, "Ysmay Dunhollow calls on Ombrin: [player line]")
        self.assertEqual(result.outcome_line, "Ysmay Dunhollow's invocation: Failure.")

    def test_invocation_options_lists_refusals(self) -> None:
        _make_chosen(self.sheet, self.being, favor=44)
        cold = WorshippedBeingFactory(name="A River Spirit")
        DevotionStandingFactory(character_sheet=self.sheet, being=cold, favor=0)

        options = invocation_options(self.sheet)

        self.assertEqual([o.being for o in options], [self.being, cold])
        self.assertTrue(options[0].can_invoke)
        self.assertEqual((options[0].uses_left, options[0].uses_per_week), (3, 3))
        self.assertEqual(options[0].difficulty.points, 30)
        self.assertFalse(options[1].can_invoke)
        self.assertIsNone(options[1].difficulty)


class FavorTargetCleanTests(TestCase):
    def test_a_being_only_on_favor_targets_and_one_any_being_target(self) -> None:
        from django.core.exceptions import ValidationError

        from world.mechanics.factories import ModifierCategoryFactory

        being = WorshippedBeingFactory(name="Ombrin")
        ensure_being_modifier_targets(being)
        stat = ModifierCategoryFactory(name="stat")
        with self.assertRaises(ValidationError):
            ModifierTarget(category=stat, name="Odd", target_being=being).full_clean()
        favor = ModifierTarget.objects.get(
            category__name=FAVOR_INVOCATION_CATEGORY_NAME, target_being=being
        ).category
        with self.assertRaises(ValidationError):
            ModifierTarget(category=favor, name="A second any being").full_clean()
        # The existing any-being target still validates against itself.
        _any_target(FAVOR_INVOCATION_CATEGORY_NAME).full_clean()
