"""Journeys for the NPC roster API (#4418): browse, ask to borrow, owner answers, play."""

from __future__ import annotations

from django.utils import timezone
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

        third = self.make_player("Cade", room=self.room)
        GMProfileFactory(account=self.account_of(third), level=GMLevel.JUNIOR)
        hidden = self.api(self.account_of(third)).post(
            f"{NPCS}answer/", {"loan_id": loan_id, "accept": True}, format="json"
        )
        self.assertEqual(hidden.status_code, status.HTTP_404_NOT_FOUND)

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

    def test_owner_without_a_gm_character_reads_as_their_role(self) -> None:
        self._list_vael()
        results = self.api(self.other_gm).get(NPCS).json()["results"]
        self.assertEqual(results[0]["owner_name"], "GM")


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

    def test_another_gm_copies_a_listed_npc_without_its_notes(self) -> None:
        other = self.api(self.other_gm)
        self.assertEqual(other.post(f"{self.url}copy-as-new/", {"name": "X"}).status_code, 404)
        self._list_vael()

        copied = other.post(f"{self.url}copy-as-new/", {"name": "Vael's Twin"}, format="json")
        self.assertEqual(copied.status_code, status.HTTP_201_CREATED, copied.data)
        twin = RosterEntry.objects.get(pk=copied.json()["id"])
        self.assertEqual(twin.created_by_account, self.other_gm)
        self.assertEqual(twin.story_npc_settings.notes_for_player, "")
        detail = other.get(f"{NPCS}{twin.pk}/")
        self.assertEqual(detail.status_code, status.HTTP_200_OK, detail.data)
        self.assertEqual(detail.json()["notes_for_player"], "")

        section = other.post(
            f"{NPCS}{twin.pk}/copy-section/",
            {"source_entry": self.entry.pk, "section": "all"},
            format="json",
        )
        self.assertEqual(section.status_code, status.HTTP_200_OK, section.data)
        self.assertEqual(other.get(f"{NPCS}{twin.pk}/").json()["notes_for_player"], "")


class AnOwnerDeclinesAndTemplatesList(NpcRosterCase):
    def test_owner_declines_a_request(self) -> None:
        self._list_vael(policy="on_request")
        # The owner sees who asked by their GM character's name, never the account's.
        mint_gm_character(self.other_gm, "Corvin")
        loan_id = self.api(self.other_gm).post(f"{self.url}borrow/").json()["id"]
        detail = self.api(self.owner).get(self.url).json()
        self.assertEqual(
            detail["open_requests"],
            [{"id": loan_id, "status": "requested", "requester_name": "Corvin"}],
        )
        declined = self.api(self.owner).post(
            f"{NPCS}answer/", {"loan_id": loan_id, "accept": False}, format="json"
        )
        self.assertEqual(declined.status_code, status.HTTP_200_OK, declined.data)
        self.assertEqual(declined.json()["status"], "declined")
        mine = [r["name"] for r in self.api(self.other_gm).get(MINE).json()]
        self.assertNotIn("Captain Vael", mine)

    def test_templates_lists_own_and_staff_templates_only(self) -> None:
        client = self.api(self.owner)
        made = client.post(
            f"{self.url}copy-as-new/", {"name": "Vael Pattern", "as_template": True}, format="json"
        )
        self.assertEqual(made.status_code, status.HTTP_201_CREATED, made.data)
        listed = client.get(f"{NPCS}templates/").json()["results"]
        self.assertEqual([row["name"] for row in listed], ["Vael Pattern"])
        self.assertEqual(self._names(self.owner), [])
        self.assertEqual(self.api(self.other_gm).get(f"{NPCS}templates/").json()["results"], [])


class TheListCostsTheSameForAnyCast(NpcRosterCase):
    def test_query_count_does_not_grow_with_rows_or_owners(self) -> None:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self._list_vael()

        def cost() -> int:
            self.api(self.other_gm).get(NPCS)  # warm per-process caches
            with CaptureQueriesContext(connection) as queries:
                response = self.api(self.other_gm).get(NPCS)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            return len(queries)

        one = cost()
        for index in range(3):
            maker = self.make_player(f"Maker{index}", room=self.room)
            account = self.account_of(maker)
            GMProfileFactory(account=account, level=GMLevel.JUNIOR)
            mint_gm_character(account, f"Warden {index}")
            minted = self.web(maker, "mint_story_npc", name=f"Extra {index}")
            entry = RosterEntry.objects.get(pk=minted.detail.data["roster_entry_id"])
            settings = entry.story_npc_settings
            settings.listed_on_npc_roster = True
            settings.lend_policy = "on_request"
            settings.save()
        self.assertEqual(len(self._names(self.other_gm)), 4)
        self.assertEqual(cost(), one)


