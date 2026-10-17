"""Journeys for a table GM reading a player's hooks (#4397): the GM reads them with the truths
underneath, writes a truth the player still cannot see, adds a hook; a member, another GM and a
stranger are refused; a character not seated at the table is not found."""

from __future__ import annotations

from django.urls import reverse

from integration_tests.harness import JourneyCase
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.gm.services import join_table
from world.secrets.factories import SecretFactory
from world.secrets.services import secrets_owned_by


class ATableGMReadsHooks(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        room = self.make_room("The Lantern")
        self.calista = self.make_player("Calista", room=room)
        self.hobb = self.make_player("Hobb", room=room)
        self.wat = self.make_player("Wat", room=room)
        self.gm_account = self.account_of(self.hobb)
        self.table = GMTableFactory(
            gm=GMProfileFactory(account=self.gm_account), name="The Lantern"
        )
        join_table(self.table, self.calista.sheet_data.primary_persona)
        self.dreams = SecretFactory(
            subject_sheet=self.calista.sheet_data, content="Dreams that tell."
        )
        SecretFactory(subject_sheet=self.calista.sheet_data, content="A keepsake.")
        self.url = reverse(
            "gm:gm-table-player-hooks", args=[self.table.pk, self.calista.sheet_data.pk]
        )

    def test_the_gm_reads_the_hooks_and_writes_the_truth_the_player_cannot_see(self) -> None:
        gm = self.api(self.gm_account)
        response = gm.get(self.url)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            [h["content"] for h in response.data], ["Dreams that tell.", "A keepsake."]
        )
        self.assertEqual(response.data[0]["kind"], "Unknown")
        self.assertEqual(response.data[0]["truths"], [])

        response = gm.post(
            self.url,
            {"hook": self.dreams.pk, "content": "The naga schemer sends them."},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["id"], self.dreams.pk)
        self.assertEqual(response.data["truths"][0]["content"], "The naga schemer sends them.")
        self.assertFalse(response.data["truths"][0]["subject_aware"])

        shelf = list(secrets_owned_by(self.calista.sheet_data).values_list("content", flat=True))
        self.assertIn("Dreams that tell.", shelf)
        self.assertNotIn("The naga schemer sends them.", shelf)

    def test_the_gm_adds_a_hook_of_their_own(self) -> None:
        gm = self.api(self.gm_account)
        response = gm.post(self.url, {"content": "Someone paid for her passage."}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(response.data["aware"])
        self.assertEqual(response.data["provenance"], "gm")
        hooks = [h["content"] for h in gm.get(self.url).data]
        self.assertIn("Someone paid for her passage.", hooks)

    def test_a_member_another_gm_and_a_stranger_are_refused(self) -> None:
        # Calista sits at the table; what she does not know stays off this route.
        self.assertEqual(self.api(self.account_of(self.calista)).get(self.url).status_code, 403)
        # Another GM does not see this table at all (the table viewset's own scoping).
        other_gm = GMProfileFactory(account=self.account_of(self.wat))
        GMTableFactory(gm=other_gm)
        self.assertEqual(self.api(self.account_of(self.wat)).get(self.url).status_code, 404)
        self.assertEqual(self.api(None).get(self.url).status_code, 403)

    def test_a_character_not_at_the_table_is_not_found(self) -> None:
        url = reverse("gm:gm-table-player-hooks", args=[self.table.pk, self.wat.sheet_data.pk])
        self.assertEqual(self.api(self.gm_account).get(url).status_code, 404)

    def test_staff_read_any_table(self) -> None:
        staff = self.account_of(self.wat)
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])
        self.assertEqual(self.api(staff).get(self.url).status_code, 200)
