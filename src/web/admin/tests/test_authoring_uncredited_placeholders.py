"""The Workbench's placeholder list reaches tables with no credit columns (#4557).

A proclamation stance carries no credit columns, so the credited backlog never saw
it. These tests drive the queue and editor fragments and the stance's own admin
form through the test client: a stance whose text says PLACEHOLDER is listed and
links to its admin form, and rewriting it there is all it takes to drop it off.
"""

from urllib.parse import urlencode

from django.db import connection
from django.forms.models import model_to_dict
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from evennia.accounts.models import AccountDB

from evennia_extensions.models import PlayerData
from web.admin.authoring.backlog import _uncredited_prose_models, uncredited_placeholder_rows
from world.contributors.factories import ContentContributorFactory
from world.societies.models import StanceArchetype
from world.traits.models import Trait, TraitCategory, TraitType


class UncreditedPlaceholderQueueTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.super = AccountDB.objects.create_superuser("rootadmin", "root@example.com", "pw-123456")
        PlayerData.objects.create(
            account=cls.super, contributor=ContentContributorFactory(name="Root Admin")
        )
        cls.trait = Trait.objects.create(
            name="Grit",
            trait_type=TraitType.STAT,
            category=TraitCategory.PHYSICAL,
            description="PLACEHOLDER how hard you are to stop.",
        )
        cls.stance = StanceArchetype.objects.create(
            name="Defense of the Old Ways",
            description="PLACEHOLDER The old forms held us together; they still do.",
        )
        cls.rewritten = StanceArchetype.objects.create(
            name="Mercy Before Law",
            description="No one is beyond redemption who asks for it.",
        )

    def setUp(self) -> None:
        self.client.force_login(self.super)

    def _queue(self, **params: str):
        return self.client.get(reverse("admin_authoring_queue"), params)

    def _stance_admin_url(self, stance: StanceArchetype) -> str:
        return reverse("admin:arxii_stancearchetype_change", args=[stance.pk])

    def test_placeholder_list_shows_the_stance_linked_to_its_admin_form(self):
        response = self._queue(status="placeholder")

        rows = [entry["row"] for entry in response.context["rows"]]
        labels = [(row.model_name, row.identity) for row in rows]
        self.assertIn(("StanceArchetype", "Defense of the Old Ways"), labels)
        self.assertNotIn(("StanceArchetype", "Mercy Before Law"), labels)
        # Credited rows first, so a credited row keeps its place whichever status opened it.
        self.assertLess(labels.index(("Trait", "Grit")), labels.index(labels[-1]))
        self.assertEqual(labels[-1], ("StanceArchetype", "Defense of the Old Ways"))

        entry = response.context["rows"][-1]
        self.assertIsNone(entry["editor_url"])
        self.assertEqual(entry["admin_url"], self._stance_admin_url(self.stance))
        self.assertContains(
            response, f'<a href="{self._stance_admin_url(self.stance)}">Defense of the Old Ways</a>'
        )

    def test_the_model_filter_offers_the_stance_table(self):
        response = self._queue(status="placeholder")

        labels = {option["label"] for option in response.context["models"]}
        self.assertIn("societies.StanceArchetype", labels)

    def test_the_to_write_list_and_the_stats_leave_it_out(self):
        queue = self._queue()  # the default status is "to write"
        stats = self.client.get(reverse("admin_authoring_stats"))

        names = {entry["row"].model_name for entry in queue.context["rows"]}
        self.assertNotIn("StanceArchetype", names)
        self.assertNotIn("societies", {s.domain for s in stats.context["stats"]})

    def test_rewriting_the_stance_on_its_admin_form_drops_it_off_the_list(self):
        change_url = self._stance_admin_url(self.stance)
        data = {
            key: value
            for key, value in model_to_dict(self.stance).items()
            if value is not None and key != "id"
        }
        data["description"] = "The old forms held us together; they still do."
        data["_save"] = "Save"

        response = self.client.post(change_url, data)

        self.assertEqual(response.status_code, 302)
        queue = self._queue(status="placeholder")
        names = {entry["row"].identity for entry in queue.context["rows"]}
        self.assertNotIn("Defense of the Old Ways", names)

    def test_next_from_the_last_credited_row_opens_the_stance_admin_form(self):
        query = urlencode(
            {
                "model": "traits.Trait",
                "pk": self.trait.pk,
                "queue": urlencode({"status": "placeholder", "model": ""}),
            }
        )
        # Only this module's own rows exist, so after Grit comes the first uncredited row.
        response = self.client.get(f"{reverse('admin_authoring_editor')}?{query}")

        nav = response.context["nav"]
        self.assertIsNone(nav.next_url)
        self.assertEqual(nav.next_admin_url, self._stance_admin_url(self.stance))
        self.assertContains(response, "Next: Defense of the Old Ways, in admin")

    def test_one_query_per_table(self):
        models = _uncredited_prose_models()
        with CaptureQueriesContext(connection) as queries:
            rows = uncredited_placeholder_rows()

        self.assertEqual(len(queries), len(models))
        self.assertEqual([row.identity for row in rows], ["Defense of the Old Ways"])
        self.assertFalse(rows[0].credited)
