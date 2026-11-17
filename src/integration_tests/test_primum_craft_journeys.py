"""Journeys for crafting with Primum (#5125).

Mira works a fire gift (the field of ``test_gift_substance_journeys``) and is also a crafter. The
recipe for an Ember Coat takes Fire Primum as an optional ingredient: she brings it by naming it,
and the coat she makes carries fire at a step set by the Primum's quality. The starter Primum
steps are Trace, Some, Rich and Massive; the tuning ties Common quality to Trace and Masterwork
to Rich, and leaves Fine tied to no step. Names are invented.
"""

from __future__ import annotations

from django.urls import reverse
from rest_framework import status

from integration_tests.test_gift_substance_journeys import _FireField
from world.checks.test_helpers import force_check_outcome
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.crafting.constants import CostConsumption, CraftingRecipeKind
from world.items.crafting.models import CraftingRecipe, CraftingRecipeConsequence
from world.items.factories import (
    CraftingMaterialRequirementFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    MaterialCategoryFactory,
    TemplateSlotFactory,
    install_full_lab_station,
    wire_enchanting_crafting,
)
from world.items.models import ItemInstance, ItemSubstance, ItemTemplate, QualityTier
from world.items.services.equip import equip_item
from world.items.services.primum_items import mint_primum_items
from world.magic.factories import FacetFactory, SubstanceFactory
from world.magic.models import PrimumStep
from world.traits.models import CheckOutcome