class CanBorrowAgreesWithRequestBorrow(NpcRosterCase):
    def test_matrix(self) -> None:
        from world.roster.services.npc_lending import (
            NPCLendingError,
            request_borrow,
        )
        from world.roster.views.npc_views import NPCViewer, npc_entries

        staff_player = self.make_player("Staffer", room=self.room)
        staff = self.account_of(staff_player)
        staff.is_staff = True
        staff.save()
        viewers = {"gm": self.other_gm, "guide": self.guide, "owner": self.owner, "staff": staff}

        def agreement(label: str) -> None:
            for who, account in viewers.items():
                entry = npc_entries().get(pk=self.entry.pk)
                predicted = NPCViewer.for_account(account).can_borrow(
                    entry, entry.story_npc_settings
                )
                try:
                    loan = request_borrow(entry=self.entry, borrower=account)
                except NPCLendingError:
                    actual = False
                else:
                    actual = True
                    loan.delete()
                self.assertEqual(predicted, actual, f"{label} / {who}")

        def configure(**fields) -> None:
            settings = self.entry.story_npc_settings
            for key, value in fields.items():
                setattr(settings, key, value)
            settings.save()

        configure(listed_on_npc_roster=True, lend_policy="not_lent")
        agreement("not lent")
        configure(lend_policy="on_request", borrow_audience="gms")
        agreement("gms only")
        configure(borrow_audience="gms_and_guides")
        agreement("gms and guides")
        configure(listed_on_npc_roster=False)
        agreement("unlisted")
        configure(listed_on_npc_roster=True)
        NPCLoan.objects.create(
            roster_entry=self.entry,
            borrower=self.other_gm,
            offered_by=self.owner,
            status="requested",
        )
        agreement("existing request")
        NPCLoan.objects.all().delete()
        tenure = self.entry.current_tenure
        tenure.end_date = timezone.now()
        tenure.save()
        self.entry.invalidate_tenure_cache()
        agreement("unheld")


class AGuideReadsItsOffers(NpcRosterCase):
    def setUp(self) -> None:
        super().setUp()
        from world.scenes.factories import SceneFactory, SceneParticipationFactory

        mint_gm_character(self.owner, "Warden Osk")
        self.scene = SceneFactory(room=self.room, name="The Siege at Low Gate")
        SceneParticipationFactory(scene=self.scene, account=self.owner, is_gm=True, is_owner=True)
        settings = self.entry.story_npc_settings
        settings.notes_for_player = NOTES
        settings.save()

    def _offer(self, entry_id=None):
        return self.web(
            self.ravenna,
            "offer_npc",
            roster_entry_id=entry_id or self.entry.pk,
            guide_account_id=self.guide.pk,
        )

    def test_offers_list_then_clear_on_accept(self) -> None:
        offered = self._offer()
        self.assertTrue(offered.detail.success, offered.detail.message)
        loan_id = offered.detail.data["loan_id"]

        rows = self.api(self.guide).get(f"{NPCS}offers/").json()["results"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["loan_id"], loan_id)
        self.assertEqual(row["roster_entry_id"], self.entry.pk)
        self.assertEqual(row["name"], "Captain Vael")
        self.assertEqual(row["scene_id"], self.scene.pk)
        self.assertEqual(row["scene_title"], "The Siege at Low Gate")
        self.assertEqual(row["offered_by_name"], "Warden Osk")
        self.assertEqual(row["notes_for_player"], NOTES)
        self.assertIn("thumbnail_url", row)

        other_guide = self.make_player("Maren", room=self.room)
        GuideProfileFactory(account=self.account_of(other_guide))
        empty = self.api(self.account_of(other_guide)).get(f"{NPCS}offers/").json()
        self.assertEqual(empty["results"], [])

        accepted = self.web(self.ilsa, "answer_npc_loan", loan_id=loan_id, accept=True)
        self.assertTrue(accepted.detail.success, accepted.detail.message)
        self.assertEqual(self.api(self.guide).get(f"{NPCS}offers/").json()["results"], [])
        mine = {r["name"]: r for r in self.api(self.guide).get(MINE).json()}
        self.assertIn("Captain Vael", mine)
        self.assertIs(mine["Captain Vael"]["is_crowd_voice"], False)

    def test_a_lent_crowd_voice_is_marked(self) -> None:
        from world.combat.factories import CombatOpponentFactory

        CombatOpponentFactory(voice_persona=self.entry.character_sheet.primary_persona)
        offered = self._offer()
        loan_id = offered.detail.data["loan_id"]
        self.web(self.ilsa, "answer_npc_loan", loan_id=loan_id, accept=True)
        mine = {r["name"]: r for r in self.api(self.guide).get(MINE).json()}
        self.assertIs(mine["Captain Vael"]["is_crowd_voice"], True)
        self.assertIs(mine["Ilsa"]["is_crowd_voice"], False)


