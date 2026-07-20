"""Tests for ghost-tutor TRAIN availability (#2460)."""

from django.test import TestCase

from world.npc_services.effects import _technique_available_to_learner


class GhostTutorAvailabilityTests(TestCase):
    """Tests for _technique_available_to_learner with GhostTutelage."""

    @classmethod
    def setUpTestData(cls):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.classes.factories import PathFactory
        from world.magic.factories import (
            CharacterTraditionFactory,
            GiftFactory,
            TechniqueFactory,
            TraditionFactory,
            TraditionGiftGrantFactory,
        )
        from world.npc_services.factories import NPCRoleFactory
        from world.progression.factories import CharacterPathHistoryFactory

        cls.sheet = CharacterSheetFactory()
        cls.tradition = TraditionFactory()
        cls.gift = GiftFactory()
        cls.technique = TechniqueFactory(gift=cls.gift)
        CharacterTraditionFactory(
            character=cls.sheet,
            tradition=cls.tradition,
            left_at=None,
        )
        # Author a signature technique for this tradition+gift
        cls.grant = TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.gift)
        cls.grant.signature_techniques.add(cls.technique)

        # Generalist trainer role (teaches_tradition=None)
        cls.role = NPCRoleFactory(teaches_tradition=None)

        # Set a path on the character so get_technique_options doesn't bail
        cls.path = PathFactory()
        CharacterPathHistoryFactory(character=cls.sheet.character, path=cls.path)

    def test_no_tutelage_signature_unavailable(self):
        """Without GhostTutelage, signature is unavailable via generalist trainer."""
        result = _technique_available_to_learner(self.sheet, self.role, self.technique)
        assert result is False

    def test_with_tutelage_signature_available(self):
        """With GhostTutelage, signature is available via generalist trainer."""
        from world.magic.models import GhostTutelage

        GhostTutelage.objects.create(character_sheet=self.sheet, tradition=self.tradition)
        result = _technique_available_to_learner(self.sheet, self.role, self.technique)
        assert result is True
