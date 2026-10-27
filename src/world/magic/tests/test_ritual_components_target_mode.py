"""Target-resonance component mode and ``qualifying_components`` (#4733, slice 4 of #4672).

Three routes make an item count toward a drift-correction offering: its template is tied
to the resonance being converted toward (material), it carries a live facet the performer's
own motif ties to that resonance (facet), or it means enough to the performer (keepsake).
"""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import (
    ItemFacetFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    meaningful_item_for,
)
from world.items.models import ItemInstance
from world.magic.constants import ComponentMode
from world.magic.exceptions import RitualComponentError
from world.magic.factories import (
    FacetFactory,
    MotifResonanceAssociationFactory,
    MotifResonanceFactory,
    ResonanceFactory,
    ResonanceTierFactory,
    RitualComponentRequirementFactory,
    RitualFactory,
)
from world.magic.models import RitualComponentRequirement
from world.magic.services.drift import qualifying_components
from world.magic.services.ritual_components import (
    _partition_requirements,
    resolve_and_consume_ritual_components,
)
from world.magic.types import QualifyingComponent


def _tied_template(resonance):
    """A template tied to ``resonance`` (a tie needs a tier, by constraint)."""
    return ItemTemplateFactory(tied_resonance=resonance, resonance_tier=ResonanceTierFactory())


class QualifyingComponentsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.target = ResonanceFactory()
        cls.other = ResonanceFactory()
        cls.facet = FacetFactory()
        motif_resonance = MotifResonanceFactory(motif__character=cls.sheet, resonance=cls.target)
        MotifResonanceAssociationFactory(motif_resonance=motif_resonance, facet=cls.facet)

    def _material(self, resonance=None, **kwargs) -> ItemInstance:
        template = _tied_template(resonance or self.target)
        return ItemInstanceFactory(template=template, **kwargs)

    def test_material_route_qualifies_only_the_tied_item(self) -> None:
        tied = self._material()
        untied = self._material(self.other)
        result = qualifying_components(self.sheet, self.target, [tied, untied])
        assert result == [QualifyingComponent(item=tied, mode=ComponentMode.MATERIAL)]

    def test_facet_route_needs_a_motif_facet_for_this_target(self) -> None:
        carrier = ItemInstanceFactory()
        ItemFacetFactory(item_instance=carrier, facet=self.facet)
        stranger = ItemInstanceFactory()
        ItemFacetFactory(item_instance=stranger, facet=FacetFactory())
        result = qualifying_components(self.sheet, self.target, [carrier, stranger])
        assert result == [QualifyingComponent(item=carrier, mode=ComponentMode.FACET)]

    def test_facet_tied_to_a_different_resonance_in_the_motif_does_not_qualify(self) -> None:
        elsewhere = FacetFactory()
        other_link = MotifResonanceFactory(motif=self.sheet.motif, resonance=self.other)
        MotifResonanceAssociationFactory(motif_resonance=other_link, facet=elsewhere)
        carrier = ItemInstanceFactory()
        ItemFacetFactory(item_instance=carrier, facet=elsewhere)
        assert qualifying_components(self.sheet, self.target, [carrier]) == []

    def test_another_characters_motif_facet_does_not_qualify(self) -> None:
        stranger_sheet = CharacterSheetFactory()
        carrier = ItemInstanceFactory()
        ItemFacetFactory(item_instance=carrier, facet=self.facet)
        assert qualifying_components(stranger_sheet, self.target, [carrier]) == []

    def test_a_removed_facet_does_not_qualify(self) -> None:
        carrier = ItemInstanceFactory()
        ItemFacetFactory(item_instance=carrier, facet=self.facet, removed_at=timezone.now())
        assert qualifying_components(self.sheet, self.target, [carrier]) == []

    def test_keepsake_route_qualifies_at_the_bar(self) -> None:
        meaningful = meaningful_item_for(self.sheet)  # own work 1 + carried 1 = 2 points
        plain = ItemInstanceFactory()
        result = qualifying_components(
            self.sheet, self.target, [meaningful, plain], min_item_meaning=2
        )
        assert result == [QualifyingComponent(item=meaningful, mode=ComponentMode.KEEPSAKE)]

    def test_keepsake_below_the_bar_does_not_qualify(self) -> None:
        meaningful = meaningful_item_for(self.sheet)
        assert (
            qualifying_components(self.sheet, self.target, [meaningful], min_item_meaning=3) == []
        )

    def test_no_bar_turns_the_keepsake_route_off(self) -> None:
        meaningful = meaningful_item_for(self.sheet)
        assert qualifying_components(self.sheet, self.target, [meaningful]) == []

    def test_an_item_meeting_two_routes_is_reported_once_under_the_first(self) -> None:
        both = meaningful_item_for(self.sheet, template=_tied_template(self.target))
        ItemFacetFactory(item_instance=both, facet=self.facet)
        result = qualifying_components(self.sheet, self.target, [both], min_item_meaning=1)
        assert result == [QualifyingComponent(item=both, mode=ComponentMode.MATERIAL)]

    def test_facet_beats_keepsake(self) -> None:
        both = meaningful_item_for(self.sheet)
        ItemFacetFactory(item_instance=both, facet=self.facet)
        result = qualifying_components(self.sheet, self.target, [both], min_item_meaning=1)
        assert result == [QualifyingComponent(item=both, mode=ComponentMode.FACET)]

    def test_routes_are_ordered_material_facet_keepsake_whatever_the_input_order(self) -> None:
        keepsake = meaningful_item_for(self.sheet)
        faceted = ItemInstanceFactory()
        ItemFacetFactory(item_instance=faceted, facet=self.facet)
        material = self._material()
        result = qualifying_components(
            self.sheet, self.target, [keepsake, faceted, material], min_item_meaning=2
        )
        assert result == [
            QualifyingComponent(item=material, mode=ComponentMode.MATERIAL),
            QualifyingComponent(item=faceted, mode=ComponentMode.FACET),
            QualifyingComponent(item=keepsake, mode=ComponentMode.KEEPSAKE),
        ]

    def test_destroyed_and_empty_items_never_qualify(self) -> None:
        destroyed = self._material(destroyed_at=timezone.now())
        empty = self._material(quantity=0)
        assert qualifying_components(self.sheet, self.target, [destroyed, empty]) == []


class TargetModeConsumptionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.target = ResonanceFactory()
        cls.ritual = RitualFactory()

    def _target_requirement(self, **kwargs) -> RitualComponentRequirement:
        return RitualComponentRequirementFactory(
            ritual=self.ritual, item_template=None, matches_target_resonance=True, **kwargs
        )

    def _material(self) -> ItemInstance:
        return ItemInstanceFactory(template=_tied_template(self.target))

    def test_a_satisfied_requirement_consumes_the_item(self) -> None:
        self._target_requirement()
        item = self._material()
        resolve_and_consume_ritual_components(
            ritual=self.ritual,
            components=[item],
            performer_sheet=self.sheet,
            resonance_context=self.target,
        )
        assert not ItemInstance.objects.filter(pk=item.pk).exists()

    def test_a_stack_is_decremented_by_the_quantity_needed(self) -> None:
        self._target_requirement(quantity=2)
        item = ItemInstanceFactory(template=_tied_template(self.target), quantity=3)
        resolve_and_consume_ritual_components(
            ritual=self.ritual,
            components=[item],
            performer_sheet=self.sheet,
            resonance_context=self.target,
        )
        item.refresh_from_db()
        assert item.quantity == 1

    def test_quantity_two_needs_two_matching_items(self) -> None:
        self._target_requirement(quantity=2)
        first, second = self._material(), self._material()
        resolve_and_consume_ritual_components(
            ritual=self.ritual,
            components=[first, second],
            performer_sheet=self.sheet,
            resonance_context=self.target,
        )
        assert not ItemInstance.objects.filter(pk__in=[first.pk, second.pk]).exists()

    def test_one_item_never_satisfies_two_requirements(self) -> None:
        self._target_requirement()
        self._target_requirement()
        item = self._material()
        with self.assertRaises(RitualComponentError):
            resolve_and_consume_ritual_components(
                ritual=self.ritual,
                components=[item],
                performer_sheet=self.sheet,
                resonance_context=self.target,
            )
        assert ItemInstance.objects.filter(pk=item.pk).exists()

    def test_the_requirement_min_item_meaning_bar_admits_a_keepsake(self) -> None:
        self._target_requirement(min_item_meaning=2)
        keepsake = meaningful_item_for(self.sheet)
        resolve_and_consume_ritual_components(
            ritual=self.ritual,
            components=[keepsake],
            performer_sheet=self.sheet,
            resonance_context=self.target,
        )
        assert not ItemInstance.objects.filter(pk=keepsake.pk).exists()

    def test_a_material_is_spent_before_a_keepsake_listed_ahead_of_it(self) -> None:
        self._target_requirement(min_item_meaning=2)
        keepsake = meaningful_item_for(self.sheet)
        material = ItemInstanceFactory(template=_tied_template(self.target))
        resolve_and_consume_ritual_components(
            ritual=self.ritual,
            components=[keepsake, material],
            performer_sheet=self.sheet,
            resonance_context=self.target,
        )
        assert ItemInstance.objects.filter(pk=keepsake.pk).exists()
        assert not ItemInstance.objects.filter(pk=material.pk).exists()

    def test_unsatisfied_requirement_raises_and_consumes_nothing(self) -> None:
        self._target_requirement()
        reagent_template = ItemTemplateFactory()
        RitualComponentRequirementFactory(ritual=self.ritual, item_template=reagent_template)
        reagent = ItemInstanceFactory(template=reagent_template)
        wrong = ItemInstanceFactory(template=_tied_template(ResonanceFactory()))
        with self.assertRaises(RitualComponentError) as ctx:
            resolve_and_consume_ritual_components(
                ritual=self.ritual,
                components=[reagent, wrong],
                performer_sheet=self.sheet,
                resonance_context=self.target,
            )
        assert self.ritual.name in ctx.exception.user_message
        assert ItemInstance.objects.filter(pk__in=[reagent.pk, wrong.pk]).count() == 2

    def test_no_target_resonance_raises(self) -> None:
        self._target_requirement()
        item = self._material()
        with self.assertRaises(RitualComponentError) as ctx:
            resolve_and_consume_ritual_components(
                ritual=self.ritual, components=[item], performer_sheet=self.sheet
            )
        assert "target resonance" in ctx.exception.user_message
        assert ItemInstance.objects.filter(pk=item.pk).exists()


class PartitionRequirementsTests(TestCase):
    def test_a_requirement_matching_no_known_mode_raises_instead_of_being_dropped(self) -> None:
        ritual = RitualFactory()
        unsaved = RitualComponentRequirement(ritual=ritual)  # no mode set; never saved
        with self.assertRaises(RitualComponentError) as ctx:
            _partition_requirements(ritual, [unsaved])
        assert ritual.name in ctx.exception.user_message
