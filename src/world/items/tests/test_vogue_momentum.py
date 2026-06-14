"""Tests for vogue-momentum accrual + decay (#514).

Covers ``bump_vogue_momentum`` (direct + via ``judge_presentation``) and
``vogue_momentum_decay_tick``. The presenter is equipped with items bearing
facets so the accrual path has worn facets to bump.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.events.factories import EventFactory
from world.items.constants import (
    FASHION_PRESENTATION_CHECK_TYPE_NAME,
    FASHION_PRESENTATION_MODIFIER_TARGET_NAME,
    FASHION_VOGUE_DECAY_FLAT,
    FASHION_VOGUE_DECAY_RATE,
    FASHION_VOGUE_MOMENTUM_STEP,
)
from world.items.factories import (
    EquippedItemFactory,
    FacetVogueMomentumFactory,
    ItemFacetFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
)
from world.items.models import FacetVogueMomentum
from world.items.services.fashion_presentation import judge_presentation, present_outfit
from world.items.services.trendsetter import bump_vogue_momentum, vogue_momentum_decay_tick
from world.magic.factories import FacetFactory
from world.mechanics.factories import ModifierTargetFactory
from world.societies.factories import SocietyFactory
from world.traits.factories import CheckOutcomeFactory


class VogueMomentumAccrualTests(TestCase):
    """Cover bump_vogue_momentum (direct) + the judge_presentation integration."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.modifier_target = ModifierTargetFactory(
            name=FASHION_PRESENTATION_MODIFIER_TARGET_NAME,
        )
        cls.check_type = CheckTypeFactory(name=FASHION_PRESENTATION_CHECK_TYPE_NAME)
        cls.outcome_success = CheckOutcomeFactory(name="vogue-success", success_level=3)

        cls.society = SocietyFactory()
        cls.event = EventFactory(host_society=cls.society)
        cls.presenter = CharacterSheetFactory()
        cls.judge = CharacterSheetFactory()

        # Equip the presenter's character with one item bearing two facets.
        cls.quality = QualityTierFactory()
        template = ItemTemplateFactory(facet_capacity=2)
        cls.instance = ItemInstanceFactory(template=template, quality_tier=cls.quality)
        cls.facet_a = FacetFactory(name="VogueFacetA")
        cls.facet_b = FacetFactory(name="VogueFacetB")
        ItemFacetFactory(
            item_instance=cls.instance,
            facet=cls.facet_a,
            attachment_quality_tier=cls.quality,
        )
        ItemFacetFactory(
            item_instance=cls.instance,
            facet=cls.facet_b,
            attachment_quality_tier=cls.quality,
        )
        EquippedItemFactory(
            character=cls.presenter.character,
            item_instance=cls.instance,
        )

    def _present(self):
        with force_check_outcome(self.outcome_success):
            return present_outfit(self.presenter, self.event)

    def test_bump_creates_rows_for_each_worn_facet(self) -> None:
        """bump_vogue_momentum creates a row per worn facet, incremented by STEP."""
        presentation = self._present()
        bump_vogue_momentum(presentation)
        for facet in (self.facet_a, self.facet_b):
            momentum = FacetVogueMomentum.objects.get(society=self.society, facet=facet)
            self.assertEqual(momentum.points, FASHION_VOGUE_MOMENTUM_STEP)

    def test_bump_increments_existing_rows(self) -> None:
        """A second bump increments existing rows rather than re-creating them."""
        presentation = self._present()
        bump_vogue_momentum(presentation)
        bump_vogue_momentum(presentation)
        momentum = FacetVogueMomentum.objects.get(society=self.society, facet=self.facet_a)
        self.assertEqual(momentum.points, 2 * FASHION_VOGUE_MOMENTUM_STEP)
        # Still exactly one row per (society, facet).
        self.assertEqual(
            FacetVogueMomentum.objects.filter(society=self.society, facet=self.facet_a).count(),
            1,
        )

    def test_bump_no_equipped_facets_is_noop(self) -> None:
        """A presenter with no equipped facets creates no momentum rows."""
        bare_presenter = CharacterSheetFactory()
        with force_check_outcome(self.outcome_success):
            presentation = present_outfit(bare_presenter, self.event)
        bump_vogue_momentum(presentation)
        self.assertFalse(FacetVogueMomentum.objects.filter(society=self.society).exists())

    def test_judge_presentation_bumps_worn_facets(self) -> None:
        """Judging a presentation bumps the worn facets' momentum for the society."""
        presentation = self._present()
        judge_presentation(self.judge, presentation)
        for facet in (self.facet_a, self.facet_b):
            momentum = FacetVogueMomentum.objects.get(society=self.society, facet=facet)
            self.assertEqual(momentum.points, FASHION_VOGUE_MOMENTUM_STEP)


class VogueMomentumDecayTests(TestCase):
    """Cover vogue_momentum_decay_tick: flat + rate decay, floored at 0."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.society = SocietyFactory()

    def test_decay_reduces_points_flat_plus_rate(self) -> None:
        """A high-momentum row loses FLAT + int(points * RATE)."""
        momentum = FacetVogueMomentumFactory(society=self.society, points=100)
        vogue_momentum_decay_tick()
        momentum.refresh_from_db()
        expected = 100 - FASHION_VOGUE_DECAY_FLAT - int(100 * FASHION_VOGUE_DECAY_RATE)
        self.assertEqual(momentum.points, expected)

    def test_decay_floors_at_zero(self) -> None:
        """A row at 1 point cannot go below zero."""
        momentum = FacetVogueMomentumFactory(society=self.society, points=1)
        vogue_momentum_decay_tick()
        momentum.refresh_from_db()
        self.assertEqual(momentum.points, 0)

    def test_decay_leaves_zero_rows_at_zero(self) -> None:
        """Rows already at 0 are untouched (and not counted as touched)."""
        zero = FacetVogueMomentumFactory(society=self.society, points=0)
        positive = FacetVogueMomentumFactory(
            society=self.society, facet=FacetFactory(), points=50
        )
        touched = vogue_momentum_decay_tick()
        zero.refresh_from_db()
        positive.refresh_from_db()
        self.assertEqual(zero.points, 0)
        self.assertEqual(touched, 1)
        self.assertLess(positive.points, 50)
