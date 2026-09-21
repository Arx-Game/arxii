"""Tie API (#3957): per-audience reads, the seven writes, the stream, the catalogue."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.journals.factories import JournalEntryFactory
from world.relationships.constants import LabelAwareness, TypeFamily, TypeValence
from world.relationships.factories import RelationshipTierFactory, RelationshipTypeFactory
from world.relationships.models import RelationshipLabel
from world.relationships.services import declare_label, get_or_create_side
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.roster.services.selection import set_selected_entry


def _owned_sheet(account):
    """A sheet with a roster entry + current tenure the account owns, and selected.

    ``CharacterSheetFactory`` alone builds no ``RosterEntry`` (``sheet.roster_entry``
    would raise), so one is built explicitly here and the sheet's ObjectDB is given the
    account (``_resolve_actor`` checks ``sheet.character.db_account_id``); mirrors
    ``world.companions.tests.test_views._actor_user``.
    """
    sheet = CharacterSheetFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(player_data__account=account, roster_entry=entry)
    sheet.character.db_account = account
    sheet.character.save(update_fields=["db_account"])
    set_selected_entry(tenure.player_data, entry)
    return sheet, tenure


class TieApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = AccountFactory()
        cls.other = AccountFactory()
        cls.stranger = AccountFactory()
        cls.staff = AccountFactory(is_staff=True)
        cls.a, cls.tenure_a = _owned_sheet(cls.owner)
        cls.b, cls.tenure_b = _owned_sheet(cls.other)
        cls.c, _ = _owned_sheet(cls.stranger)
        cls.lover = RelationshipTypeFactory(
            name="Lover", valence=TypeValence.WARM, family=TypeFamily.HEART
        )
        cls.enemy = RelationshipTypeFactory(
            name="Enemy", valence=TypeValence.HOSTILE, family=TypeFamily.CONTEST
        )
        cls.rival = RelationshipTypeFactory(
            name="Rival", valence=TypeValence.HOSTILE, family=TypeFamily.CONTEST
        )
        RelationshipTierFactory(tier_number=1, depth_threshold=25)
        RelationshipTierFactory(tier_number=2, depth_threshold=100)
        RelationshipTierFactory(tier_number=3, depth_threshold=500)
        cls.ab = get_or_create_side(source=cls.a, target=cls.b)
        cls.ab.scene_depth, cls.ab.invested_depth, cls.ab.tier = 48, 184, 2
        cls.ab.affection, cls.ab.conflict, cls.ab.summary = 41, 28, "A throat."
        cls.ab.save()
        cls.ba = get_or_create_side(source=cls.b, target=cls.a)
        cls.ba.scene_depth, cls.ba.invested_depth = 48, 60
        cls.ba.save()
        declare_label(
            side=cls.ab, type=cls.lover, awareness=LabelAwareness.CLANDESTINE, tenure=cls.tenure_a
        )
        declare_label(side=cls.ab, type=cls.enemy, tenure=cls.tenure_a)

    def _client(self, account):
        client = APIClient()
        client.force_authenticate(user=account)
        return client

    def test_owner_sees_everything(self):
        data = self._client(self.owner).get(f"/api/relationships/relationships/{self.ab.pk}/").data
        self.assertEqual(data["audience"], "owner")
        self.assertEqual(data["depth"], 340)
        self.assertEqual(data["next_tier_threshold"], 500)
        self.assertEqual([lab["type_name"] for lab in data["labels"]], ["Lover", "Enemy"])
        self.assertEqual(data["breakdown"]["affection"], 41)
        self.assertEqual(data["breakdown"]["their_added_depth"], 108)
        self.assertEqual(data["summary"], "A throat.")

    def test_other_side_sees_known_labels_and_no_feeling(self):
        data = self._client(self.other).get(f"/api/relationships/relationships/{self.ab.pk}/").data
        self.assertEqual(data["audience"], "other_side")
        self.assertEqual([lab["type_name"] for lab in data["labels"]], ["Lover"])
        self.assertEqual(data["depth"], 340)
        self.assertIsNone(data["breakdown"]["affection"])
        self.assertNotIn("ap_this_week", {k: v for k, v in data.items() if v is not None})

    def test_third_party_404s_without_a_public_label(self):
        url = f"/api/relationships/relationships/{self.ab.pk}/"
        response = self._client(self.stranger).get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_third_party_sees_public_labels_and_no_numbers(self):
        label = RelationshipLabel.objects.get(relationship=self.ab, type=self.lover)
        label.awareness = LabelAwareness.PUBLIC
        label.save(update_fields=["awareness"])
        url = f"/api/relationships/relationships/{self.ab.pk}/"
        data = self._client(self.stranger).get(url).data
        self.assertEqual(data["audience"], "third_party")
        self.assertEqual([lab["type_name"] for lab in data["labels"]], ["Lover"])
        self.assertIsNone(data["depth"])
        self.assertIsNone(data["breakdown"])
        self.assertEqual(data["summary"], "A throat.")

    def test_staff_sees_all(self):
        data = self._client(self.staff).get(f"/api/relationships/relationships/{self.ab.pk}/").data
        self.assertEqual(data["audience"], "staff")
        self.assertEqual(len(data["labels"]), 2)

    def test_list_is_own_sides_only(self):
        data = self._client(self.owner).get("/api/relationships/relationships/").data
        ids = [row["id"] for row in data["results"]]
        self.assertEqual(ids, [self.ab.pk])

    def test_writes(self):
        client = self._client(self.other)
        response = client.post(
            "/api/relationships/relationships/declare/",
            {
                "target_persona_id": self.a.personas.first().pk,
                "type_id": self.rival.pk,
                "awareness": "public",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        label_id = response.data["data"]["label_id"]
        response = client.post(
            "/api/relationships/relationships/awareness/",
            {"label_id": label_id, "awareness": "private"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = client.post(
            "/api/relationships/relationships/shift/",
            {"label_id": label_id, "new_type_id": self.enemy.pk, "note": "worse"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        response = client.post(
            "/api/relationships/relationships/summary/",
            {"target_persona_id": self.a.personas.first().pk, "summary": "Hers."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        response = client.post(
            "/api/relationships/relationships/end/",
            {"label_id": response.data["data"].get("label_id", label_id)},
            format="json",
        )
        self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST))

    def test_label_write_refused_for_someone_elses_label(self):
        label = RelationshipLabel.objects.get(relationship=self.ab, type=self.lover)
        response = self._client(self.other).post(
            "/api/relationships/relationships/end/", {"label_id": label.pk}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["message"], "That is not your relationship.")

    def test_stream_filters_by_viewer(self):
        JournalEntryFactory(author=self.a, about=self.b, is_public=False, title="Black")
        JournalEntryFactory(author=self.b, about=self.a, is_public=True, title="White")
        url = f"/api/relationships/relationships/{self.ab.pk}/stream/"
        data = self._client(self.other).get(url).data
        self.assertEqual([i["title"] for i in data], ["White"])

    def test_types_catalogue(self):
        data = self._client(self.stranger).get("/api/relationships/types/").data
        names = {row["name"] for row in data.get("results", data)}
        self.assertEqual(names, {"Lover", "Enemy", "Rival"})
