"""Tests for CharacterState appearance extensions."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
)
from flows.object_states.character_state import CharacterState
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.fatigue.models import FatiguePool
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    TemplateSlotFactory,
)
from world.items.models import EquippedItem
from world.vitals.models import CharacterVitals


class CharacterStateDisplayWornTests(TestCase):
    def setUp(self) -> None:
        self.character = CharacterFactory(db_key="DispWornChar")
        self.context = MagicMock()
        self.state = CharacterState(self.character, context=self.context)

    def _equip(self, region: str, layer: str, name: str, *, covers: bool = False) -> None:
        template = ItemTemplateFactory(name=name)
        TemplateSlotFactory(
            template=template,
            body_region=region,
            equipment_layer=layer,
            covers_lower_layers=covers,
        )
        item_obj = ObjectDBFactory(
            db_key=f"{name}_obj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        item = ItemInstanceFactory(template=template, game_object=item_obj)
        EquippedItem.objects.create(
            character=self.character,
            item_instance=item,
            body_region=region,
            equipment_layer=layer,
        )

    def test_get_display_worn_empty_for_naked_character(self) -> None:
        self.assertEqual(self.state.get_display_worn(), "")

    def test_get_display_worn_returns_formatted_line_for_one_item(self) -> None:
        self._equip(BodyRegion.TORSO, EquipmentLayer.BASE, "Shirt")
        result = self.state.get_display_worn()
        self.assertIn("Shirt", result)
        # Should mention "Wearing" — exact format flexible.
        self.assertIn("Wearing", result)

    def test_get_display_worn_lists_multiple_items(self) -> None:
        self._equip(BodyRegion.TORSO, EquipmentLayer.BASE, "Shirt")
        self._equip(BodyRegion.WAIST, EquipmentLayer.BASE, "Belt")
        result = self.state.get_display_worn()
        self.assertIn("Shirt", result)
        self.assertIn("Belt", result)

    def test_get_display_worn_hides_concealed_items_for_other_observer(self) -> None:
        # Coat covers shirt
        self._equip(BodyRegion.TORSO, EquipmentLayer.BASE, "Shirt")
        self._equip(BodyRegion.TORSO, EquipmentLayer.OVER, "Coat", covers=True)

        observer_char = CharacterFactory(db_key="ObsChar")
        observer_account = AccountFactory(username="obs_account")
        observer_account.is_staff = False
        observer_account.save()
        observer_char.db_account = observer_account
        observer_char.save()
        observer_state = CharacterState(observer_char, context=self.context)

        result = self.state.get_display_worn(looker=observer_state)
        self.assertIn("Coat", result)
        self.assertNotIn("Shirt", result)

    def test_get_display_worn_shows_concealed_for_self_looker(self) -> None:
        self._equip(BodyRegion.TORSO, EquipmentLayer.BASE, "Shirt")
        self._equip(BodyRegion.TORSO, EquipmentLayer.OVER, "Coat", covers=True)
        # Self-look: pass own state
        result = self.state.get_display_worn(looker=self.state)
        self.assertIn("Shirt", result)
        self.assertIn("Coat", result)

    def test_get_display_status_empty_without_sheet(self) -> None:
        # CharacterFactory has no CharacterSheet → no vitals/fatigue/conditions.
        self.assertEqual(self.state.get_display_status(), "")


class CharacterStateDisplayStatusTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.context = MagicMock()
        self.state = CharacterState(self.character, context=self.context)

    def test_empty_when_healthy_unfatigued_no_conditions(self) -> None:
        CharacterVitals.objects.create(character_sheet=self.sheet, health=100, max_health=100)
        self.assertEqual(self.state.get_display_status(), "")

    def test_includes_wound_descriptor_when_hurt(self) -> None:
        CharacterVitals.objects.create(character_sheet=self.sheet, health=40, max_health=100)
        result = self.state.get_display_status()
        self.assertIn("Status", result)
        self.assertIn("badly wounded", result)

    def test_includes_fatigue_zone_when_fatigued(self) -> None:
        CharacterVitals.objects.create(character_sheet=self.sheet, health=100, max_health=100)
        # capacity is 0 for a statless test sheet, so any current > 0 → EXHAUSTED.
        FatiguePool.objects.create(character_sheet=self.sheet, physical_current=1)
        result = self.state.get_display_status()
        self.assertIn("exhausted", result.lower())

    def test_includes_visible_condition_observer_text(self) -> None:
        CharacterVitals.objects.create(character_sheet=self.sheet, health=100, max_health=100)
        template = ConditionTemplateFactory(
            name="VisibleBleed",
            is_visible_to_others=True,
            observer_description="bleeding heavily",
        )
        ConditionInstanceFactory(target=self.character, condition=template)
        result = self.state.get_display_status()
        self.assertIn("bleeding heavily", result)

    def test_visible_conditions_ordered_by_display_priority(self) -> None:
        CharacterVitals.objects.create(character_sheet=self.sheet, health=100, max_health=100)
        low = ConditionTemplateFactory(
            name="LowPrio",
            is_visible_to_others=True,
            observer_description="faintly trembling",
            display_priority=1,
        )
        high = ConditionTemplateFactory(
            name="HighPrio",
            is_visible_to_others=True,
            observer_description="wreathed in flame",
            display_priority=99,
        )
        ConditionInstanceFactory(target=self.character, condition=low)
        ConditionInstanceFactory(target=self.character, condition=high)
        result = self.state.get_display_status()
        self.assertLess(result.index("wreathed in flame"), result.index("faintly trembling"))

    def test_hidden_condition_excluded(self) -> None:
        CharacterVitals.objects.create(character_sheet=self.sheet, health=100, max_health=100)
        template = ConditionTemplateFactory(
            name="HiddenPain",
            is_visible_to_others=False,
            observer_description="secret agony",
        )
        ConditionInstanceFactory(target=self.character, condition=template)
        self.assertEqual(self.state.get_display_status(), "")

    def test_empty_when_no_vitals_row(self) -> None:
        # Sheet exists but no CharacterVitals/fatigue/conditions → nothing to say.
        self.assertEqual(self.state.get_display_status(), "")


class CharacterStateReturnAppearanceTests(TestCase):
    def setUp(self) -> None:
        self.character = CharacterFactory(db_key="AppearanceChar")
        self.character.db.desc = "A tall figure with measured eyes."
        self.context = MagicMock()
        # Make get_state_by_pk return None so name display defaults to self.name.
        self.context.get_state_by_pk = MagicMock(return_value=None)
        self.state = CharacterState(self.character, context=self.context)

    def test_return_appearance_omits_worn_when_naked(self) -> None:
        result = self.state.return_appearance()
        self.assertNotIn("Wearing", result)

    def test_return_appearance_includes_worn_when_equipped(self) -> None:
        template = ItemTemplateFactory(name="Cloak")
        TemplateSlotFactory(
            template=template,
            body_region=BodyRegion.SHOULDERS,
            equipment_layer=EquipmentLayer.OVER,
        )
        item_obj = ObjectDBFactory(
            db_key="cloak_obj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        item = ItemInstanceFactory(template=template, game_object=item_obj)
        EquippedItem.objects.create(
            character=self.character,
            item_instance=item,
            body_region=BodyRegion.SHOULDERS,
            equipment_layer=EquipmentLayer.OVER,
        )

        result = self.state.return_appearance()
        self.assertIn("Cloak", result)
        self.assertIn("Wearing", result)
