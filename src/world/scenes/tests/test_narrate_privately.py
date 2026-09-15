"""narrate_privately: one Narrator line to one character, both channels (#3574)."""

from unittest import mock

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import InteractionMode
from world.scenes.interaction_services import narrate_privately
from world.scenes.models import Interaction
from world.scenes.narrator import NARRATOR_PERSONA_NAME


class NarratePrivatelyTests(TestCase):
    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.room = ObjectDBFactory(
            db_key="NarratePrivatelyRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.character.location = self.room
        self.character.save()

    def test_line_reaches_recipient_only_on_both_channels(self) -> None:
        bystander = CharacterFactory(location=self.room)
        with (
            mock.patch.object(self.character, "msg") as recipient_msg,
            mock.patch.object(bystander, "msg") as bystander_msg,
        ):
            narrate_privately(self.character, "Your ward gutters out.")

        bystander_msg.assert_not_called()
        # Telnet companion: exactly one positional-text call on the recipient.
        positional = [c for c in recipient_msg.call_args_list if c.args]
        self.assertEqual(len(positional), 1)
        self.assertEqual(positional[0].args, ("Your ward gutters out.",))
        # WS channel: exactly one interaction-kwarg call on the recipient.
        ws_calls = [c for c in recipient_msg.call_args_list if "interaction" in c.kwargs]
        self.assertEqual(len(ws_calls), 1)

    def test_persists_a_narrator_whisper_scoped_to_the_recipient(self) -> None:
        with mock.patch.object(self.character, "msg"):
            narrate_privately(self.character, "Your ward gutters out.")

        interaction = Interaction.objects.get(content="Your ward gutters out.")
        self.assertEqual(interaction.mode, InteractionMode.WHISPER)
        self.assertEqual(interaction.persona.name, NARRATOR_PERSONA_NAME)
        receiver_personas = list(interaction.receivers.values_list("persona_id", flat=True))
        self.assertEqual(receiver_personas, [self.sheet.primary_persona.pk])

    def test_no_persona_is_a_silent_no_op(self) -> None:
        loner = CharacterFactory()  # no CharacterSheet, so no primary persona
        with mock.patch.object(loner, "msg") as msg:
            narrate_privately(loner, "nothing to say")
        msg.assert_not_called()
        self.assertFalse(Interaction.objects.filter(content="nothing to say").exists())
