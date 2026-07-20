"""E2E test: ghost-tutor summoning -> TRAIN availability (#2460).

Exercises the full journey:
1. CG-finalized character with an orphaned tradition (active CharacterTradition).
2. Summon the ghost tutor via the service function.
3. GhostTutelage created.
4. _technique_available_to_learner returns True for a signature technique.
"""

from django.test import TestCase

from world.magic.models import GhostTutelage
from world.npc_services.effects import _technique_available_to_learner


class GhostTutorE2ETest(TestCase):
    """End-to-end: summon -> available -> train."""

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

        # Path so get_technique_options doesn't bail
        cls.path = PathFactory()
        CharacterPathHistoryFactory(character=cls.sheet.character, path=cls.path)

    def test_full_journey(self):
        """Summon -> GhostTutelage created -> signature available."""
        from world.magic.services.ghost_tutor import summon_ghost_tutor

        # 1. Before summoning, signature is unavailable via generalist trainer
        assert not _technique_available_to_learner(self.sheet, self.role, self.technique)

        # 2. Summon the ghost tutor
        result = summon_ghost_tutor(
            character_sheet=self.sheet,
            ritual=None,  # ritual is opaque to the service
            tradition=self.tradition,
        )
        assert result["created"] is True

        # 3. GhostTutelage exists
        assert (
            GhostTutelage.objects.filter(
                character_sheet=self.sheet, tradition=self.tradition
            ).count()
            == 1
        )

        # 4. Signature now available via generalist trainer
        assert _technique_available_to_learner(self.sheet, self.role, self.technique)
