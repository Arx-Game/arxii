"""The sheet's Ties cast (#3957): per-viewer cards on ``GET /api/character-sheets/{pk}/``."""

from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.constants import LabelAwareness
from world.relationships.factories import RelationshipTypeFactory
from world.relationships.services import declare_label, get_or_create_side
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.roster.services.selection import set_selected_entry


def _owned_sheet(account):
    """A sheet with a roster entry + current tenure the account owns, and selected."""
    sheet = CharacterSheetFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(player_data__account=account, roster_entry=entry)
    sheet.character.db_account = account
    sheet.character.save(update_fields=["db_account"])
    set_selected_entry(tenure.player_data, entry)
    return sheet


class SheetTiesSectionTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = AccountFactory()
        cls.other = AccountFactory()
        cls.stranger = AccountFactory()
        cls.a = _owned_sheet(cls.owner)
        cls.b = _owned_sheet(cls.other)
        cls.c = CharacterSheetFactory()
        cls.lover = RelationshipTypeFactory(name="Lover")
        cls.rival = RelationshipTypeFactory(name="Rival")
        # Alice -> Bob, Clandestine: visible to Alice (owner) and Bob (other side).
        cls.ab = get_or_create_side(source=cls.a, target=cls.b)
        cls.ab.scene_depth = 30
        cls.ab.save()
        declare_label(side=cls.ab, type=cls.lover, awareness=LabelAwareness.CLANDESTINE)
        # Alice -> Carol, Public: visible to Alice (owner) and any stranger.
        cls.ac = get_or_create_side(source=cls.a, target=cls.c)
        cls.ac.scene_depth = 12
        cls.ac.save()
        declare_label(side=cls.ac, type=cls.rival, awareness=LabelAwareness.PUBLIC)

    def _ties(self, sheet, viewer):
        self.client.force_authenticate(user=viewer)
        return self.client.get(f"/api/character-sheets/{sheet.pk}/").data["ties"]

    def _card(self, cards, relationship_id):
        return next(card for card in cards if card["relationship_id"] == relationship_id)

    def test_owner_sees_both_cards_with_depth(self):
        cards = self._ties(self.a, self.owner)
        ids = {card["relationship_id"] for card in cards}
        self.assertEqual(ids, {self.ab.pk, self.ac.pk})
        for card in cards:
            self.assertIsNotNone(card["depth"])

    def test_other_side_sees_the_clandestine_label_and_a_depth(self):
        cards = self._ties(self.a, self.other)
        card = self._card(cards, self.ab.pk)
        self.assertEqual([lab["awareness"] for lab in card["labels"]], ["clandestine"])
        self.assertIsNotNone(card["depth"])

    def test_stranger_sees_only_the_publicly_labelled_card_with_no_numbers(self):
        cards = self._ties(self.a, self.stranger)
        ids = {card["relationship_id"] for card in cards}
        self.assertEqual(ids, {self.ac.pk})
        card = self._card(cards, self.ac.pk)
        self.assertIsNone(card["depth"])
        self.assertIsNone(card["tier"])
