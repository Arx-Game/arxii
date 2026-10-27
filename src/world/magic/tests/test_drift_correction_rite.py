"""The drift correction rite: preview, focus, check, conversion (#4733, slice 4 of #4672)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.utils import timezone

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.items.factories import EquippedItemFactory, ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance
from world.magic.constants import GainSource
from world.magic.exceptions import (
    DriftConversionInvalidError,
    DriftCorrectionNotConfiguredError,
    DriftOfferNotFoundError,
    RitualComponentError,
)
from world.magic.factories import (
    CharacterAuraFactory,
    DriftConversionCapFactory,
    DriftConversionOfferFactory,
    DriftCorrectionRiteFactory,
    ResonanceTierFactory,
    set_aura_split,
)
from world.magic.models import (
    CharacterResonance,
    DriftConversionCap,
    DriftConversionOffer,
    DriftCorrectionOutcomeShare,
    ResonanceGrant,
)
from world.magic.models.fall_redemption import ConversionType
from world.magic.services.drift import get_drift_correction_config
from world.magic.services.drift_correction import (
    focus_bonus,
    max_yield_per_earned_point,
    perform_drift_correction_rite,
    preview_conversion,
)
from world.magic.tests.test_drift_offer import DriftOfferTestBase, _author_pair, _hold
from world.scenes.factories import SceneFactory
from world.scenes.interaction_services import invalidate_active_scene_cache
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

    def perform(self, amount=12, tier="Success", source=None, components=None, offer=None):
        with force_check_outcome(self.outcomes[tier]):
            return perform_drift_correction_rite(
                offer or self.offer,
                source_resonance=source or self.dread,
                target_resonance=self.dawnlight,
                amount=amount,
                components=[self.component] if components is None else components,
            )

    def cap_value(self) -> int | None:
        return (
            DriftConversionCap.objects.filter(pk=self.cap.pk).values_list("cap", flat=True).first()
        )


class PerformRiteTests(DriftRiteTestBase):
    def test_full_share_converts_the_whole_amount_and_clears_the_offer(self) -> None:
        result = self.perform(amount=12)
        self.assertEqual(_balance(self.sheet, self.dread), 18)
        self.assertEqual(_balance(self.sheet, self.dawnlight), 6)
        grant = ResonanceGrant.objects.get(source=GainSource.DRIFT_CORRECTION)
        self.assertEqual((grant.resonance, grant.amount), (self.dawnlight, 6))
        self.assertIsNone(self.cap_value())
        self.assertFalse(DriftConversionOffer.objects.filter(pk=self.offer.pk).exists())
        self.assertTrue(_consumed(self.component_pk))
        self.assertEqual((result.converted_amount, result.granted_amount), (12, 6))
        self.assertEqual(result.attempted_amount, 12)
        self.assertEqual(result.outcome_name, "Success")
        self.assertEqual(result.success_level, 1)
        self.assertEqual(result.conversion_type, ConversionType.REDEMPTION)
        self.assertEqual(
            (result.source_resonance_id, result.target_resonance_id),
            (self.dread.pk, self.dawnlight.pk),
        )

    def test_half_share_converts_half_and_keeps_the_rest_of_the_cap(self) -> None:
        self.set_shares(Success="0.50")
        result = self.perform(amount=12)
        self.assertEqual((result.converted_amount, result.granted_amount), (6, 3))
        self.assertEqual(self.cap_value(), 6)
        self.assertEqual(_balance(self.sheet, self.dread), 24)
        self.assertTrue(DriftConversionOffer.objects.filter(pk=self.offer.pk).exists())

    def test_failure_tier_consumes_the_offering_and_moves_nothing(self) -> None:
        self.set_shares(Failure="0.00")
        result = self.perform(amount=12, tier="Failure")
        self.assertTrue(_consumed(self.component_pk))
        self.assertEqual(_balance(self.sheet, self.dread), 30)
        self.assertEqual(_balance(self.sheet, self.dawnlight), 0)
        self.assertEqual(self.cap_value(), 12)
        self.assertFalse(ResonanceGrant.objects.filter(source=GainSource.DRIFT_CORRECTION).exists())
        self.assertEqual((result.converted_amount, result.granted_amount), (0, 0))
        self.assertEqual(result.success_level, -1)

    def test_one_unit_at_half_rate_still_grants_one(self) -> None:
        result = self.perform(amount=1)
        self.assertEqual((result.converted_amount, result.granted_amount), (1, 1))
        self.assertEqual(self.cap_value(), 11)

    def test_missing_share_row_refuses_and_rolls_back_the_offering(self) -> None:
        DriftCorrectionOutcomeShare.objects.filter(outcome_tier=self.outcomes["Success"]).delete()
        with self.assertRaises(DriftCorrectionNotConfiguredError):
            self.perform()
        self.assertFalse(_consumed(self.component_pk))
        self.assertEqual(self.cap_value(), 12)
        self.assertEqual(_balance(self.sheet, self.dread), 30)


class FallDirectionTests(DriftRiteTestBase):
    def test_celestial_drift_into_an_abyssal_character_grants_more_than_converted(self) -> None:
        room = ObjectDBFactory(db_key="DriftFallRoom", db_typeclass_path="typeclasses.rooms.Room")
        sheet = CharacterSheetFactory()
        sheet.character.location = room
        sheet.character.save()
        scene = SceneFactory(room=room)
        invalidate_active_scene_cache(room)
        set_aura_split(
            CharacterAuraFactory(character=sheet), celestial="10", primal="10", abyssal="80"
        )
        _hold(sheet, self.dread, 0, lifetime=500)
        _hold(sheet, self.dawnlight, 30)
        offer = DriftConversionOfferFactory(character_sheet=sheet, scene=scene)
        DriftConversionCapFactory(offer=offer, target_resonance=self.dread, cap=10)
        with force_check_outcome(self.outcomes["Success"]):
            result = perform_drift_correction_rite(
                offer,
                source_resonance=self.dawnlight,
                target_resonance=self.dread,
                amount=10,
                components=[_tied_item(self.dread)],
            )
        self.assertEqual((result.converted_amount, result.granted_amount), (10, 15))
        self.assertEqual(result.conversion_type, ConversionType.FALL)
        self.assertEqual(_balance(sheet, self.dread), 15)
        self.assertEqual(_balance(sheet, self.dawnlight), 20)


class RefusalTests(DriftRiteTestBase):
    def assert_nothing_moved(self) -> None:
        self.assertFalse(_consumed(self.component_pk))
        self.assertEqual(_balance(self.sheet, self.dread), 30)
        self.assertEqual(_balance(self.sheet, self.dawnlight), 0)
        self.assertFalse(ResonanceGrant.objects.filter(source=GainSource.DRIFT_CORRECTION).exists())

    def test_amount_zero(self) -> None:
        with self.assertRaises(DriftConversionInvalidError):
            self.perform(amount=0)
        self.assert_nothing_moved()

    def test_amount_over_the_cap_remainder(self) -> None:
        with self.assertRaises(DriftConversionInvalidError):
            self.perform(amount=13)
        self.assert_nothing_moved()
        self.assertEqual(self.cap_value(), 12)

    def test_amount_over_the_held_balance(self) -> None:
        self.cap.cap = 40
        self.cap.save(update_fields=["cap"])
        with self.assertRaises(DriftConversionInvalidError):
            self.perform(amount=31)
        self.assert_nothing_moved()

    def test_own_affinity_source_is_not_convertible(self) -> None:
        _hold(self.sheet, self.sunrise, 20)
        with self.assertRaises(DriftConversionInvalidError):
            self.perform(amount=5, source=self.sunrise)
        self.assert_nothing_moved()
        self.assertEqual(_balance(self.sheet, self.sunrise), 20)

    def test_non_qualifying_components(self) -> None:
        with self.assertRaises(RitualComponentError):
            self.perform(components=[ItemInstanceFactory()])
        self.assert_nothing_moved()
        self.assertEqual(self.cap_value(), 12)

    def test_rite_not_configured(self) -> None:
        self.config.rite = None
        self.config.save(update_fields=["rite"])
        with self.assertRaises(DriftCorrectionNotConfiguredError) as ctx:
            self.perform()
        self.assertEqual(
            ctx.exception.user_message, "The rite of correction is not set up yet; tell staff."
        )
        self.assert_nothing_moved()

    def test_check_type_not_configured(self) -> None:
        self.config.check_type = None
        self.config.save(update_fields=["check_type"])
        with self.assertRaises(DriftCorrectionNotConfiguredError):
            self.perform()
        self.assert_nothing_moved()

    def test_offer_lapsed_with_its_finished_scene(self) -> None:
        self.scene.finish_scene()
        with self.assertRaises(DriftOfferNotFoundError):
            self.perform()
        self.assert_nothing_moved()

    def test_offer_row_left_on_a_finished_scene_is_refused(self) -> None:
        self.scene.is_active = False
        self.scene.date_finished = timezone.now()
        self.scene.save(update_fields=["is_active", "date_finished"])
        with self.assertRaises(DriftOfferNotFoundError):
            self.perform()
        self.assert_nothing_moved()

    def test_no_cap_toward_the_target(self) -> None:
        self.cap.delete()
        with self.assertRaises(DriftOfferNotFoundError):
            self.perform()
        self.assert_nothing_moved()

    def test_pair_with_no_authored_conversion(self) -> None:
        _author_pair(self.abyssal, self.celestial, None, "")
        with self.assertRaises(DriftConversionInvalidError):
            self.perform()
        self.assert_nothing_moved()


class FocusTests(DriftRiteTestBase):
    def test_no_modifier_target_and_no_touchstone_is_zero(self) -> None:
        self.assertEqual(focus_bonus(self.sheet, self.dawnlight), 0)

    def test_worn_touchstone_feeds_the_check_as_extra_modifiers(self) -> None:
        EquippedItemFactory(character=self.sheet, item_instance=_tied_item(self.dawnlight))
        self.sheet.character.equipped_items.invalidate()
        bonus = focus_bonus(self.sheet, self.dawnlight)
        self.assertGreater(bonus, 0)
        roll = MagicMock(return_value=MagicMock(outcome=self.outcomes["Success"]))
        with patch(ROLL_PATH, roll):
            result = perform_drift_correction_rite(
                self.offer,
                source_resonance=self.dread,
                target_resonance=self.dawnlight,
                amount=12,
                components=[self.component],
            )
        roll.assert_called_once()
        args, kwargs = roll.call_args
        self.assertEqual(kwargs["extra_modifiers"], bonus)
        self.assertEqual(args[1], self.config.check_type)
        self.assertEqual(result.focus_bonus, bonus)


class PreviewTests(DriftRiteTestBase):
    def test_preview_lists_convertible_drift_at_the_pair_rate(self) -> None:
        preview = preview_conversion(self.offer, self.dawnlight)
        self.assertEqual(preview.target_resonance_id, self.dawnlight.pk)
        self.assertEqual(preview.cap_remaining, 12)
        self.assertEqual(preview.focus_bonus, 0)
        self.assertEqual(len(preview.sources), 1)
        option = preview.sources[0]
        self.assertEqual(
            (option.resonance_id, option.balance, option.max_amount, option.projected_output),
            (self.dread.pk, 30, 12, 6),
        )
        self.assertEqual(option.multiplier, Decimal("0.50"))
        self.assertEqual(option.conversion_type, ConversionType.REDEMPTION)

    def test_preview_toward_a_target_with_no_cap_offers_nothing_to_move(self) -> None:
        preview = preview_conversion(self.offer, self.sunrise)
        self.assertEqual(preview.cap_remaining, 0)
        self.assertTrue(all(option.max_amount == 0 for option in preview.sources))


class MaxYieldTests(DriftRiteTestBase):
    def test_max_yield_below_direct_earning(self) -> None:
        yield_per_point = max_yield_per_earned_point(self.config)
        self.assertEqual(yield_per_point, Decimal("0.75"))
        self.assertLess(yield_per_point, 1)
