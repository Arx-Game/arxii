"""A consumed item leaves nothing behind on its holder (#4099 ghost-object defect).

``consume_materials`` used to ``delete()`` a used-up ``ItemInstance``. ``game_object``
cascades the other way (deleting the ObjectDB removes the instance, not vice versa), so
the item's game object stayed in the character's inventory as a ghost. Every shared
consumer (crafting, rituals, prices) now goes through ``destroy_consumed_item_instance``:
a bare throwaway is hard-deleted with its game object, an instance with provenance is
soft-deleted and taken out of play.
"""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import OwnershipEventType
from world.items.crafting.constants import CostConsumption
from world.items.crafting.cost import StagedCost, consume_cost
from world.items.factories import ItemTemplateFactory
from world.items.models import ItemInstance, OwnershipEvent
from world.magic.factories import RitualComponentRequirementFactory
from world.magic.services.ritual_components import resolve_and_consume_ritual_components
from world.magic.tests.price_cost_helpers import carry


class CraftingConsumesThrowawayTests(TestCase):
    def test_used_up_material_leaves_no_row_and_no_game_object(self) -> None:
        sheet = CharacterSheetFactory()
        material = carry(sheet.character, ItemTemplateFactory(), quantity=1)
        game_object_pk = material.game_object_id

        consume_cost(
            crafter_character=sheet.character,
            staged=StagedCost(action_points=0, anima=0, material_allocations=[(material, 1)]),
            consumption=CostConsumption.FULL,
        )

        self.assertFalse(ItemInstance.objects.filter(pk=material.pk).exists())
        self.assertFalse(ObjectDB.objects.filter(pk=game_object_pk).exists())
        self.assertEqual(list(sheet.character.carried_items), [])

    def test_partly_used_stack_stays(self) -> None:
        sheet = CharacterSheetFactory()
        material = carry(sheet.character, ItemTemplateFactory(), quantity=3)

        consume_cost(
            crafter_character=sheet.character,
            staged=StagedCost(action_points=0, anima=0, material_allocations=[(material, 1)]),
            consumption=CostConsumption.FULL,
        )

        material.refresh_from_db()
        self.assertEqual(material.quantity, 2)
        self.assertIsNone(material.destroyed_at)


class RitualConsumesProvenancedComponentTests(TestCase):
    def test_component_with_provenance_is_soft_deleted_and_out_of_play(self) -> None:
        sheet = CharacterSheetFactory()
        requirement = RitualComponentRequirementFactory(quantity=1)
        component = carry(sheet.character, requirement.item_template, quantity=1)
        OwnershipEvent.objects.create(
            item_instance=component,
            event_type=OwnershipEventType.TRANSFERRED,
            to_character_sheet=sheet,
        )
        game_object = component.game_object

        resolve_and_consume_ritual_components(
            ritual=requirement.ritual, components=[component], performer_sheet=sheet
        )

        component.refresh_from_db()
        game_object.refresh_from_db()
        self.assertIsNotNone(component.destroyed_at)
        self.assertEqual(component.quantity, 0)
        self.assertIsNone(game_object.location)
        self.assertTrue(
            component.ownership_events.filter(event_type=OwnershipEventType.CONSUMED).exists()
        )
        self.assertEqual(list(sheet.character.carried_items), [])
