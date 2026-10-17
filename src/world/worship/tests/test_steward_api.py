"""The table page's Beings section API (#4333 slice 4).

The table GM reads the stewarded being's card, writes pledge types, answers and
sacrifice lines with the same limits as the staff builders, and answers or
dismisses a closed pledge. Text is labelled placeholders.
"""

from __future__ import annotations

from rest_framework.test import APIClient

from world.gm.constants import GMLevel, GMPromptStatus
from world.gm.factories import GMProfileFactory
from world.gm.models import GMPrompt
from world.worship.models import Answer, Pledge, Vision
from world.worship.tests.test_stewards import StewardTestBase

_BASE = "/api/worship/"


class StewardApiTests(StewardTestBase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.client.default_format = "json"
        self.client.force_authenticate(self.gm_account)

    def test_the_table_gm_reads_the_being_card(self) -> None:
        self._full_answer("Success")
        response = self.client.get(f"{_BASE}stewarded-beings/", {"table": self.table.pk})

        self.assertEqual(response.status_code, 200, response.content)
        (card,) = response.json()["results"]
        self.assertEqual(card["name"], "Ombrin")
        self.assertEqual(card["table"], self.table.pk)
        self.assertEqual(card["favored_facets"], [{"id": self.silk.pk, "name": "Silk"}])
        self.assertEqual(card["closing_rites"], [{"id": self.rite.pk, "name": "Ombrin's rite"}])
        (pledge,) = card["pledges"]
        self.assertEqual(pledge["covered_tiers"], [self.outcomes["Success"].pk])
        self.assertEqual(
            {clue["id"] for clue in card["catalogue_clues"]},
            {self.fact_clue.pk, self.follow_up_clue.pk},
        )

    def test_another_gm_sees_no_stewarded_being(self) -> None:
        self.client.force_authenticate(GMProfileFactory(level=GMLevel.SENIOR).account)
        response = self.client.get(f"{_BASE}stewarded-beings/")
        self.assertEqual(response.json()["results"], [])
        response = self.client.post(
            f"{_BASE}steward-pledges/",
            {
                "being": self.being.pk,
                "name": "[GM-authored pledge name]",
                "favor_target": 10,
                "span_weeks": 1,
                "closing_rite": self.rite.pk,
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_the_table_gm_writes_a_pledge_type(self) -> None:
        response = self.client.post(
            f"{_BASE}steward-pledges/",
            {
                "being": self.being.pk,
                "name": "[GM-authored pledge name]",
                "description": "[GM-authored pledge description]",
                "favor_target": 10,
                "span_weeks": 1,
                "closing_rite": self.rite.pk,
            },
        )

        self.assertEqual(response.status_code, 201, response.content)
        pledge = Pledge.objects.get(pk=response.json()["id"])
        self.assertEqual((pledge.favor_target, pledge.span_weeks), (10, 1))

    def test_an_answer_keeps_the_tier_limits_and_the_catalogue(self) -> None:
        self._full_answer("Success")  # puts the clues in the catalogue
        partial = {
            "being": self.being.pk,
            "pledge": self.pledge.pk,
            "outcome_tier": self.outcomes["Partial Success"].pk,
            "delay_text": "[GM-authored delay text]",
            "fact_text": "[GM-authored fact text]",
        }
        response = self.client.post(f"{_BASE}steward-answers/", partial)
        self.assertEqual(response.status_code, 400)
        self.assertIn("fact_text", response.json())

        partial.pop("fact_text")
        partial["follow_up_clue"] = self.follow_up_clue.pk
        response = self.client.post(f"{_BASE}steward-answers/", partial)
        self.assertEqual(response.status_code, 201, response.content)
        answer = Answer.objects.get(pk=response.json()["id"])

        line = self.client.post(
            f"{_BASE}steward-sacrifice-lines/",
            {"answer": answer.pk, "facet": self.silk.pk, "text": "[GM-authored sacrifice line]"},
        )
        self.assertEqual(line.status_code, 201, line.content)

    def test_the_panel_lists_and_sends(self) -> None:
        answer = self._full_answer("Success")
        prompt = self._closed("Success")

        response = self.client.get(f"{_BASE}steward-prompts/", {"table": self.table.pk})
        (row,) = response.json()["results"]
        self.assertEqual(row["being_name"], "Ombrin")
        self.assertEqual(row["outcome_tier_name"], "Success")
        self.assertTrue(row["may_write_free_text"])
        self.assertEqual([option["id"] for option in row["options"]], [answer.pk])

        sent = self.client.post(
            f"{_BASE}steward-prompts/{prompt.pk}/answer/", {"answer": answer.pk}, format="json"
        )
        self.assertEqual(sent.status_code, 200, sent.content)
        self.assertEqual(Vision.objects.get(recipient=self.sheet).answer, answer)
        self.assertEqual(GMPrompt.objects.get(pk=prompt.pk).status, GMPromptStatus.CONFIRMED)

    def test_the_panel_dismisses_to_the_draw(self) -> None:
        answer = self._full_answer("Success")
        prompt = self._closed("Success")

        response = self.client.post(f"{_BASE}steward-prompts/{prompt.pk}/dismiss/")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Vision.objects.get(recipient=self.sheet).answer, answer)

    def test_a_stranger_does_not_see_the_stewarded_pledge_types(self) -> None:
        stranger = APIClient()
        stranger.force_authenticate(GMProfileFactory().account)
        response = stranger.get(f"{_BASE}pledges/")
        self.assertNotIn(self.pledge.pk, [row["id"] for row in response.json()["results"]])

        member = APIClient()
        member.force_authenticate(self.account)
        response = member.get(f"{_BASE}pledges/")
        self.assertIn(self.pledge.pk, [row["id"] for row in response.json()["results"]])
