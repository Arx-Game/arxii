"""Journeys for the NPC roster API (#4418): browse, ask to borrow, owner answers, play."""

from __future__ import annotations

from rest_framework import status

from integration_tests.harness import JourneyCase
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, GuideProfileFactory, seed_default_gm_level_caps
from world.roster.models import NPCLoan, RosterEntry
from world.roster.services.staff_characters import mint_gm_character

NPCS = "/api/roster/npcs/"
MINE = "/api/roster/entries/mine/"
NOTES = "Never let anyone see her hands shake."


class NpcRosterCase(JourneyCase):
    """Ravenna owns Captain Vael and lists him; Ilsa is a Guide; Bram is another GM."""

    def setUp(self) -> None:
        super().setUp()
        seed_default_gm_level_caps()
        self.room = self.make_room("Low Gate")
        self.ravenna = self.make_player("Ravenna", room=self.room)
        self.owner = self.account_of(self.ravenna)
        GMProfileFactory(account=self.owner, level=GMLevel.JUNIOR)
        self.ilsa = self.make_player("Ilsa", room=self.room)
        self.guide = self.account_of(self.ilsa)
        GuideProfileFactory(account=self.guide)
        self.bram = self.make_player("Bram", room=self.room)
        self.other_gm = self.account_of(self.bram)
        GMProfileFactory(account=self.other_gm, level=GMLevel.JUNIOR)
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.pc = self.account_of(self.ysmay)

        minted = self.web(self.ravenna, "mint_story_npc", name="Captain Vael")
        self.assertTrue(minted.detail.success, minted.detail.message)
        self.entry = RosterEntry.objects.get(pk=minted.detail.data["roster_entry_id"])
        self.url = f"{NPCS}{self.entry.pk}/"

    def _list_vael(self, borrower_audience="gms", policy="on_request", listed=True):
        patched = self.api(self.owner).patch(
            self.url,
            {
                "listed_on_npc_roster": listed,
                "lend_policy": policy,
                "borrow_audience": borrower_audience,
                "notes_for_player": NOTES,
            },
            format="json",
        )
        self.assertEqual(patched.status_code, status.HTTP_200_OK, patched.data)

    def _names(self, account, query="") -> list[str]:
        response = self.api(account).get(f"{NPCS}{query}")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return [row["name"] for row in response.json()["results"]]


class AGmBorrowsAListedNpc(NpcRosterCase):
    def test_ask_to_borrow_owner_approves_borrower_plays(self) -> None:
        self._list_vael(policy="on_request")
        self.assertEqual(self._names(self.other_gm), ["Captain Vael"])
        row = self.api(self.other_gm).get(NPCS).json()["results"][0]
        self.assertTrue(row["can_borrow"])
        self.assertEqual(self._names(self.other_gm, "?lendable_to_me=true"), ["Captain Vael"])

        asked = self.api(self.other_gm).post(f"{self.url}borrow/")
        self.assertEqual(asked.status_code, status.HTTP_201_CREATED, asked.data)
        loan_id = asked.json()["id"]
        self.assertEqual(asked.json()["status"], "requested")
        mine = [r["name"] for r in self.api(self.other_gm).get(MINE).json()]
        self.assertNotIn("Captain Vael", mine)
        again = self.api(self.other_gm).get(NPCS).json()["results"][0]
        self.assertFalse(again["can_borrow"])

        refused = self.api(self.other_gm).post(
            f"{NPCS}answer/", {"loan_id": loan_id, "accept": True}, format="json"
        )
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(refused.json()["detail"], "Only the NPC's owner can answer that request.")

        answered = self.api(self.owner).post(
            f"{NPCS}answer/", {"loan_id": loan_id, "accept": True}, format="json"
        )
        self.assertEqual(answered.status_code, status.HTTP_200_OK, answered.data)
        self.assertEqual(answered.json()["status"], "active")
        self.assertEqual(NPCLoan.objects.get(pk=loan_id).status, "active")

        mine = [r["name"] for r in self.api(self.other_gm).get(MINE).json()]
        self.assertIn("Captain Vael", mine)
        mine = [r["name"] for r in self.api(self.owner).get(MINE).json()]
        self.assertNotIn("Captain Vael", mine)

    def test_a_guide_cannot_borrow_gms_only_and_a_pc_cannot_browse(self) -> None:
        self._list_vael(borrower_audience="gms")
        self.assertEqual(self.api(self.guide).get(f"{self.url}").status_code, 404)
        guide_row = self.api(self.guide).get(NPCS).json()["results"][0]
        self.assertFalse(guide_row["can_borrow"])
        refused = self.api(self.guide).post(f"{self.url}borrow/")
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(refused.json()["detail"], "That NPC is lent only to GMs.")
        self.assertEqual(self.api(self.pc).get(NPCS).status_code, status.HTTP_403_FORBIDDEN)

        self._list_vael(borrower_audience="gms_and_guides")
        self.assertTrue(self.api(self.guide).get(NPCS).json()["results"][0]["can_borrow"])


