"""Sentry ARX2-7 (prod, 2026-09-02): ``GET /api/missions/journal/`` 500'd with
``'list' object has no attribute 'pk'``.

Under ``MULTISESSION_MODE = 2`` Evennia's ``Account.puppet`` returns the
*list* of all puppets (empty when nothing is puppeted), never ``None``, so the
journal handed a list to ``journal_for``. The web client's notion of "who am
I" is the durable selection (``PlayerData.selected_entry``, #3412), which
needs no live session at all.
"""

from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import RosterTenureFactory
from world.roster.services.selection import set_selected_entry


class JournalActorResolutionTests(APITestCase):
    def setUp(self) -> None:
        self.account = AccountFactory()
        self.client.force_authenticate(user=self.account)

    def test_no_selection_and_no_puppet_is_a_clear_400(self) -> None:
        response = self.client.get("/api/missions/journal/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.content[:300])
        self.assertIn("character", str(response.data).lower())

    def test_selected_character_reads_its_journal_without_a_session(self) -> None:
        sheet = CharacterSheetFactory()
        tenure = RosterTenureFactory(
            roster_entry__character_sheet__character=sheet.character,
            player_data__account=self.account,
        )
        set_selected_entry(tenure.player_data, tenure.roster_entry)
        response = self.client.get("/api/missions/journal/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content[:300])
        self.assertEqual(response.data["results"], [])
