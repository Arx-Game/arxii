"""The rite of settling: its offering, roll, focus and share (#4733, #5124)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.items.factories import (
    EquippedItemFactory,
    ItemFacetFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
    meaningful_item_for,
)
from world.items.models import ItemInstance
from world.magic.constants import EffectKind, GainSource, ReflectionChoice, TargetKind
from world.magic.exceptions import (
    DriftCorrectionNotConfiguredError,
    NoWaitingReflectionError,
    RitualComponentError,
)
from world.magic.factories import (
    DriftConversionCapFactory,
    DriftConversionOfferFactory,
    DriftCorrectionRiteFactory,
    FacetFactory,
    ReflectionFactory,
    ResonanceTierFactory,
    SettlingRiteFactory,
    ThreadFactory,
    ThreadPullEffectFactory,
)
from world.magic.models import (
    CharacterResonance,
    DriftConversionCap,
    DriftCorrectionOutcomeShare,
    Reflection,
    ResonanceGrant,
    SettlingRite,
)
from world.magic.services.drift import get_drift_correction_config
from world.magic.services.drift_correction import (
    focus_bonus,
    max_yield_per_earned_point,
    perform_settling_rite,
)
from world.magic.services.resonance import grant_resonance
from world.magic.services.settling_preview import settling_rite_reading
from world.magic.tests.test_drift_offer import DriftOfferTestBase, _hold
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.services import equipment_walk_total
from world.traits.constants import CANONICAL_OUTCOME_LEVELS
from world.traits.services import ensure_canonical_check_outcome

ROLL_PATH = "world.magic.services.drift_correction.perform_check_with_modifiers"


def _tied_item(resonance) -> ItemInstance:
    template = ItemTemplateFactory(tied_resonance=resonance, resonance_tier=ResonanceTierFactory())
    return ItemInstanceFactory(template=template)


def _consumed(pk: int) -> bool:
    """Whether the item row is gone or used up. Takes the pk: a delete clears ``item.pk``."""
    row = ItemInstance.objects.filter(pk=pk).values("destroyed_at", "quantity").first()
    return row is None or row["destroyed_at"] is not None or row["quantity"] <= 0


def _balance(sheet, resonance) -> int:
    return (
        CharacterResonance.objects.filter(character_sheet=sheet, resonance=resonance)
        .values_list("balance", flat=True)
        .first()
        or 0
    )


class DriftRiteTestBase(DriftOfferTestBase):
    """A Celestial character with 30 Abyssal drift, an offer capped at 12 toward Dawnlight."""

    def setUp(self) -> None:
        super().setUp()
        config = get_drift_correction_config()
        config.rite = DriftCorrectionRiteFactory()
        config.check_type = CheckTypeFactory()
        config.check_difficulty = 0
        config.cap_percent = 50
        config.save()
        self.config = config
        self.outcomes = {
            name: ensure_canonical_check_outcome(name) for name in CANONICAL_OUTCOME_LEVELS
        }
        self.set_shares(**dict.fromkeys(CANONICAL_OUTCOME_LEVELS, "1.00"))
        self.offer = DriftConversionOfferFactory(character_sheet=self.sheet, scene=self.scene)
        self.cap = DriftConversionCapFactory(
            offer=self.offer, target_resonance=self.dawnlight, cap=12
        )
        self.component = _tied_item(self.dawnlight)
        self.component_pk = self.component.pk

    def set_shares(self, **shares: str) -> None:
        for name, share in shares.items():
            DriftCorrectionOutcomeShare.objects.update_or_create(
                outcome_tier=ensure_canonical_check_outcome(name),
                defaults={"converted_share": Decimal(share)},
            )

    def reflect_disown_dread(self) -> Reflection:
        """A waiting reflection that disowns the Dread unsettling her."""
        return ReflectionFactory(
            character_sheet=self.sheet, resonance=self.dread, choice=ReflectionChoice.DISOWN
        )

    def perform(self, tier="Success", components=None):
        with force_check_outcome(self.outcomes[tier]):
            return perform_settling_rite(
                self.sheet, components=[self.component] if components is None else components
            )

    def cap_value(self) -> int | None:
        return (
            DriftConversionCap.objects.filter(pk=self.cap.pk).values_list("cap", flat=True).first()
        )


class PerformRiteTests(DriftRiteTestBase):
    def test_a_keepsake_is_a_qualifying_offering_for_the_resonance_she_disowns(self) -> None:
        reflection = self.reflect_disown_dread()
        requirement = self.config.rite.requirements.get(matches_target_resonance=True)
        requirement.min_item_meaning = 2
        requirement.save()
        keepsake = meaningful_item_for(self.sheet)
        keepsake_pk = keepsake.pk
        self.perform(components=[keepsake])
        self.assertTrue(_consumed(keepsake_pk))
        self.assertFalse(_consumed(self.component_pk))
        self.assertIsNotNone(Reflection.objects.get(pk=reflection.pk).rite)

    def test_a_missing_share_row_for_any_tier_refuses_before_rolling_or_consuming(self) -> None:
        reflection = self.reflect_disown_dread()
        DriftCorrectionOutcomeShare.objects.filter(
            outcome_tier=self.outcomes["Critical Failure"]
        ).delete()
        roll = MagicMock()
        with patch(ROLL_PATH, roll), self.assertRaises(DriftCorrectionNotConfiguredError):
            self.perform()
        roll.assert_not_called()
        self.assertFalse(_consumed(self.component_pk))
        self.assertIsNone(Reflection.objects.get(pk=reflection.pk).rite)
        self.assertEqual(_balance(self.sheet, self.dread), 30)

    def test_a_roll_with_no_outcome_spends_nothing_and_leaves_the_reflection_waiting(self) -> None:
        reflection = self.reflect_disown_dread()
        roll = MagicMock(return_value=MagicMock(outcome=None))
        with patch(ROLL_PATH, roll), self.assertRaises(DriftCorrectionNotConfiguredError):
            perform_settling_rite(self.sheet, components=[self.component])
        roll.assert_called_once()
        self.assertFalse(_consumed(self.component_pk))
        self.assertEqual((self.component.pk, self.component.quantity), (self.component_pk, 1))
        self.assertIsNone(Reflection.objects.get(pk=reflection.pk).rite)
        self.assertEqual(_balance(self.sheet, self.dread), 30)
        self.assertEqual(self.cap_value(), 12)

    def test_an_embraced_deed_grant_needs_both_the_rite_and_the_reflection(self) -> None:
        rite = SettlingRiteFactory(character_sheet=self.sheet)
        with self.assertRaises(ValueError):
            grant_resonance(
                self.sheet, self.dawnlight, 4, source=GainSource.EMBRACED_DEED, settling_rite=rite
            )
        self.assertFalse(ResonanceGrant.objects.filter(source=GainSource.EMBRACED_DEED).exists())

    def test_nothing_waiting_is_a_refusal_that_rolls_nothing(self) -> None:
        roll = MagicMock()
        with patch(ROLL_PATH, roll), self.assertRaises(NoWaitingReflectionError):
            self.perform()
        roll.assert_not_called()
        self.assertFalse(_consumed(self.component_pk))

    def test_an_offering_that_pays_for_nothing_the_rite_moves_writes_nothing(self) -> None:
        reflection = self.reflect_disown_dread()
        roll = MagicMock()
        with patch(ROLL_PATH, roll), self.assertRaises(RitualComponentError):
            self.perform(components=[_tied_item(self.sunrise)])
        roll.assert_not_called()
        self.assertIsNone(Reflection.objects.get(pk=reflection.pk).rite)
        self.assertFalse(SettlingRite.objects.exists())

    def test_a_disowned_unsettling_resonance_turns_the_cap_and_spends_it(self) -> None:
        reflection = self.reflect_disown_dread()
        result = self.perform()
        # The cap of 12 at a full share: 12 Dread at 0.5 is 6 Dawnlight.
        self.assertEqual(
            result.lines, ("You disown your Drift Dread: 12 Drift Dread became 6 Drift Dawnlight.",)
        )
        self.assertEqual(_balance(self.sheet, self.dread), 18)
        self.assertEqual(_balance(self.sheet, self.dawnlight), 6)
        self.assertIsNone(self.cap_value())
        self.assertIsNotNone(Reflection.objects.get(pk=reflection.pk).rite)


class FallbackConversionTargetTests(DriftRiteTestBase):
    """An offering tied to no main-affinity resonance sends the disown where she can atone."""

    def setUp(self) -> None:
        super().setUp()
        # Dawnlight holds the larger lifetime but no open cap; Sunrise (also Celestial) is
        # smaller and holds the open cap.
        _hold(self.sheet, self.sunrise, 0, lifetime=5)
        self.cap.delete()
        DriftConversionCapFactory(offer=self.offer, target_resonance=self.sunrise, cap=12)
        self.component = _tied_item(self.dread)

    def test_the_disown_and_the_preview_both_turn_toward_the_resonance_with_the_open_cap(
        self,
    ) -> None:
        self.reflect_disown_dread()

        reading = settling_rite_reading(self.sheet, [self.component])
        self.assertEqual(
            reading.reflections[0].effect_line,
            "Drift Dread turns toward Drift Sunrise, up to 12.",
        )

        result = self.perform()

        self.assertEqual(
            result.lines,
            ("You disown your Drift Dread: 12 Drift Dread became 6 Drift Sunrise.",),
        )
        self.assertEqual(_balance(self.sheet, self.sunrise), 6)
        self.assertEqual(_balance(self.sheet, self.dawnlight), 0)

    def test_with_no_open_cap_the_largest_main_affinity_resonance_is_still_the_fallback(
        self,
    ) -> None:
        DriftConversionCap.objects.all().delete()
        self.reflect_disown_dread()

        reading = settling_rite_reading(self.sheet, [self.component])

        self.assertEqual(
            reading.reflections[0].effect_line,
            "Nothing will turn, because no chance to atone is open.",
        )


class FocusTests(DriftRiteTestBase):
    def test_no_modifier_target_and_no_touchstone_is_zero(self) -> None:
        self.assertEqual(focus_bonus(self.sheet, self.dawnlight), 0)

    def test_worn_touchstone_feeds_the_check_as_extra_modifiers(self) -> None:
        EquippedItemFactory(character=self.sheet, item_instance=_tied_item(self.dawnlight))
        self.sheet.character.equipped_items.invalidate()
        bonus = focus_bonus(self.sheet, self.dawnlight)
        self.assertGreater(bonus, 0)
        self.reflect_disown_dread()
        roll = MagicMock(return_value=MagicMock(outcome=self.outcomes["Success"]))
        with patch(ROLL_PATH, roll):
            result = perform_settling_rite(self.sheet, components=[self.component])
        roll.assert_called_once()
        args, kwargs = roll.call_args
        self.assertEqual(kwargs["extra_modifiers"], bonus)
        self.assertEqual(args[1], self.config.check_type)
        self.assertEqual(result.focus_bonus, bonus)

    def test_equipment_walk_on_the_target_feeds_the_check(self) -> None:
        category = ModifierCategoryFactory(name="resonance")
        target = ModifierTargetFactory(
            name="DriftFocusTarget", category=category, target_resonance=self.dawnlight
        )
        facet = FacetFactory(name="DriftFocusFacet")
        item = ItemInstanceFactory(
            template=ItemTemplateFactory(facet_capacity=1),
            quality_tier=QualityTierFactory(name="DriftFocusQuality", stat_multiplier=2.0),
        )
        ItemFacetFactory(
            item_instance=item,
            facet=facet,
            attachment_quality_tier=QualityTierFactory(
                name="DriftFocusAttach", stat_multiplier=3.0
            ),
        )
        EquippedItemFactory(character=self.sheet, item_instance=item)
        ThreadFactory(
            owner=self.sheet,
            resonance=self.dawnlight,
            target_kind=TargetKind.FACET,
            target_facet=facet,
            target_trait=None,
            level=2,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.FACET,
            resonance=self.dawnlight,
            tier=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=5,
        )
        self.sheet.character.equipped_items.invalidate()
        self.sheet.character.threads.invalidate()
        walk = equipment_walk_total(self.sheet, target)
        self.assertEqual(walk, 60)  # 5 flat x item 2 x attachment 3 x level 2
        self.assertEqual(focus_bonus(self.sheet, self.dawnlight), walk)
        self.reflect_disown_dread()
        roll = MagicMock(return_value=MagicMock(outcome=self.outcomes["Success"]))
        with patch(ROLL_PATH, roll):
            result = perform_settling_rite(self.sheet, components=[self.component])
        self.assertEqual(roll.call_args.kwargs["extra_modifiers"], walk)
        self.assertEqual(result.focus_bonus, walk)


class MaxYieldTests(DriftRiteTestBase):
    def test_max_yield_below_direct_earning(self) -> None:
        yield_per_point = max_yield_per_earned_point(self.config)
        self.assertEqual(yield_per_point, Decimal("0.75"))
        self.assertLess(yield_per_point, 1)
