"""Tests for ItemCheckModifier and its contribution to collect_check_modifiers."""

from django.test import TestCase

from world.checks.constants import ModifierSourceKind
from world.checks.factories import CheckTypeFactory
from world.checks.services import collect_check_modifiers
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import EquippedItemFactory, ItemInstanceFactory, ItemTemplateFactory


class ItemCheckModifierContributionTests(TestCase):
    """collect_check_modifiers emits EQUIPMENT contributions for equipped items."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.models import ItemCheckModifier

        cls.character = CharacterFactory(db_key="ItemModTestChar")
        cls.sheet = CharacterSheetFactory(character=cls.character)

        cls.check_type = CheckTypeFactory(name="stealth_test_851")
        cls.other_check_type = CheckTypeFactory(name="combat_test_851")

        cls.template = ItemTemplateFactory(name="Padded Boots 851")
        cls.item = ItemInstanceFactory(template=cls.template)

        # Author a +3 modifier on stealth for this template.
        cls.modifier = ItemCheckModifier.objects.create(
            template=cls.template,
            check_type=cls.check_type,
            modifier_value=3,
        )

    def tearDown(self) -> None:
        from world.items.models import EquippedItem

        EquippedItem.objects.filter(character=self.character.sheet_data).delete()
        self.character.equipped_items.invalidate()

    # -- no equipped item → no EQUIPMENT contribution --

    def test_no_equipped_item_no_equipment_contribution(self) -> None:
        breakdown = collect_check_modifiers(self.sheet, self.check_type)
        kinds = [c.source_kind for c in breakdown.contributions]
        self.assertNotIn(ModifierSourceKind.EQUIPMENT, kinds)

    # -- equipped item with a modifier for a DIFFERENT check type → no contribution --

    def test_equipped_item_wrong_check_type_no_contribution(self) -> None:
        EquippedItemFactory(
            character=self.character.sheet_data,
            item_instance=self.item,
            body_region=BodyRegion.FEET,
            equipment_layer=EquipmentLayer.BASE,
        )
        breakdown = collect_check_modifiers(self.sheet, self.other_check_type)
        kinds = [c.source_kind for c in breakdown.contributions]
        self.assertNotIn(ModifierSourceKind.EQUIPMENT, kinds)

    # -- equipped item with matching check_type modifier → contribution with correct value --

    def test_equipped_item_with_modifier_contributes_equipment_kind(self) -> None:
        EquippedItemFactory(
            character=self.character.sheet_data,
            item_instance=self.item,
            body_region=BodyRegion.FEET,
            equipment_layer=EquipmentLayer.BASE,
        )
        breakdown = collect_check_modifiers(self.sheet, self.check_type)
        equipment_contribs = [
            c for c in breakdown.contributions if c.source_kind == ModifierSourceKind.EQUIPMENT
        ]
        self.assertEqual(len(equipment_contribs), 1)
        self.assertEqual(equipment_contribs[0].value, 3)

    def test_equipped_item_contribution_total_includes_equipment_value(self) -> None:
        EquippedItemFactory(
            character=self.character.sheet_data,
            item_instance=self.item,
            body_region=BodyRegion.FEET,
            equipment_layer=EquipmentLayer.BASE,
        )
        breakdown = collect_check_modifiers(self.sheet, self.check_type)
        equipment_contribs = [
            c for c in breakdown.contributions if c.source_kind == ModifierSourceKind.EQUIPMENT
        ]
        # total includes the equipment contribution
        self.assertIn(equipment_contribs[0].value, range(-1000, 1001))
        self.assertEqual(breakdown.total, sum(c.value for c in breakdown.contributions))

    # -- item with no modifier on template → no EQUIPMENT contribution --

    def test_equipped_item_template_without_modifier_no_contribution(self) -> None:
        from world.items.factories import ItemTemplateFactory

        plain_template = ItemTemplateFactory(name="Plain Gloves 851")
        plain_item = ItemInstanceFactory(template=plain_template)
        EquippedItemFactory(
            character=self.character.sheet_data,
            item_instance=plain_item,
            body_region=BodyRegion.HEAD,
            equipment_layer=EquipmentLayer.BASE,
        )
        breakdown = collect_check_modifiers(self.sheet, self.check_type)
        kinds = [c.source_kind for c in breakdown.contributions]
        self.assertNotIn(ModifierSourceKind.EQUIPMENT, kinds)


class RequiresAttunementContributionTests(TestCase):
    """requires_attunement (#3430): the EQUIPMENT contribution of a flagged template
    is gated on the SAME joined ItemInstance being both equipped and attuned to the
    checking character -- the apply-once stacking rule from the ratified spec."""

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.models import ItemCheckModifier

        cls.character = CharacterFactory(db_key="AttuneModTestChar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.other_character = CharacterFactory(db_key="AttuneModOtherChar")
        cls.other_sheet = CharacterSheetFactory(character=cls.other_character)

        cls.check_type = CheckTypeFactory(name="stealth_test_3430")

        cls.flagged_template = ItemTemplateFactory(
            name="Boots of Quiet Steps 3430", requires_attunement=True
        )
        ItemCheckModifier.objects.create(
            template=cls.flagged_template,
            check_type=cls.check_type,
            modifier_value=5,
        )

    def tearDown(self) -> None:
        from world.items.models import EquippedItem

        EquippedItem.objects.filter(
            character__in=[self.character.sheet_data, self.other_character.sheet_data]
        ).delete()
        self.character.equipped_items.invalidate()
        self.other_character.equipped_items.invalidate()

    def test_attuned_equipped_holder_receives_contribution(self) -> None:
        item = ItemInstanceFactory(
            template=self.flagged_template,
            attuned_to_character_sheet=self.character.sheet_data,
        )
        EquippedItemFactory(
            character=self.character.sheet_data,
            item_instance=item,
            body_region=BodyRegion.FEET,
            equipment_layer=EquipmentLayer.BASE,
        )
        breakdown = collect_check_modifiers(self.sheet, self.check_type)
        equipment_contribs = [
            c for c in breakdown.contributions if c.source_kind == ModifierSourceKind.EQUIPMENT
        ]
        self.assertEqual(len(equipment_contribs), 1)
        self.assertEqual(equipment_contribs[0].value, 5)

    def test_unattuned_holder_of_flagged_template_no_contribution(self) -> None:
        item = ItemInstanceFactory(template=self.flagged_template)  # never attuned
        EquippedItemFactory(
            character=self.character.sheet_data,
            item_instance=item,
            body_region=BodyRegion.FEET,
            equipment_layer=EquipmentLayer.BASE,
        )
        breakdown = collect_check_modifiers(self.sheet, self.check_type)
        kinds = [c.source_kind for c in breakdown.contributions]
        self.assertNotIn(ModifierSourceKind.EQUIPMENT, kinds)

    def test_attuned_to_someone_else_no_contribution(self) -> None:
        item = ItemInstanceFactory(
            template=self.flagged_template,
            attuned_to_character_sheet=self.other_character.sheet_data,
        )
        EquippedItemFactory(
            character=self.character.sheet_data,
            item_instance=item,
            body_region=BodyRegion.FEET,
            equipment_layer=EquipmentLayer.BASE,
        )
        breakdown = collect_check_modifiers(self.sheet, self.check_type)
        kinds = [c.source_kind for c in breakdown.contributions]
        self.assertNotIn(ModifierSourceKind.EQUIPMENT, kinds)

    def test_two_equipped_instances_one_attuned_applies_once(self) -> None:
        attuned_item = ItemInstanceFactory(
            template=self.flagged_template,
            attuned_to_character_sheet=self.character.sheet_data,
        )
        unattuned_item = ItemInstanceFactory(template=self.flagged_template)
        EquippedItemFactory(
            character=self.character.sheet_data,
            item_instance=attuned_item,
            body_region=BodyRegion.FEET,
            equipment_layer=EquipmentLayer.BASE,
        )
        EquippedItemFactory(
            character=self.character.sheet_data,
            item_instance=unattuned_item,
            body_region=BodyRegion.HEAD,
            equipment_layer=EquipmentLayer.BASE,
        )
        breakdown = collect_check_modifiers(self.sheet, self.check_type)
        equipment_contribs = [
            c for c in breakdown.contributions if c.source_kind == ModifierSourceKind.EQUIPMENT
        ]
        # Two equipped instances of the SAME template, only one attuned -- the modifier
        # applies once, never doubled, per the ratified stacking rule.
        self.assertEqual(len(equipment_contribs), 1)
        self.assertEqual(equipment_contribs[0].value, 5)

    def test_flag_false_template_unaffected_by_attunement(self) -> None:
        """Regression: an unflagged template contributes regardless of attunement."""
        from world.items.models import ItemCheckModifier

        plain_template = ItemTemplateFactory(name="Ordinary Boots 3430", requires_attunement=False)
        ItemCheckModifier.objects.create(
            template=plain_template,
            check_type=self.check_type,
            modifier_value=2,
        )
        item = ItemInstanceFactory(template=plain_template)  # never attuned
        EquippedItemFactory(
            character=self.character.sheet_data,
            item_instance=item,
            body_region=BodyRegion.FEET,
            equipment_layer=EquipmentLayer.BASE,
        )
        breakdown = collect_check_modifiers(self.sheet, self.check_type)
        equipment_contribs = [
            c for c in breakdown.contributions if c.source_kind == ModifierSourceKind.EQUIPMENT
        ]
        self.assertEqual(len(equipment_contribs), 1)
        self.assertEqual(equipment_contribs[0].value, 2)

    def test_attach_then_clear_attunement_toggles_contribution(self) -> None:
        """Break-the-invariant variant: attaching attunement makes the modifier
        contribute; clearing it makes the contribution stop again."""
        item = ItemInstanceFactory(template=self.flagged_template)
        EquippedItemFactory(
            character=self.character.sheet_data,
            item_instance=item,
            body_region=BodyRegion.FEET,
            equipment_layer=EquipmentLayer.BASE,
        )

        breakdown = collect_check_modifiers(self.sheet, self.check_type)
        kinds = [c.source_kind for c in breakdown.contributions]
        self.assertNotIn(ModifierSourceKind.EQUIPMENT, kinds)

        item.attuned_to_character_sheet = self.character.sheet_data
        item.save(update_fields=["attuned_to_character_sheet"])
        breakdown = collect_check_modifiers(self.sheet, self.check_type)
        equipment_contribs = [
            c for c in breakdown.contributions if c.source_kind == ModifierSourceKind.EQUIPMENT
        ]
        self.assertEqual(len(equipment_contribs), 1)

        item.attuned_to_character_sheet = None
        item.save(update_fields=["attuned_to_character_sheet"])
        breakdown = collect_check_modifiers(self.sheet, self.check_type)
        kinds = [c.source_kind for c in breakdown.contributions]
        self.assertNotIn(ModifierSourceKind.EQUIPMENT, kinds)
