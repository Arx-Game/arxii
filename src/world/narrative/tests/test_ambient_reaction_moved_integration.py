"""Full MOVED-event pipeline proof for ambient reactions (#2471).

Mirrors world/magic/tests/test_scar_moved_triggers.py's pattern: install the shared
Trigger on a room by hand (this is what Task 7's grid-import automation will do),
move a character in via at_post_move, assert delivery — proving Character.at_post_move
-> emit_event(MOVED) -> Trigger dispatch -> Flow -> emit_room_ambient_reaction ->
NarrativeMessage works end to end, independent of the content-authoring pipeline.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.narrative.ambient_trigger_content import ensure_ambient_reaction_content
from world.narrative.factories import AmbientEmoteLineFactory
from world.narrative.models import NarrativeMessageDelivery


class AmbientReactionMovedIntegrationTest(TestCase):
    def setUp(self) -> None:
        from flows.models import Trigger

        self.origin_room = ObjectDBFactory(
            db_key="Origin", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.destination_room = ObjectDBFactory(
            db_key="Destination", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.profile = RoomProfileFactory(objectdb=self.destination_room)
        AmbientEmoteLineFactory(
            room_profile=self.profile, arriver_body="The quiet here presses in."
        )

        trigger_def = ensure_ambient_reaction_content()
        trigger, _created = Trigger.objects.get_or_create(
            obj=self.destination_room, trigger_definition=trigger_def
        )
        self.destination_room.trigger_handler.on_trigger_added(trigger)

        self.character = CharacterFactory()
        CharacterSheetFactory(character=self.character)

    def _place_in(self, room) -> None:
        """Set character.location without firing hooks (setup only)."""
        self.character.db_location = room
        self.character.save(update_fields=["db_location"])

    def test_moving_into_room_delivers_ambient_line(self) -> None:
        self._place_in(self.destination_room)
        self.character.at_post_move(source_location=self.origin_room)

        msgs = list(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=self.character.character_sheet
            ).values_list("message__body", flat=True)
        )
        self.assertEqual(msgs, ["The quiet here presses in."])

    def test_moving_into_untriggered_room_is_silent(self) -> None:
        self._place_in(self.origin_room)
        self.character.at_post_move(source_location=self.destination_room)

        msgs = list(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=self.character.character_sheet
            )
        )
        self.assertEqual(msgs, [])
