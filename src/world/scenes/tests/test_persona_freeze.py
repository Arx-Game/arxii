"""Recorded scenes freeze the presented persona (#1109, slice 2).

A logged interaction stores the face the actor wore *at that moment* and never re-resolves
to their current active persona. Without this, switching faces later would retroactively
out someone — a scene where Robert acted would silently become a scene where Bob acted.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.factories import InteractionFactory, PersonaFactory
from world.scenes.interaction_serializers import InteractionListSerializer
from world.scenes.services import set_active_persona


class RecordedPersonaFreezeTests(TestCase):
    def test_interaction_persona_is_frozen_after_a_later_face_switch(self) -> None:
        sheet = CharacterSheetFactory()
        acted_as = sheet.primary_persona  # the face worn when the line was posed
        interaction = InteractionFactory(persona=acted_as)

        # The actor later switches to a different face of the same character.
        other_face = PersonaFactory(character_sheet=sheet)
        set_active_persona(sheet, other_face)

        interaction.refresh_from_db()
        # The record never re-resolves to the current active persona.
        assert interaction.persona_id == acted_as.pk
        # And the display reads the frozen face, not the face worn now.
        payload = InteractionListSerializer().get_persona(interaction)
        assert payload["name"] == acted_as.name
        assert payload["name"] != other_face.name
