"""REST surface for prepared per-character Audere text (#4101 Task 4).

Covers ``PreparedCrossingTextViewSet`` (list/create/patch/destroy) — the
table-GM/staff authoring surface for ``CharacterCrossingText``. Prepared text is
private to its author (staff or the character's table GM): the crossing player
themselves and any unrelated GM must never read it.
"""

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory, GMTableMembershipFactory
from world.magic.factories import (
    AudereMajoraCrossingFactory,
    AudereMajoraThresholdFactory,
    CharacterCrossingTextFactory,
)
from world.magic.models import CharacterCrossingText
from world.roster.factories import RosterTenureFactory


class PreparedCrossingTextAPITest(TestCase):
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
        cls.list_url = reverse("magic:prepared-crossing-text-list")

    def setUp(self):
        self.client = APIClient()

    def _detail_url(self, pk: int) -> str:
        return reverse("magic:prepared-crossing-text-detail", args=[pk])

    def test_table_gm_can_create_patch_and_list(self):
        self.client.force_authenticate(self.table_gm.account)

        create_resp = self.client.post(
            self.list_url,
            {"character_sheet": self.sheet.pk, "vision_text": "her own vision"},
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED, create_resp.data)
        pk = create_resp.data["id"]
        self.assertEqual(create_resp.data["prepared_by_role"], "table_gm")

        patch_resp = self.client.patch(
            self._detail_url(pk), {"vision_text": "revised vision"}, format="json"
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK, patch_resp.data)
        self.assertEqual(patch_resp.data["vision_text"], "revised vision")

        list_resp = self.client.get(self.list_url)
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK, list_resp.data)
        result_ids = {row["id"] for row in list_resp.data["results"]}
        self.assertIn(pk, result_ids)

    def test_unrelated_gm_cannot_create_and_sees_empty_list(self):
        self.client.force_authenticate(self.stranger_gm.account)

        create_resp = self.client.post(
            self.list_url,
            {"character_sheet": self.sheet.pk, "vision_text": "an uninvited vision"},
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_400_BAD_REQUEST, create_resp.data)

        CharacterCrossingTextFactory(character_sheet=self.sheet, vision_text="hers")
        list_resp = self.client.get(self.list_url)
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK, list_resp.data)
        self.assertEqual(list_resp.data["results"], [])

    def test_player_who_owns_the_sheet_sees_empty_list(self):
        CharacterCrossingTextFactory(character_sheet=self.sheet, vision_text="a spoiler")
        self.client.force_authenticate(self.player_account)

        list_resp = self.client.get(self.list_url)
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK, list_resp.data)
        self.assertEqual(list_resp.data["results"], [])

    def test_staff_lists_every_row(self):
        CharacterCrossingTextFactory(character_sheet=self.sheet, vision_text="hers")
        other_sheet = CharacterSheetFactory()
        CharacterCrossingTextFactory(character_sheet=other_sheet, vision_text="theirs")
        self.client.force_authenticate(self.staff)

        list_resp = self.client.get(self.list_url)
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK, list_resp.data)
        self.assertEqual(len(list_resp.data["results"]), 2)

    def test_consumed_row_rejects_patch(self):
        text = CharacterCrossingTextFactory(character_sheet=self.sheet, vision_text="hers")
        threshold = AudereMajoraThresholdFactory()
        crossing = AudereMajoraCrossingFactory(character_sheet=self.sheet, threshold=threshold)
        text.crossing = crossing
        text.save(update_fields=["crossing"])

        self.client.force_authenticate(self.staff)
        resp = self.client.patch(
            self._detail_url(text.pk), {"vision_text": "too late"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)

    def test_response_carries_role_and_no_account_identifier(self):
        text = CharacterCrossingTextFactory(
            character_sheet=self.sheet, vision_text="hers", prepared_by=self.staff
        )
        self.client.force_authenticate(self.staff)

        resp = self.client.get(self._detail_url(text.pk))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data["prepared_by_role"], "staff")
        self.assertNotIn("prepared_by", resp.data)
        self.assertNotIn(self.staff.username, str(resp.data))

    def test_unused_filter_narrows_to_unconsumed_rows(self):
        unused_text = CharacterCrossingTextFactory(character_sheet=self.sheet, vision_text="fresh")
        used_text = CharacterCrossingTextFactory(
            character_sheet=CharacterSheetFactory(), vision_text="spent"
        )
        threshold = AudereMajoraThresholdFactory()
        crossing = AudereMajoraCrossingFactory(
            character_sheet=used_text.character_sheet, threshold=threshold
        )
        used_text.crossing = crossing
        used_text.save(update_fields=["crossing"])
        self.client.force_authenticate(self.staff)

        unused_resp = self.client.get(self.list_url, {"unused": "true"})
        self.assertEqual(unused_resp.status_code, status.HTTP_200_OK, unused_resp.data)
        unused_ids = {row["id"] for row in unused_resp.data["results"]}
        self.assertIn(unused_text.pk, unused_ids)
        self.assertNotIn(used_text.pk, unused_ids)

        used_resp = self.client.get(self.list_url, {"unused": "false"})
        self.assertEqual(used_resp.status_code, status.HTTP_200_OK, used_resp.data)
        used_ids = {row["id"] for row in used_resp.data["results"]}
        self.assertIn(used_text.pk, used_ids)
        self.assertNotIn(unused_text.pk, used_ids)

    def test_destroy_unused_row_succeeds(self):
        text = CharacterCrossingTextFactory(character_sheet=self.sheet, vision_text="hers")
        self.client.force_authenticate(self.staff)

        resp = self.client.delete(self._detail_url(text.pk))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT, resp.data)
        self.assertFalse(CharacterCrossingText.objects.filter(pk=text.pk).exists())

    def test_destroy_used_row_rejected(self):
        text = CharacterCrossingTextFactory(character_sheet=self.sheet, vision_text="hers")
        threshold = AudereMajoraThresholdFactory()
        crossing = AudereMajoraCrossingFactory(character_sheet=self.sheet, threshold=threshold)
        text.crossing = crossing
        text.save(update_fields=["crossing"])
        self.client.force_authenticate(self.staff)

        resp = self.client.delete(self._detail_url(text.pk))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        self.assertTrue(CharacterCrossingText.objects.filter(pk=text.pk).exists())

    def test_list_query_count_does_not_scale_with_row_count(self):
        """N+1 regression guard (fix round 1): character_name must not query per row.

        ``prepared_by`` is left unset on every row so a would-be N+1 on THAT field
        (a separate, out-of-scope FK — see the fix-round-1 report) can't mask a
        regression on ``character_name`` here: a null FK never issues a query.
        The query count is pinned at two different row counts (1 and 5) and must
        come out identical — if it scaled with row count, it wouldn't.
        """
        self.client.force_authenticate(self.staff)
        self.client.get(self.list_url)  # warm the session row; not part of either count below

        # 1 session lookup + 3 for the view itself (pagination count, pagination
        # fetch, batched persona-name lookup) — NOT 1 + 3*N for N rows.
        CharacterCrossingTextFactory(character_sheet=CharacterSheetFactory(), vision_text="hers")
        with self.assertNumQueries(4):
            resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(len(resp.data["results"]), 1)

        for _ in range(4):
            CharacterCrossingTextFactory(character_sheet=CharacterSheetFactory(), vision_text="x")
        with self.assertNumQueries(4):
            resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(len(resp.data["results"]), 5)
