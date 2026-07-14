"""Hot-provenance ledger reads (#1985)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.items.constants import OwnershipEventType
from world.items.factories import ItemInstanceFactory
from world.items.models import OwnershipEvent
from world.items.services.provenance import has_unresolved_stolen_provenance, stolen_victim


class StolenProvenanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.victim = CharacterSheetFactory()
        cls.thief = CharacterSheetFactory()
        cls.fence = CharacterSheetFactory()
        cls.item = ItemInstanceFactory()

    def _event(self, event_type, from_sheet, to_sheet):
        return OwnershipEvent.objects.create(
            item_instance=self.item,
            event_type=event_type,
            from_character_sheet=from_sheet,
            to_character_sheet=to_sheet,
        )

    def test_clean_item_is_not_hot(self):
        self._event(OwnershipEventType.GIVEN, self.victim, self.fence)
        self.assertFalse(has_unresolved_stolen_provenance(self.item))
        self.assertIsNone(stolen_victim(self.item))

    def test_stolen_item_is_hot_with_victim(self):
        self._event(OwnershipEventType.STOLEN, self.victim, self.thief)
        self.assertTrue(has_unresolved_stolen_provenance(self.item))
        self.assertEqual(stolen_victim(self.item), self.victim)

    def test_stolen_then_returned_is_clean(self):
        self._event(OwnershipEventType.STOLEN, self.victim, self.thief)
        self._event(OwnershipEventType.GIVEN, self.thief, self.victim)
        self.assertFalse(has_unresolved_stolen_provenance(self.item))

    def test_fence_chain_stays_hot(self):
        self._event(OwnershipEventType.STOLEN, self.victim, self.thief)
        self._event(OwnershipEventType.GIVEN, self.thief, self.fence)
        self.assertTrue(has_unresolved_stolen_provenance(self.item))
        self.assertEqual(stolen_victim(self.item), self.victim)

    def test_second_theft_tracks_latest_victim(self):
        self._event(OwnershipEventType.STOLEN, self.victim, self.thief)
        self._event(OwnershipEventType.GIVEN, self.thief, self.victim)
        self._event(OwnershipEventType.STOLEN, self.fence, self.thief)
        self.assertTrue(has_unresolved_stolen_provenance(self.item))
        self.assertEqual(stolen_victim(self.item), self.fence)