class NotesAreGuarded(NpcRosterCase):
    def test_notes_are_owner_borrower_and_staff_only(self) -> None:
        self._list_vael(policy="without_asking")

        def notes_seen(account):
            return self.api(account).get(NPCS).json()["results"][0].get("notes_for_player")

        self.assertEqual(notes_seen(self.owner), NOTES)
        self.assertNotIn("notes_for_player", self.api(self.other_gm).get(NPCS).json()["results"][0])
        self.assertEqual(self.api(self.other_gm).get(self.url).status_code, 404)

        borrowed = self.api(self.other_gm).post(f"{self.url}borrow/")
        self.assertEqual(borrowed.status_code, status.HTTP_201_CREATED, borrowed.data)
        self.assertEqual(borrowed.json()["status"], "active")
        self.assertEqual(notes_seen(self.other_gm), NOTES)
        seen = self.api(self.other_gm).get(self.url)
        self.assertEqual(seen.status_code, 200)
        self.assertEqual(seen.json()["notes_for_player"], NOTES)
        # An active borrower reads the notes but cannot change the holder's settings.
        edit = self.api(self.other_gm).patch(self.url, {"lend_policy": "not_lent"}, format="json")
        self.assertEqual(edit.status_code, 404)

        staff = self.make_player("Staffer", room=self.room)
        staff_account = self.account_of(staff)
        staff_account.is_staff = True
        staff_account.save()
        self.assertEqual(notes_seen(staff_account), NOTES)
        # Someone else, signed in as a GM without the loan, still sees none.
        third = self.make_player("Cade", room=self.room)
        GMProfileFactory(account=self.account_of(third), level=GMLevel.JUNIOR)
        self.assertIsNone(notes_seen(self.account_of(third)))


class OwnerNameIsACharacter(NpcRosterCase):
    def test_owner_shown_by_gm_character_name(self) -> None:
        mint_gm_character(self.owner, "Warden Osk")
        self._list_vael()
        response = self.api(self.other_gm).get(NPCS)
        results = response.json()["results"]
        self.assertEqual(results[0]["owner_name"], "Warden Osk")
        self.assertNotIn(self.owner.username, response.content.decode())

    def test_owner_without_a_gm_character_reads_as_staff(self) -> None:
        self._list_vael()
        results = self.api(self.other_gm).get(NPCS).json()["results"]
        self.assertEqual(results[0]["owner_name"], "Staff")


class AnOwnerAuthorsAnNpc(NpcRosterCase):
    def test_owner_authors_and_copies_others_get_404(self) -> None:
        from world.npc_services.models import NpcPreference, NpcRegard, PersonalityTrait

        trait = PersonalityTrait.objects.create(name="Vanity")
        client = self.api(self.owner)
        persona = self.ysmay.sheet_data.primary_persona
        regard = client.put(
            f"{self.url}regard/",
            {"target_type": "persona", "target_id": persona.pk, "value": 40},
            format="json",
        )
        self.assertEqual(regard.status_code, status.HTTP_200_OK, regard.data)
        holder = self.entry.character_sheet.primary_persona
        self.assertEqual(NpcRegard.objects.get(holder_persona=holder).value, 40)
        prefs = client.put(
            f"{self.url}preferences/",
            {"preferences": [{"trait": trait.pk, "valence": "likes"}]},
            format="json",
        )
        self.assertEqual(prefs.status_code, status.HTTP_200_OK, prefs.data)
        self.assertEqual(NpcPreference.objects.get(persona=holder).valence, "likes")

        copied = client.post(f"{self.url}copy-as-new/", {"name": "Captain Vael II"}, format="json")
        self.assertEqual(copied.status_code, status.HTTP_201_CREATED, copied.data)
        new_url = f"{NPCS}{copied.json()['id']}/"
        self.assertEqual(client.get(new_url).status_code, 200)
        section = client.post(
            f"{new_url}copy-section/",
            {"source_entry": self.entry.pk, "section": "regard"},
            format="json",
        )
        self.assertEqual(section.status_code, status.HTTP_200_OK, section.data)

        other = self.api(self.other_gm)
        self.assertEqual(other.put(f"{self.url}regard/", {}, format="json").status_code, 404)
        self.assertEqual(other.post(f"{self.url}copy-as-new/", {"name": "X"}).status_code, 404)
        stolen = other.post(
            f"{NPCS}{copied.json()['id']}/copy-section/",
            {"source_entry": self.entry.pk, "section": "all"},
            format="json",
        )
        self.assertEqual(stolen.status_code, 404)
        self.assertEqual(other.get(f"{NPCS}templates/").json()["results"], [])