class CrowdVoiceShowsOnEverySurface(NpcRosterCase):
    def test_selected_entry_payload_marks_a_crowd_voice(self) -> None:
        from evennia_extensions.models import PlayerData
        from world.combat.factories import CombatOpponentFactory
        from world.roster.services.selection import set_selected_entry

        CombatOpponentFactory(voice_persona=self.entry.character_sheet.primary_persona)
        player_data = PlayerData.objects.get(account=self.owner)
        set_selected_entry(player_data, self.entry)
        payload = self.api(self.owner).get("/api/user/").json()
        self.assertIs(payload["selected_entry"]["is_crowd_voice"], True)
        ysmay_payload = self.api(self.pc).get("/api/user/").json()
        self.assertIs(ysmay_payload["selected_entry"]["is_crowd_voice"], False)


class OfferListQueryCount(NpcRosterCase):
    def test_offers_cost_the_same_for_one_or_five(self) -> None:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from world.scenes.factories import SceneFactory, SceneParticipationFactory

        guide_client = self.api(self.guide)

        def offer_from_new_gm(index: int) -> None:
            room = self.make_room(f"Hall {index}")
            maker = self.make_player(f"Offerer{index}", room=room)
            account = self.account_of(maker)
            GMProfileFactory(account=account, level=GMLevel.JUNIOR)
            mint_gm_character(account, f"Warden {index}")
            minted = self.web(maker, "mint_story_npc", name=f"Extra {index}")
            scene = SceneFactory(room=room, name=f"Scene {index}")
            SceneParticipationFactory(scene=scene, account=account, is_gm=True, is_owner=True)
            offered = self.web(
                maker,
                "offer_npc",
                roster_entry_id=minted.detail.data["roster_entry_id"],
                guide_account_id=self.guide.pk,
            )
            self.assertTrue(offered.detail.success, offered.detail.message)

        def cost() -> tuple[int, int]:
            from world.roster.models import RosterEntry as Entry

            guide_client.get(f"{NPCS}offers/")
            for model in (NPCLoan, Entry):
                model.flush_instance_cache()
            with CaptureQueriesContext(connection) as queries:
                response = guide_client.get(f"{NPCS}offers/")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            return len(queries), len(response.json()["results"])

        offer_from_new_gm(0)
        one, rows = cost()
        self.assertEqual(rows, 1)
        for index in range(1, 5):
            offer_from_new_gm(index)
        five, rows = cost()
        self.assertEqual(rows, 5)
        self.assertEqual(five, one)

    def test_offer_with_no_known_offerer_reads_as_staff(self) -> None:
        from world.roster.models import NPCLoan as Loan
        from world.roster.serializers.npc_roster import NPCOfferSerializer

        loan = Loan(roster_entry=self.entry, borrower=self.guide, offered_by=self.owner)
        data = NPCOfferSerializer(loan, context={"offered_names": {}}).data
        self.assertEqual(data["offered_by_name"], "Staff")


class TheAccountSaysWhetherItIsAGuide(NpcRosterCase):
    def test_is_guide_follows_an_active_guide_profile(self) -> None:
        self.assertIs(self.api(self.guide).get("/api/user/").json()["is_guide"], True)
        self.assertIs(self.api(self.other_gm).get("/api/user/").json()["is_guide"], False)
        profile = self.guide.guide_profile
        profile.is_active = False
        profile.save()
        self.assertIs(self.api(self.guide).get("/api/user/").json()["is_guide"], False)
