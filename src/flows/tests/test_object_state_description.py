"""What ``look`` shows as an object's description (#4329).

``BaseState.description`` used to read ``item_data.desc``, which no data handler
defines, so every plain object and exit described itself as "You see nothing of
note." whatever had been written for it. It now reads ``ObjectDisplayData``, the
store rooms and characters already read and the one staff ``desc`` writes.
"""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from evennia_extensions.models import ObjectDisplayData
from flows.factories import SceneDataManagerFactory
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.services.materialize import materialize_item_game_object_in_room


class ObjectStateDescriptionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.room = ObjectDBFactory(db_key="hall", db_typeclass_path="typeclasses.rooms.Room")
        cls.rock = ObjectDBFactory(db_key="rock", location=cls.room)
        cls.bare = ObjectDBFactory(db_key="pebble", location=cls.room)
        cls.door = ObjectDBFactory(
            db_key="north",
            db_typeclass_path="typeclasses.exits.Exit",
            location=cls.room,
            destination=cls.room,
        )
        ObjectDisplayData.objects.create(
            object=cls.rock, permanent_description="A rock worn smooth by the river."
        )
        ObjectDisplayData.objects.create(
            object=cls.door, permanent_description="A low oak door, iron-banded."
        )

    def _state(self, obj):
        return SceneDataManagerFactory().initialize_state_for_object(obj)

    def test_object_reads_its_permanent_description(self):
        assert self._state(self.rock).description == "A rock worn smooth by the river."

    def test_exit_reads_its_permanent_description(self):
        assert self._state(self.door).description == "A low oak door, iron-banded."

    def test_object_with_nothing_written_falls_back(self):
        assert self._state(self.bare).description == "You see nothing of note."

    def test_look_appearance_carries_the_description(self):
        appearance = self._state(self.rock).return_appearance()
        assert "A rock worn smooth by the river." in appearance


class ItemObjectDescriptionTests(TestCase):
    """An item's game object describes itself from its ItemInstance (#4329).

    ``look cup`` renders the cup's game object through ``BaseState``; the item's
    text lives on the instance (``custom_description``, else the template's), the
    same text ``look cup in bag`` already showed.
    """

    @classmethod
    def setUpTestData(cls):
        cls.room = ObjectDBFactory(db_key="cuproom", db_typeclass_path="typeclasses.rooms.Room")
        template = ItemTemplateFactory(name="Copper cup", description="A dented copper cup.")
        cls.plain = ItemInstanceFactory(template=template)
        cls.plain_object = materialize_item_game_object_in_room(cls.plain, cls.room)
        cls.engraved = ItemInstanceFactory(
            template=template, custom_description="A copper cup engraved with a heron."
        )
        cls.engraved_object = materialize_item_game_object_in_room(cls.engraved, cls.room)

    def _state(self, obj):
        return SceneDataManagerFactory().initialize_state_for_object(obj)

    def test_item_reads_its_template_description(self):
        assert self._state(self.plain_object).description == "A dented copper cup."

    def test_a_custom_description_wins(self):
        assert self._state(self.engraved_object).description == (
            "A copper cup engraved with a heron."
        )
