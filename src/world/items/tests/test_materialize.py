"""Tests for template default-property application at materialization (#2503).

``apply_template_properties`` copies a template's authored ``ItemTemplateProperty``
rows onto the materialized ``ObjectDB`` as ``ObjectProperty`` rows, and
``materialize_item_game_object`` (the sole ItemInstance -> ObjectDB chokepoint)
calls it automatically.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import (
    ItemInstanceFactory,
    ItemTemplateFactory,
    ItemTemplatePropertyFactory,
)
from world.items.models import ItemInstance
from world.items.services.materialize import (
    apply_template_properties,
    materialize_item_game_object,
    materialize_item_game_object_in_room,
)
from world.items.services.staging import stage_prop
from world.mechanics.factories import PropertyFactory
from world.mechanics.models import ObjectProperty


class ApplyTemplatePropertiesTests(TestCase):
    """Unit tests for ``apply_template_properties`` in isolation."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.template = ItemTemplateFactory()
        cls.flammable = PropertyFactory(name="flammable")
        cls.heavy = PropertyFactory(name="heavy")

    def test_applies_all_declared_default_properties(self) -> None:
        ItemTemplatePropertyFactory(item_template=self.template, property=self.flammable, value=1)
        ItemTemplatePropertyFactory(item_template=self.template, property=self.heavy, value=2)
        instance = ItemInstanceFactory(template=self.template, holder_character_sheet=self.sheet)

        obj = materialize_item_game_object(instance, self.sheet)

        self.assertIsNotNone(obj)
        values = dict(
            ObjectProperty.objects.filter(object=obj).values_list("property__name", "value")
        )
        self.assertEqual(values, {"flammable": 1, "heavy": 2})

    def test_no_declared_properties_writes_nothing(self) -> None:
        instance = ItemInstanceFactory(template=self.template, holder_character_sheet=self.sheet)

        obj = materialize_item_game_object(instance, self.sheet)

        self.assertIsNotNone(obj)
        self.assertFalse(ObjectProperty.objects.filter(object=obj).exists())

    def test_reapplying_does_not_duplicate(self) -> None:
        ItemTemplatePropertyFactory(item_template=self.template, property=self.flammable, value=1)
        instance = ItemInstanceFactory(template=self.template, holder_character_sheet=self.sheet)
        obj = materialize_item_game_object(instance, self.sheet)

        # Re-applying (e.g. a hypothetical re-materialization path) upserts, not dupes.
        apply_template_properties(obj, self.template)
        apply_template_properties(obj, self.template)

        rows = ObjectProperty.objects.filter(object=obj, property=self.flammable)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.get().value, 1)

    def test_reapplying_updates_changed_value(self) -> None:
        link = ItemTemplatePropertyFactory(
            item_template=self.template, property=self.flammable, value=1
        )
        instance = ItemInstanceFactory(template=self.template, holder_character_sheet=self.sheet)
        obj = materialize_item_game_object(instance, self.sheet)

        link.value = 3
        link.save(update_fields=["value"])
        apply_template_properties(obj, self.template)

        row = ObjectProperty.objects.get(object=obj, property=self.flammable)
        self.assertEqual(row.value, 3)


class MaterializeInRoomTests(TestCase):
    """``materialize_item_game_object_in_room`` -- the GM stage-prop chokepoint (#2503)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.room = ObjectDBFactory(db_key="MaterializeRoom")
        cls.template = ItemTemplateFactory()
        cls.flammable = PropertyFactory(name="flammable_in_room")
        ItemTemplatePropertyFactory(item_template=cls.template, property=cls.flammable, value=1)

    def test_creates_holder_less_object_at_room(self) -> None:
        instance = ItemInstanceFactory(template=self.template)

        obj = materialize_item_game_object_in_room(instance, self.room)

        self.assertIsNotNone(obj)
        self.assertEqual(obj.location, self.room)
        instance.refresh_from_db()
        self.assertEqual(instance.game_object, obj)
        self.assertIsNone(instance.holder_character_sheet)

    def test_applies_template_default_properties(self) -> None:
        instance = ItemInstanceFactory(template=self.template)

        obj = materialize_item_game_object_in_room(instance, self.room)

        row = ObjectProperty.objects.get(object=obj, property=self.flammable)
        self.assertEqual(row.value, 1)


class StagePropTests(TestCase):
    """``stage_prop`` -- the GM improv service function itself (#2503)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.room = ObjectDBFactory(db_key="StagePropRoom")
        cls.template = ItemTemplateFactory(name="Stage Prop Torch")
        cls.flammable = PropertyFactory(name="flammable_stage_prop")
        ItemTemplatePropertyFactory(item_template=cls.template, property=cls.flammable, value=1)

    def test_creates_new_instance_and_object_in_room(self) -> None:
        obj = stage_prop(self.template, self.room)

        self.assertEqual(obj.location, self.room)
        instance = ItemInstance.objects.get(game_object=obj)
        self.assertEqual(instance.template, self.template)
        self.assertIsNone(instance.holder_character_sheet)
        self.assertEqual(ObjectProperty.objects.get(object=obj, property=self.flammable).value, 1)
