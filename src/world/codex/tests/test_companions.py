"""The companion registry (#4198): an owner registered at ready is asked on retrieve,
never on list, and an entry no owner claims carries ``null``."""

from unittest import mock

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.codex import companions
from world.codex.companions import companion_for, register_companion
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CharacterCodexKnowledgeFactory, CodexEntryFactory
from world.codex.types import Companion, CompanionGroup, CompanionItem, CompanionReader
from world.roster.factories import RosterTenureFactory


class CompanionRegistryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.entry = CodexEntryFactory(name="The Fleshreaper", is_public=True)
        cls.other = CodexEntryFactory(name="Unowned", is_public=True)
        cls.hidden = CodexEntryFactory(name="Being Researched", is_public=False)
        cls.account = AccountFactory(username="researcher")
        cls.roster_entry = RosterTenureFactory(player_data__account=cls.account).roster_entry

    def test_a_provider_answers_on_retrieve_and_is_not_asked_on_list(self):
        asked = []

        def provider(entry, reader):
            asked.append((entry.pk, reader))
            if entry.pk != self.entry.pk:
                return None
            return Companion(
                rail=[CompanionGroup("Domains", [CompanionItem("Carnage, Hunters")])],
                sections=[],
            )

        with mock.patch.object(companions, "_PROVIDERS", []):
            register_companion(provider)
            register_companion(provider)
            self.assertEqual(len(companions._PROVIDERS), 1)
            client = APIClient()
            listing = client.get("/api/codex/entries/")
            self.assertEqual(listing.status_code, status.HTTP_200_OK)
            self.assertEqual(asked, [])
            self.assertNotIn("companion", listing.data[0])

            detail = client.get(f"/api/codex/entries/{self.entry.pk}/")
            self.assertEqual(detail.status_code, status.HTTP_200_OK)
            self.assertEqual(
                detail.data["companion"],
                {
                    "rail": [
                        {
                            "label": "Domains",
                            "items": [
                                {
                                    "text": "Carnage, Hunters",
                                    "entry_id": None,
                                    "anchor": None,
                                    "href": None,
                                }
                            ],
                        }
                    ],
                    "sections": [],
                },
            )
            self.assertEqual(len(asked), 1)
            reader = asked[0][1]
            self.assertIn(self.entry.pk, reader.visible_entry_ids)
            self.assertFalse(reader.is_staff)

            unowned = client.get(f"/api/codex/entries/{self.other.pk}/")
            self.assertIsNone(unowned.data["companion"])

    def test_an_entry_still_being_researched_carries_no_companion(self):
        CharacterCodexKnowledgeFactory(
            roster_entry=self.roster_entry,
            entry=self.hidden,
            status=CodexKnowledgeStatus.UNCOVERED,
        )

        def always(entry, reader):
            return Companion(rail=[CompanionGroup("Domains", [CompanionItem("x")])], sections=[])

        with mock.patch.object(companions, "_PROVIDERS", [always]):
            client = APIClient()
            client.force_authenticate(user=self.account)
            detail = client.get(f"/api/codex/entries/{self.hidden.pk}/")
            self.assertEqual(detail.status_code, status.HTTP_200_OK)
            self.assertIsNone(detail.data["lore_content"])
            self.assertIsNone(detail.data["companion"])

    def test_no_provider_means_null(self):
        with mock.patch.object(companions, "_PROVIDERS", []):
            reader = CompanionReader(visible_entry_ids=frozenset({self.entry.pk}), is_staff=False)
            self.assertIsNone(companion_for(self.entry, reader))
            detail = APIClient().get(f"/api/codex/entries/{self.entry.pk}/")
            self.assertEqual(detail.status_code, status.HTTP_200_OK)
            self.assertIsNone(detail.data["companion"])

    def test_the_reader_may_see_only_what_the_view_resolved(self):
        reader = CompanionReader(visible_entry_ids=frozenset({self.entry.pk}), is_staff=False)
        self.assertTrue(reader.may_see(self.entry.pk))
        self.assertFalse(reader.may_see(self.other.pk))
        self.assertFalse(reader.may_see(None))
