"""CG gender options: only CG-selectable rows reach the picker (#4022)."""

from django.test import TestCase
from evennia.accounts.models import AccountDB
from rest_framework.test import APIClient

from world.character_creation.factories import CharacterDraftFactory
from world.character_sheets.factories import GenderFactory
from world.character_sheets.models import Gender


class GenderOptionsTests(TestCase):
    """A row staff keep for NPCs or disguises (an "Indeterminable") must never
    be offered in CG, where the choice is explicit: Female, Male, Non-Binary."""

    @classmethod
    def setUpTestData(cls):
        cls.account = AccountDB.objects.create_user(username="gend", password="x")
        cls.female = GenderFactory(key="female", display_name="Female", is_cg_selectable=True)
        cls.hidden = GenderFactory(
            key="indeterminable", display_name="Indeterminable", is_cg_selectable=False
        )
        cls.draft = CharacterDraftFactory(account=cls.account)

    def _client(self) -> APIClient:
        client = APIClient()
        client.force_authenticate(self.account)
        return client

    def test_lists_only_cg_selectable_genders(self):
        res = self._client().get("/api/character-creation/genders/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual([row["key"] for row in res.json()], ["female"])

    def test_draft_rejects_a_gender_that_is_not_cg_selectable(self):
        client = self._client()
        res = client.patch(
            f"/api/character-creation/drafts/{self.draft.id}/",
            {"selected_gender_id": self.hidden.id},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        res = client.patch(
            f"/api/character-creation/drafts/{self.draft.id}/",
            {"selected_gender_id": self.female.id},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.selected_gender, self.female)

    def test_the_unread_default_flag_is_gone(self):
        """Nothing read ``is_default``; null on the sheet is the unknown gender."""
        field_names = {field.name for field in Gender._meta.get_fields()}
        self.assertNotIn("is_default", field_names)
        self.assertIn("is_cg_selectable", field_names)
