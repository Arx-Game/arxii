"""Journeys for the GM cast panel's tools (#4418): they name the scene, not where the GM stands."""

from __future__ import annotations

from rest_framework import status

from integration_tests.harness import JourneyCase
from world.combat.constants import OpponentTier
from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory, ThreatPoolFactory
from world.combat.models import CombatOpponent
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, GuideProfileFactory, seed_default_gm_level_caps
from world.roster.constants import NPCLendPolicy
from world.roster.models import NPCLoan, RosterEntry
from world.roster.services.staff_characters import mint_gm_character
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.models import Persona

CAST_LIST = "/api/scenes/{}/cast-list/"
REFUSED = "Only the scene's GM or staff can do that."


class TheGmRunsTheCastFromAnywhere(JourneyCase):
    """Ravenna GMs the siege at Low Gate but is browsing as a character in her study;
    Ilsa is a Guide; Ysmay is a player at the gate."""

    def setUp(self) -> None:
        super().setUp()
        seed_default_gm_level_caps()
        self.gate = self.make_room("Low Gate")
        self.study = self.make_room("Ravenna's Study")
        self.ravenna = self.make_player("Ravenna", room=self.study)
        self.gm = self.account_of(self.ravenna)
        GMProfileFactory(account=self.gm, level=GMLevel.JUNIOR)
        self.ilsa = self.make_player("Ilsa", room=self.gate)
        self.guide = self.account_of(self.ilsa)
        GuideProfileFactory(account=self.guide)
        self.ysmay = self.make_player("Ysmay", room=self.gate)

        self.scene = SceneFactory(room=self.gate, name="The Siege at Low Gate")
        SceneParticipationFactory(scene=self.scene, account=self.gm, is_gm=True, is_owner=True)

        minted = self.web(
            self.ravenna, "mint_story_npc", name="Captain Vael", description="An officer."
        )
        self.assertTrue(minted.detail.success, minted.detail.message)
        self.entry = RosterEntry.objects.get(pk=minted.detail.data["roster_entry_id"])
        vael = self.entry.character_sheet.character
        vael.location = self.gate
        vael.save()

        self.encounter = CombatEncounterFactory(scene=self.scene, room=self.gate)
        pool = ThreatPoolFactory(name="Low Gate watch", description="Tired spearmen.")
        self.guards = [
            CombatOpponentFactory(
                encounter=self.encounter,
                tier=OpponentTier.MOOK,
                threat_pool=pool,
                name=f"Low Gate watch {number}",
            )
            for number in range(8)
        ]

    def _offer(self, character):
        return self.web(
            character,
            "offer_npc",
            roster_entry_id=self.entry.pk,
            guide_account_id=self.guide.pk,
            scene_id=self.scene.pk,
        )

    def test_a_gm_elsewhere_offers_and_takes_back_by_scene(self) -> None:
        offered = self._offer(self.ravenna)
        self.assertTrue(offered.detail.success, offered.detail.message)
        loan_id = offered.detail.data["loan_id"]
        self.assertEqual(NPCLoan.objects.get(pk=loan_id).scene, self.scene)

        accepted = self.web(self.ilsa, "answer_npc_loan", loan_id=loan_id, accept=True)
        self.assertTrue(accepted.detail.success, accepted.detail.message)

        taken = self.web(self.ravenna, "take_back_npc", loan_id=loan_id, scene_id=self.scene.pk)
        self.assertTrue(taken.detail.success, taken.detail.message)
        self.assertEqual(NPCLoan.objects.get(pk=loan_id).status, "ended")

    def _vael_row(self) -> dict:
        rows = self.api(self.gm).get(CAST_LIST.format(self.scene.pk)).json()
        return next(row for row in rows if row["name"] == "Captain Vael")

    def test_the_cast_list_says_what_role_the_player_plays_in(self) -> None:
        # Real-testing bug H: a GM who borrowed from the roster was shown as a Guide.
        mint_gm_character(self.gm, "Ravenna's Mask")
        row = self._vael_row()
        self.assertEqual((row["played_by"], row["played_by_role"]), ("Ravenna's Mask", "gm"))

        offered = self._offer(self.ravenna)
        loan_id = offered.detail.data["loan_id"]
        self.web(self.ilsa, "answer_npc_loan", loan_id=loan_id, accept=True)
        self.assertEqual(self._vael_row()["played_by_role"], "guide")
        self.web(self.ravenna, "take_back_npc", loan_id=loan_id, scene_id=self.scene.pk)

        # Corvin, a GM with no Guide role, borrows Vael from the NPC roster.
        corvin_account = self.account_of(self.make_player("Bram", room=self.study))
        GMProfileFactory(account=corvin_account, level=GMLevel.JUNIOR)
        mint_gm_character(corvin_account, "Corvin")
        settings = self.entry.story_npc_settings
        settings.listed_on_npc_roster = True
        settings.lend_policy = NPCLendPolicy.WITHOUT_ASKING
        settings.save()
        borrowed = self.api(corvin_account).post(f"/api/roster/npcs/{self.entry.pk}/borrow/")
        self.assertEqual(borrowed.json()["status"], "active", borrowed.data)
        row = self._vael_row()
        self.assertEqual((row["played_by"], row["played_by_role"]), ("Corvin", "gm"))

    def test_someone_who_does_not_run_the_scene_is_refused(self) -> None:
        offered = self._offer(self.ysmay)
        self.assertFalse(offered.detail.success)
        self.assertEqual(offered.detail.message, REFUSED)
        self.assertFalse(NPCLoan.objects.exists())

        guards = [guard.pk for guard in self.guards]
        renamed = self.web(
            self.ysmay, "describe_crowd", opponent_ids=guards, name="Rabble", scene_id=self.scene.pk
        )
        self.assertFalse(renamed.detail.success)
        self.assertEqual(renamed.detail.message, REFUSED)

    def test_describe_crowd_renames_the_mooks_in_the_cast_list(self) -> None:
        described = self.web(
            self.ravenna,
            "describe_crowd",
            opponent_ids=[guard.pk for guard in self.guards],
            name="Gate wardens",
            description="Eight wardens in rain-dark cloaks.",
            scene_id=self.scene.pk,
        )
        self.assertTrue(described.detail.success, described.detail.message)

        response = self.api(self.gm).get(CAST_LIST.format(self.scene.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        crowds = [row for row in response.json() if row["kind"] == "crowd"]
        self.assertEqual(len(crowds), 1)
        self.assertEqual(crowds[0]["name"], "Gate wardens")
        self.assertEqual(crowds[0]["description"], "Eight wardens in rain-dark cloaks.")
        self.assertEqual(crowds[0]["count"], 8)

    def test_describing_a_voiced_crowd_renames_its_voice(self) -> None:
        voiced = self.web(
            self.ravenna,
            "voice_crowd",
            opponent_ids=[guard.pk for guard in self.guards],
            name="Gate guards",
            scene_id=self.scene.pk,
        )
        self.assertTrue(voiced.detail.success, voiced.detail.message)
        described = self.web(
            self.ravenna,
            "describe_crowd",
            opponent_ids=[guard.pk for guard in self.guards],
            name="Gate wardens",
            scene_id=self.scene.pk,
        )
        self.assertTrue(described.detail.success, described.detail.message)
        crowds = [
            row
            for row in self.api(self.gm).get(CAST_LIST.format(self.scene.pk)).json()
            if row["kind"] == "crowd"
        ]
        self.assertEqual([row["name"] for row in crowds], ["Gate wardens"])
        entry = RosterEntry.objects.get(pk=voiced.detail.data["roster_entry_id"])
        self.assertEqual(entry.character_sheet.character.key, "Gate wardens")
        self.assertEqual(
            Persona.objects.get(pk=voiced.detail.data["persona_id"]).name, "Gate wardens"
        )

    def test_describing_a_voiced_crowd_shows_the_new_description(self) -> None:
        # #4418 bug 2: the row read the voice's old description after the edit.
        guard_ids = [guard.pk for guard in self.guards]
        voiced = self.web(
            self.ravenna,
            "voice_crowd",
            opponent_ids=guard_ids,
            name="Gate guards",
            scene_id=self.scene.pk,
        )
        self.assertTrue(voiced.detail.success, voiced.detail.message)
        described = self.web(
            self.ravenna,
            "describe_crowd",
            opponent_ids=guard_ids,
            name="",
            description="Eight wardens in rain-dark cloaks.",
            scene_id=self.scene.pk,
        )
        self.assertTrue(described.detail.success, described.detail.message)
        crowds = [
            row
            for row in self.api(self.gm).get(CAST_LIST.format(self.scene.pk)).json()
            if row["kind"] == "crowd"
        ]
        self.assertEqual(
            [row["description"] for row in crowds], ["Eight wardens in rain-dark cloaks."]
        )

    def test_renaming_a_crowd_renames_its_bodies_in_the_room(self) -> None:
        # Round 3: the room's object list kept showing the bodies' old name.
        guard_ids = [guard.pk for guard in self.guards]
        voiced = self.web(
            self.ravenna,
            "voice_crowd",
            opponent_ids=guard_ids,
            name="Gate guards",
            scene_id=self.scene.pk,
        )
        self.assertTrue(voiced.detail.success, voiced.detail.message)
        for _ in range(2):  # a second save under the same name is not "name taken"
            renamed = self._describe(guard_ids, "Gate wardens")
            self.assertTrue(renamed.detail.success, renamed.detail.message)

        bodies = [guard.objectdb for guard in CombatOpponent.objects.filter(pk__in=guard_ids)]
        self.assertEqual(len(bodies), 8)
        self.assertEqual({body.key for body in bodies}, {"Gate wardens"})
        self.assertEqual({body.location for body in bodies}, {self.gate})
        in_room = [obj.key for obj in self.gate.contents if obj in bodies]
        self.assertEqual(in_room, ["Gate wardens"] * 8)

    def _describe(self, opponent_ids, name: str):
        return self.web(
            self.ravenna,
            "describe_crowd",
            opponent_ids=opponent_ids,
            name=name,
            scene_id=self.scene.pk,
        )

    def test_a_voice_cannot_take_a_name_already_in_use(self) -> None:
        guard_ids = [guard.pk for guard in self.guards]
        voiced = self.web(
            self.ravenna,
            "voice_crowd",
            opponent_ids=guard_ids,
            name="Gate guards",
            scene_id=self.scene.pk,
        )
        self.assertTrue(voiced.detail.success, voiced.detail.message)
        refused = self._describe(guard_ids, "Captain Vael")
        self.assertFalse(refused.detail.success)
        self.assertEqual(refused.detail.message, "A character by that name already exists.")
        self.assertFalse(CombatOpponent.objects.filter(name="Captain Vael").exists())

    def test_a_name_longer_than_the_crowd_can_hold_is_refused(self) -> None:
        refused = self._describe([guard.pk for guard in self.guards], "W" * 201)
        self.assertFalse(refused.detail.success)
        self.assertEqual(refused.detail.message, "A crowd's name can be at most 200 characters.")
        accepted = self._describe([guard.pk for guard in self.guards], "W" * 200)
        self.assertTrue(accepted.detail.success, accepted.detail.message)

    def test_a_finished_fight_or_two_fights_are_not_one_crowd(self) -> None:
        other = CombatEncounterFactory(scene=self.scene, room=self.gate)
        stray = CombatOpponentFactory(encounter=other, tier=OpponentTier.MOOK, name="Stray")
        mixed = self._describe([self.guards[0].pk, stray.pk], "Rabble")
        self.assertFalse(mixed.detail.success)
        self.assertEqual(mixed.detail.message, "A crowd belongs to one fight.")

        self.encounter.status = RoundStatus.COMPLETED
        self.encounter.save()
        finished = self._describe([guard.pk for guard in self.guards], "Rabble")
        self.assertFalse(finished.detail.success)
        self.assertEqual(finished.detail.message, "Those aren't a crowd still in the fight.")
        self.assertFalse(CombatOpponent.objects.filter(name="Rabble").exists())
