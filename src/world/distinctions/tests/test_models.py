"""Tests for SheetUpdateRequest (#2628) and distinction effect rank sizes (#4660)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import ModifierSize
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionEffectFactory,
    DistinctionEffectRankSizeFactory,
    DistinctionFactory,
    SheetUpdateRequestFactory,
)
from world.distinctions.models import MANEUVER_EFFECT_SIZE_REFUSAL, DistinctionEffectRankSize
from world.distinctions.types import (
    DistinctionOrigin,
    SheetUpdateRequestStatus,
    SheetUpdateRequestType,
)
from world.mechanics.constants import MANEUVER_EFFECT_CATEGORY_NAME, ManeuverEffectKey
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.maneuver_effects import ensure_maneuver_effects, get_maneuver_effect


class SheetUpdateRequestModelTests(TestCase):
    def test_add_request_requires_target_distinction(self):
        sheet = CharacterSheetFactory()
        req = SheetUpdateRequestFactory.build(
            character_sheet=sheet,
            request_type=SheetUpdateRequestType.DISTINCTION_ADD,
            target_distinction=None,
            justification="Test",
            xp_cost=10,
            origin=DistinctionOrigin.UNLOCK_PURCHASE,
        )
        with self.assertRaises(ValidationError):
            req.clean()

    def test_remove_request_requires_target_character_distinction(self):
        sheet = CharacterSheetFactory()
        req = SheetUpdateRequestFactory.build(
            character_sheet=sheet,
            request_type=SheetUpdateRequestType.DISTINCTION_REMOVE,
            target_distinction=None,
            target_character_distinction=None,
            justification="Test",
            xp_cost=0,
            origin=DistinctionOrigin.UNLOCK_PURCHASE,
        )
        with self.assertRaises(ValidationError):
            req.clean()

    def test_add_must_not_set_target_character_distinction(self):
        sheet = CharacterSheetFactory()
        cd = CharacterDistinctionFactory(character=sheet)
        req = SheetUpdateRequestFactory.build(
            character_sheet=sheet,
            request_type=SheetUpdateRequestType.DISTINCTION_ADD,
            target_distinction=cd.distinction,
            target_character_distinction=cd,
            justification="Test",
            xp_cost=10,
            origin=DistinctionOrigin.UNLOCK_PURCHASE,
        )
        with self.assertRaises(ValidationError):
            req.clean()

    def test_default_status_is_pending(self):
        req = SheetUpdateRequestFactory()
        assert req.status == SheetUpdateRequestStatus.PENDING

    def test_str_includes_type_and_cost(self):
        sheet = CharacterSheetFactory()
        dist = DistinctionFactory(cost_per_rank=5, max_rank=1)
        req = SheetUpdateRequestFactory(
            character_sheet=sheet,
            request_type=SheetUpdateRequestType.DISTINCTION_ADD,
            target_distinction=dist,
            xp_cost=5,
        )
        assert "Add" in str(req)
        assert "5" in str(req)


class DistinctionEffectRankSizeConstraintTests(TestCase):
    """The database refuses what the admin form refuses, for writes that skip ``clean()``.

    The admin journey covers ``clean()``; a bulk load or a script write reaches only these.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.effect = DistinctionEffectFactory(
            distinction=DistinctionFactory(max_rank=3), modifier_size=ModifierSize.MINOR
        )

    def test_paramount_is_refused(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            DistinctionEffectRankSizeFactory(effect=self.effect, size=ModifierSize.PARAMOUNT)

    def test_rank_one_is_refused(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            DistinctionEffectRankSizeFactory(effect=self.effect, rank=1)

    def test_one_size_per_rank(self) -> None:
        DistinctionEffectRankSizeFactory(effect=self.effect, rank=2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DistinctionEffectRankSizeFactory(effect=self.effect, rank=2)


class DistinctionEffectRankSizeCacheTests(TestCase):
    """A running server's cached effect sees staff add and remove rank sizes (#4660).

    The effect is identity-mapped, so its ``cached_rank_sizes`` outlives a request; the
    check path's prefetch skips an effect that already holds the list.
    """

    def setUp(self) -> None:
        self.effect = DistinctionEffectFactory(
            distinction=DistinctionFactory(max_rank=3), modifier_size=ModifierSize.MINOR
        )
        self.assertEqual(ModifierSize.MINOR, self.effect.size_at_rank(2))

    def test_a_saved_rank_size_reaches_the_cached_effect(self) -> None:
        DistinctionEffectRankSizeFactory(effect=self.effect, rank=2, size=ModifierSize.LARGE)
        self.assertEqual(ModifierSize.LARGE, self.effect.size_at_rank(2))

    def test_a_deleted_rank_size_leaves_the_cached_effect(self) -> None:
        row = DistinctionEffectRankSizeFactory(effect=self.effect, rank=2, size=ModifierSize.LARGE)
        self.assertEqual(ModifierSize.LARGE, self.effect.size_at_rank(2))
        row.delete()
        self.assertEqual(ModifierSize.MINOR, self.effect.size_at_rank(2))

    def test_a_queryset_delete_leaves_the_cached_effect(self) -> None:
        DistinctionEffectRankSizeFactory(effect=self.effect, rank=2, size=ModifierSize.LARGE)
        self.assertEqual(ModifierSize.LARGE, self.effect.size_at_rank(2))
        DistinctionEffectRankSize.objects.filter(effect=self.effect).delete()
        self.assertEqual(ModifierSize.MINOR, self.effect.size_at_rank(2))


class ManeuverEffectTargetFlatOnlyTests(TestCase):
    """A distinction effect on a maneuver effect target is flat, never sized (#4783)."""

    @classmethod
    def setUpTestData(cls) -> None:
        ensure_maneuver_effects()
        category = ModifierCategoryFactory(name=MANEUVER_EFFECT_CATEGORY_NAME)
        cls.target = ModifierTargetFactory(
            category=category,
            name="Charge: damage",
            scope_maneuver_effect=get_maneuver_effect(ManeuverEffectKey.CHARGE_DAMAGE),
        )

    def test_a_sized_effect_on_a_maneuver_effect_target_is_refused(self) -> None:
        effect = DistinctionEffectFactory.build(
            distinction=DistinctionFactory(), target=self.target, modifier_size=ModifierSize.MINOR
        )

        with self.assertRaises(ValidationError) as caught:
            effect.clean()

        self.assertEqual(
            caught.exception.message_dict["modifier_size"], [MANEUVER_EFFECT_SIZE_REFUSAL]
        )

    def test_a_flat_effect_on_a_maneuver_effect_target_is_accepted(self) -> None:
        effect = DistinctionEffectFactory.build(
            distinction=DistinctionFactory(), target=self.target, modifier_size=None
        )

        effect.clean()

    def test_a_sized_effect_on_another_category_is_accepted(self) -> None:
        effect = DistinctionEffectFactory.build(
            distinction=DistinctionFactory(), modifier_size=ModifierSize.MINOR
        )

        effect.clean()

    def test_a_rank_size_row_on_a_maneuver_effect_target_is_refused(self) -> None:
        # The effect row is written past clean() (a script or bulk load), then a rank size
        # is authored against it.
        effect = DistinctionEffectFactory(
            distinction=DistinctionFactory(max_rank=3),
            target=self.target,
            modifier_size=ModifierSize.MINOR,
        )
        row = DistinctionEffectRankSizeFactory.build(
            effect=effect, rank=2, size=ModifierSize.MODERATE
        )

        with self.assertRaises(ValidationError) as caught:
            row.clean()

        self.assertIn(MANEUVER_EFFECT_SIZE_REFUSAL, caught.exception.messages)
