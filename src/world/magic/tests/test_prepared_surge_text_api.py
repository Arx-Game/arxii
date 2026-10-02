"""REST surface for prepared per-character Audere surge text (#4101 Task 4, fix round 1).

Mirrors ``test_prepared_text_api.py``'s ``PreparedCrossingTextAPITest`` coverage for
``PreparedSurgeTextViewSet`` / ``CharacterSurgeText``. Two things differ because the
model itself differs: there is no patron layer and nothing to "use up" — a surge line
fires on every surge, so there is no consumed-record refusal and no ``unused`` filter
(``PreparedSurgeTextFilter`` only narrows on ``character_sheet``).
"""

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory, GMTableMembershipFactory
from world.magic.factories import CharacterSurgeTextFactory
from world.magic.models import CharacterSurgeText
from world.roster.factories import RosterTenureFactory


class PreparedSurgeTextAPITest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.table_gm = GMProfileFactory()
        table = GMTableFactory(gm=cls.table_gm)
        GMTableMembershipFactory(table=table, persona=cls.sheet.primary_persona)
        cls.stranger_gm = GMProfileFactory()
        cls.staff = AccountFactory(is_staff=True)
        cls.tenure = RosterTenureFactory(roster_entry__character_sheet=cls.sheet)
        cls.player_account = cls.tenure.player_data.account
        cls.list_url = reverse("magic:prepared-surge-text-list")

    def setUp(self):
        self.client = APIClient()

    def _detail_url(self, pk: int) -> str:
        return reverse("magic:prepared-surge-text-detail", args=[pk])

    def test_staff_can_list_create_and_update(self):
        self.client.force_authenticate(self.staff)

        create_resp = self.client.post(
            self.list_url,
            {"character_sheet": self.sheet.pk, "surge_text": "the room crackles"},
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.data)
        pk = create_resp.data["id"]
        self.assertEqual(create_resp.data["prepared_by_role"], "staff")

        patch_resp = self.client.patch(
            self._detail_url(pk), {"surge_text": "the air thickens"}, format="json"
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK, patch_resp.data)
        self.assertEqual(patch_resp.data["surge_text"], "the air thickens")

        list_resp = self.client.get(self.list_url)
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK, list_resp.data)
        result_ids = {row["id"] for row in list_resp.data["results"]}
        self.assertIn(pk, result_ids)

    def test_table_gm_can_create_and_read(self):
        self.client.force_authenticate(self.table_gm.account)

        create_resp = self.client.post(
            self.list_url,
            {"character_sheet": self.sheet.pk, "surge_text": "her own surge line"},
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.data)
        pk = create_resp.data["id"]
        self.assertEqual(create_resp.data["prepared_by_role"], "table_gm")

        read_resp = self.client.get(self._detail_url(pk))
        self.assertEqual(read_resp.status_code, status.HTTP_200_OK, read_resp.data)
        self.assertEqual(read_resp.data["surge_text"], "her own surge line")

    def test_unrelated_gm_cannot_create_and_sees_empty_list(self):
        self.client.force_authenticate(self.stranger_gm.account)

        create_resp = self.client.post(
            self.list_url,
            {"character_sheet": self.sheet.pk, "surge_text": "an uninvited line"},
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_400_BAD_REQUEST, create_resp.data)

        CharacterSurgeTextFactory(character_sheet=self.sheet, surge_text="hers")
        list_resp = self.client.get(self.list_url)
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK, list_resp.data)
        self.assertEqual(list_resp.data["results"], [])

    def test_player_who_owns_the_sheet_sees_empty_list(self):
        CharacterSurgeTextFactory(character_sheet=self.sheet, surge_text="a spoiler")
        self.client.force_authenticate(self.player_account)

        list_resp = self.client.get(self.list_url)
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK, list_resp.data)
        self.assertEqual(list_resp.data["results"], [])

    def test_destroy_succeeds(self):
        """No consumed-record concept for surge text — delete just succeeds."""
        text = CharacterSurgeTextFactory(character_sheet=self.sheet, surge_text="hers")
        self.client.force_authenticate(self.staff)

        resp = self.client.delete(self._detail_url(text.pk))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT, resp.data)
        self.assertFalse(CharacterSurgeText.objects.filter(pk=text.pk).exists())

    def test_list_query_count_does_not_scale_with_row_count(self):
        """N+1 regression guard (fix round 1), mirroring the crossing-text version."""
        self.client.force_authenticate(self.staff)
        self.client.get(self.list_url)  # warm the session row; not part of either count below

        CharacterSurgeTextFactory(character_sheet=CharacterSheetFactory(), surge_text="hers")
        with self.assertNumQueries(4):
            resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(len(resp.data["results"]), 1)

        for _ in range(4):
            CharacterSurgeTextFactory(character_sheet=CharacterSheetFactory(), surge_text="x")
        with self.assertNumQueries(4):
            resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(len(resp.data["results"]), 5)
