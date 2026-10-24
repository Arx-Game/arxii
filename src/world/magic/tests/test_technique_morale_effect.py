"""Tests for the technique morale payload rows and their cache (#4619)."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.magic.factories import (
    TechniqueDraftFactory,
    TechniqueDraftMoraleEffectFactory,
    TechniqueFactory,
    TechniqueMoraleEffectFactory,
)
from world.magic.models import Technique, TechniqueDraftMoraleEffect, TechniqueMoraleEffect
from world.magic.services.technique_effects import (
    invalidate_technique_payload_caches,
    technique_payload_prefetches,
)


class TechniqueMoraleEffectTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.row = TechniqueMoraleEffectFactory(
            base_morale=20,
            morale_intensity_multiplier=Decimal("0.50"),
            morale_per_extra_sl=5,
            minimum_success_level=1,
        )

    def test_compute_morale_adds_power_and_extra_success_levels(self) -> None:
        assert self.row.compute_morale(effective_power=10, success_level=3) == 35

    def test_compute_morale_at_the_minimum_level_is_base_plus_power(self) -> None:
        assert self.row.compute_morale(effective_power=0, success_level=1) == 20

    def test_a_technique_holds_one_morale_effect(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            TechniqueMoraleEffect.objects.create(technique=self.row.technique, base_morale=3)

    def test_clean_refuses_a_row_that_removes_no_morale(self) -> None:
        row = TechniqueMoraleEffect(technique=TechniqueFactory(), base_morale=0)
        with self.assertRaisesMessage(ValidationError, "This row removes no morale."):
            row.full_clean()

    def test_cached_morale_effect_is_none_without_a_row(self) -> None:
        assert TechniqueFactory().cached_morale_effect is None

    def test_prefetched_technique_reads_its_morale_effect_without_a_query(self) -> None:
        tech = Technique.objects.prefetch_related(*technique_payload_prefetches()).get(
            pk=self.row.technique_id
        )
        with self.assertNumQueries(0):
            assert tech.cached_morale_effect == self.row

    def test_prefetched_technique_without_a_row_reads_none_without_a_query(self) -> None:
        bare = TechniqueFactory()
        tech = Technique.objects.prefetch_related(*technique_payload_prefetches()).get(pk=bare.pk)
        with self.assertNumQueries(0):
            assert tech.cached_morale_effect is None

    def test_invalidate_drops_the_cached_morale_effect(self) -> None:
        tech = TechniqueFactory()
        assert tech.cached_morale_effect is None
        TechniqueMoraleEffectFactory(technique=tech)
        invalidate_technique_payload_caches(tech)
        assert tech.cached_morale_effect is not None

    def test_a_draft_holds_one_morale_effect(self) -> None:
        draft_row = TechniqueDraftMoraleEffectFactory()
        with self.assertRaises(IntegrityError), transaction.atomic():
            TechniqueDraftMoraleEffect.objects.create(draft=draft_row.draft, base_morale=3)

    def test_a_draft_row_may_be_incomplete(self) -> None:
        row = TechniqueDraftMoraleEffect(draft=TechniqueDraftFactory(), base_morale=0)
        row.full_clean()
