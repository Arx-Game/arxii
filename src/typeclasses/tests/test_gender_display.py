from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from flows.factories import SceneDataManagerFactory


class GenderAndDisplayNameTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="room",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.char = ObjectDBFactory(
            db_key="Alice",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.viewer = ObjectDBFactory(
            db_key="Bob",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )

    def test_default_gender_is_neutral(self):
        context = SceneDataManagerFactory()
        state = context.initialize_state_for_object(self.char)
        assert state.gender == "neutral"
        assert self.char.gender == "neutral"

    def test_get_display_name_uses_state(self):
        assert self.char.get_display_name(self.viewer) == "Alice"
        context = SceneDataManagerFactory()
        self.room.scene_data = context
        for obj in (self.room, self.char, self.viewer):
            context.initialize_state_for_object(obj)
        char_state = context.get_state_by_pk(self.char.pk)
        char_state.fake_name = "Mysterious figure"
        assert self.char.get_display_name(self.viewer) == "Mysterious figure"
