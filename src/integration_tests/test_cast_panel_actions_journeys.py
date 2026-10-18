"""Journeys for the GM cast panel's tools (#4418): they name the scene, not where the GM stands."""

from __future__ import annotations

from rest_framework import status

from integration_tests.harness import JourneyCase
from world.combat.constants import OpponentTier
from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory, ThreatPoolFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, GuideProfileFactory, seed_default_gm_level_caps
from world.roster.models import NPCLoan, RosterEntry
from world.scenes.factories import SceneFactory, SceneParticipationFactory

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