class _PrimumCraft(_FireField):
    """Mira in the Long Hall, which has a lab station, with the Ember Coat recipe."""

    def setUp(self) -> None:
        super().setUp()
        install_full_lab_station(self.profile)
        self.facet_recipe = wire_enchanting_crafting(base_difficulty_level=0)
        self.common = QualityTier.objects.get(name="Common")
        self.fine = QualityTier.objects.get(name="Fine")
        self.master = QualityTier.objects.get(name="Masterwork")
        for rank, tier in ((1, self.common), (3, self.master)):
            step = PrimumStep.objects.get(rank=rank)
            step.item_quality = tier
            step.save(update_fields=["item_quality"])

        self.coat_template = ItemTemplate.objects.get(name="Craftable Dagger")
        self.coat_template.name = "Ember Coat"
        self.coat_template.save(update_fields=["name"])
        TemplateSlotFactory(
            template=self.coat_template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.OVER,
        )
        self.primum_template = ItemTemplateFactory(
            name="Fire Primum",
            primum_substance=self.substance,
            is_stackable=True,
            max_stack_size=20,
        )
        self.coat_recipe = CraftingRecipe.objects.get(
            kind=CraftingRecipeKind.ITEM_CREATE, output_item_template=self.coat_template
        )
        self.primum_req = CraftingMaterialRequirementFactory(
            recipe=self.coat_recipe,
            item_template=self.primum_template,
            quantity=1,
            is_optional=True,
        )

    # -- seams ----------------------------------------------------------------------

    def give_primum(self, quality: QualityTier | None) -> None:
        """A harvest hands Mira one Fire Primum of ``quality``."""
        mint_primum_items(self.sheet, self.substance, 1, quality)

    def primum_held(self) -> int:
        return sum(
            inst.quantity
            for inst in ItemInstance.objects.in_play().filter(
                template=self.primum_template, holder_character_sheet=self.sheet
            )
        )

    def craft_coat(self, *, optional: list[int], outcome: str = "Enchanting Success"):
        """Mira crafts the coat through the web action; returns the dispatch result."""
        with force_check_outcome(CheckOutcome.objects.get(name=outcome)):
            return self.web(
                self.mira,
                "craft_create_item",
                output_template=self.coat_template,
                optional_requirements=optional,
            )

    def newest_coat(self) -> ItemInstance:
        return ItemInstance.objects.filter(template=self.coat_template).order_by("-pk").first()

    def carried_step(self, item: ItemInstance) -> str | None:
        row = ItemSubstance.objects.filter(item_instance=item).select_related("step").first()
        return row.step.name if row is not None else None

    def inventory_row(self, item: ItemInstance) -> dict:
        """The item's row on Mira's own inventory listing."""
        response = self.api(self.account_of(self.mira)).get(
            reverse("item-instance-list"), {"character": self.mira.pk}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        (row,) = [r for r in response.json()["results"] if r["id"] == item.pk]
        return row


class CraftingWithPrimum(_PrimumCraft):
    def test_primum_ingredient_makes_a_coat_that_carries_fire_and_helps_the_fire_mage_only(
        self,
    ) -> None:
        self.give_primum(self.fine)
        baseline = self.primum_lines(self.cast())
        self.assertEqual(baseline, {"Surroundings: fire": 2})

        result = self.craft_coat(optional=[self.primum_req.pk])

        self.assertTrue(result.detail.success, result.detail.message)
        coat = self.newest_coat()
        self.assertEqual(self.primum_held(), 0)
        # Fine is tied to no step, so the coat carries the lowest one.
        self.assertEqual(self.carried_step(coat), "Trace")
        self.assertEqual(ItemSubstance.objects.get(item_instance=coat).substance, self.substance)
        # Carried in a pack, it gives no power.
        self.assertEqual(self.primum_lines(self.cast()), baseline)

        equip_item(
            character_sheet=self.sheet,
            item_instance=coat,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.OVER,
        )
        worn = self.primum_lines(self.cast())

        self.assertEqual(
            [label for label in worn if label.endswith("(fire)")], ["Ember Coat (fire)"]
        )
        self.assertGreater(sum(worn.values()), sum(baseline.values()))
        # Tomas, who is only standing in the room, reads what the coat carries.
        seen = self.api(self.account_of(self.tomas)).get(
            reverse("visible-item-detail-detail", args=[coat.pk]), {"observer": self.tomas.pk}
        )
        self.assertEqual(seen.status_code, status.HTTP_200_OK, seen.content)
        self.assertEqual(seen.json()["carries"], ["fire"])

        # A wearer whose gift works another substance gets no line and no power from it.
        self.gift.substance = SubstanceFactory(name="stone")
        self.gift.save(update_fields=["substance"])
        stone_lines = self.primum_lines(self.cast())
        self.assertFalse(
            any("Ember Coat" in label or "fire" in label for label in stone_lines), stone_lines
        )

    def test_optional_primum_is_consumed_only_when_the_crafter_names_it(self) -> None:
        # Not holding the optional ingredient never stops the craft.
        self.assertTrue(self.craft_coat(optional=[]).detail.success)
        # Naming an ingredient she does not hold is refused.
        refused = self.craft_coat(optional=[self.primum_req.pk])
        self.assertFalse(refused.detail.success)

        self.give_primum(self.master)
        result = self.craft_coat(optional=[])

        self.assertTrue(result.detail.success, result.detail.message)
        coat = self.newest_coat()
        self.assertEqual(self.primum_held(), 1)
        self.assertFalse(ItemSubstance.objects.filter(item_instance=coat).exists())
        self.assertEqual(self.inventory_row(coat)["carries"], [])

    def test_facet_attach_with_primum_stamps_the_item(self) -> None:
        facet_req = CraftingMaterialRequirementFactory(
            recipe=self.facet_recipe,
            item_template=self.primum_template,
            quantity=1,
            is_optional=True,
        )
        cloak = ItemInstanceFactory(
            template=ItemTemplateFactory(name="Grey Cloak", facet_capacity=3),
            holder_character_sheet=self.sheet,
        )
        self.give_primum(self.common)

        with force_check_outcome(CheckOutcome.objects.get(name="Enchanting Success")):
            result = self.web(
                self.mira,
                "craft_attach_facet",
                item_instance=cloak,
                facet=FacetFactory(name="Cinder"),
                optional_requirements=[facet_req.pk],
            )

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(self.primum_held(), 0)
        self.assertEqual(self.carried_step(cloak), "Trace")
        self.assertEqual(ItemSubstance.objects.get(item_instance=cloak).substance, self.substance)

    def test_best_quality_primum_sets_the_step_and_a_missing_quality_uses_the_lowest_step(
        self,
    ) -> None:
        self.primum_req.quantity = 2
        self.primum_req.save(update_fields=["quantity"])
        self.give_primum(self.common)
        self.give_primum(self.master)

        self.assertTrue(self.craft_coat(optional=[self.primum_req.pk]).detail.success)

        self.assertEqual(self.carried_step(self.newest_coat()), "Rich")

        self.primum_req.quantity = 1
        self.primum_req.save(update_fields=["quantity"])
        self.give_primum(None)  # granted by a mission: no quality at all

        self.assertTrue(self.craft_coat(optional=[self.primum_req.pk]).detail.success)

        self.assertEqual(self.carried_step(self.newest_coat()), "Trace")

    def test_unconsumed_craft_stamps_nothing(self) -> None:
        botch_row = CraftingRecipeConsequence.objects.get(
            recipe=self.coat_recipe, consequence__outcome_tier__name="Enchanting Botch"
        )
        botch_row.cost_consumption = CostConsumption.NONE
        botch_row.save(update_fields=["cost_consumption"])
        self.give_primum(self.master)

        self.craft_coat(optional=[self.primum_req.pk], outcome="Enchanting Botch")

        self.assertEqual(self.primum_held(), 1)
        self.assertFalse(ItemSubstance.objects.exists())

    def test_category_requirement_recipe_can_be_quoted(self) -> None:
        gems = MaterialCategoryFactory(name="Precious Gemstones")
        ruby = ItemTemplateFactory(name="Ruby", material_category=gems)
        gem_req = CraftingMaterialRequirementFactory(
            recipe=self.coat_recipe, item_template=None, material_category=gems, quantity=2
        )
        held = ItemInstanceFactory(template=ruby, quantity=2, holder_character_sheet=self.sheet)

        def quote() -> dict:
            response = self.api(self.account_of(self.mira)).get(
                reverse("item-craft-create-quote"), {"template": self.coat_template.pk}
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
            return response.json()

        covered = quote()

        rows = {row["name"]: row for row in covered["costs"]["materials"]}
        self.assertEqual(
            rows["Precious Gemstones"],
            {
                "requirement_id": gem_req.pk,
                "material_category_id": gems.pk,
                "item_template_id": None,
                "name": "Precious Gemstones",
                "quantity_required": 2,
                "have": 2,
                "is_optional": False,
            },
        )
        self.assertTrue(rows["Fire Primum"]["is_optional"])
        self.assertEqual(rows["Fire Primum"]["have"], 0)
        # The optional Primum she does not hold never makes the recipe unaffordable.
        self.assertTrue(covered["affordable"])

        held.quantity = 0
        held.save(update_fields=["quantity"])

        self.assertFalse(quote()["affordable"])
