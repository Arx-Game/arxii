"""Tests for PersonaPayloadSerializer used in the account payload."""

from django.test import TestCase

from web.api.serializers import PersonaPayloadSerializer
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import PersonaType
from world.scenes.models import Persona


class PersonaPayloadSerializerTests(TestCase):
    """Serializer should expose only the fields the frontend needs."""

    def test_serializes_primary_persona(self) -> None:
        sheet = CharacterSheetFactory()
        primary = sheet.primary_persona
        data = PersonaPayloadSerializer(primary).data
        assert data == {
            "id": primary.id,
            "name": primary.name,
            "persona_type": "primary",
            "display_name": primary.name,
        }

    def test_serializes_established_persona(self) -> None:
        sheet = CharacterSheetFactory()
        established = Persona.objects.create(
            character_sheet=sheet,
            name="Hooded Stranger",
            persona_type=PersonaType.ESTABLISHED,
        )
        data = PersonaPayloadSerializer(established).data
        assert data["persona_type"] == "established"
        assert data["name"] == "Hooded Stranger"
        assert data["id"] == established.id
