"""active_combat_engagement_for (#3573): the serializer's COMBAT-engagement traversal."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.services import active_combat_engagement_for
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement


class ActiveCombatEngagementForTests(TestCase):
    def test_returns_none_without_engagement(self) -> None:
        character = CharacterSheetFactory().character
        self.assertIsNone(active_combat_engagement_for(character))

    def test_returns_combat_engagement_whose_source_is_the_encounter(self) -> None:
        encounter = CombatEncounterFactory()
        participant = CombatParticipantFactory(encounter=encounter)
        character = participant.character_sheet.character
        # Mirror escalation.py's creation shape (services.py:1490-1496 shows the same kwargs).
        from django.contrib.contenttypes.models import ContentType

        CharacterEngagement.objects.create(
            character=participant.character_sheet,
            engagement_type=EngagementType.COMBAT,
            source_content_type=ContentType.objects.get_for_model(encounter),
            source_id=encounter.pk,
        )
        engagement = active_combat_engagement_for(character)
        self.assertIsNotNone(engagement)
        self.assertEqual(engagement.source, encounter)
