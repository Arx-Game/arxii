"""Journeys for the actions ledger (#3657, tranche 6 step 3): a GM stages authored
content in the room she stands in. Each types what a GM types and asserts what she
was told and what rows the room now holds."""

from __future__ import annotations

from integration_tests.harness import JourneyCase
from world.gm.constants import CatalogSuggestionProposalKind, GMLevel
from world.gm.factories import GMProfileFactory
from world.gm.models import CatalogSuggestion
from world.mechanics.constants import DiscoveryType
from world.mechanics.factories import ChallengeTemplateFactory, SituationTemplateFactory
from world.mechanics.models import ChallengeInstance, SituationInstance
from world.scenes.action_constants import DIFFICULTY_BAND_STEP, DIFFICULTY_VALUES, DifficultyChoice


class StagingASituation(JourneyCase):
    """Ravenna, a Junior GM, dresses the cellar with an authored situation and a single
    challenge; Hobb, newly approved, may only browse; Marrow is staff."""

    def setUp(self) -> None:
        super().setUp()
        self.cellar = self.make_room("The Flooded Cellar")
        self.ysmay = self.make_player("Ysmay", room=self.cellar)
        self.hobb = self.make_player("Hobb", room=self.cellar)
        self.ravenna = self.make_player("Ravenna", room=self.cellar)
        self.marrow = self.make_player("Marrow", room=self.cellar)
        staff = self.account_of(self.marrow)
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])
        GMProfileFactory(account=self.account_of(self.ravenna), level=GMLevel.JUNIOR)
        GMProfileFactory(account=self.account_of(self.hobb), level=GMLevel.STARTING)
        self.rising_water = SituationTemplateFactory(name="Rising Water")
        self.barred_gate = ChallengeTemplateFactory(
            name="Barred Gate", severity=DIFFICULTY_VALUES[DifficultyChoice.NORMAL]
        )

    def test_a_junior_gm_sets_the_situation_and_staff_may_too(self) -> None:
        self.assertIn(
            "Set which situation? (setsituation <name|id>)",
            self.telnet(self.ravenna, "setsituation"),
        )
        self.assertIn(
            "No such situation template.", self.telnet(self.ravenna, "setsituation Low Tide")
        )
        self.assertIn("GM trust required.", self.telnet(self.ysmay, "setsituation Rising Water"))
        self.assertIn(
            "Requires Junior GM or higher.", self.telnet(self.hobb, "setsituation Rising Water")
        )
        self.assertFalse(SituationInstance.objects.filter(template=self.rising_water).exists())

        self.telnet(self.ravenna, "setsituation Rising Water")
        self.assertTrue(
            SituationInstance.objects.filter(
                template=self.rising_water, location=self.cellar
            ).exists()
        )
        self.telnet(self.marrow, f"setsituation {self.rising_water.pk}")
        self.assertEqual(
            SituationInstance.objects.filter(
                template=self.rising_water, location=self.cellar
            ).count(),
            2,
        )

    def test_the_catalog_is_browsed_by_anyone_the_game_trusts_a_little(self) -> None:
        self.assertIn("GM trust required.", self.telnet(self.ysmay, "setsituation find Water"))
        told = self.telnet(self.hobb, "setsituation find Water")
        self.assertIn("Situations matching 'Water':", told)
        self.assertIn(f"[{self.rising_water.pk}] Rising Water", told)
        told = self.telnet(self.ravenna, "setsituation find Gate")
        self.assertIn("No situation templates matched 'Gate'.", told)
        self.assertIn(f"[{self.barred_gate.pk}] Barred Gate (Normal)", told)

    def test_one_challenge_is_placed_on_a_named_thing_and_shifted_a_band(self) -> None:
        self.assertIn(
            "Usage: setsituation challenge <name|id>=<target name>",
            self.telnet(self.ravenna, "setsituation challenge Barred Gate"),
        )
        self.assertIn(
            "No such challenge template.",
            self.telnet(self.ravenna, "setsituation challenge Portcullis=the gate"),
        )
        self.assertIn(
            "Name what embodies the challenge (e.g. 'the barred gate').",
            self.telnet(self.ravenna, "setsituation challenge Barred Gate="),
        )
        self.assertIn(
            "Requires Junior GM or higher.",
            self.telnet(self.hobb, "setsituation challenge Barred Gate=the barred gate"),
        )
        self.assertFalse(ChallengeInstance.objects.exists())

        told = self.telnet(self.ravenna, "setsituation challenge Barred Gate=the barred gate")
        self.assertIn("Barred Gate placed on the barred gate (Normal).", told)
        placed = ChallengeInstance.objects.get(template=self.barred_gate)
        self.assertIsNone(placed.situation_instance)
        self.assertEqual(placed.location, self.cellar)
        self.assertEqual(placed.target_object.db_key, "the barred gate")
        self.assertEqual((placed.severity_adjustment, placed.adjustment_reason), (0, ""))
        self.assertTrue(placed.is_active)

        told = self.telnet(
            self.ravenna,
            "setsituation challenge Barred Gate=the far gate setback=they braced it",
        )
        self.assertIn("Barred Gate placed on the far gate (Hard)", told)
        self.assertIn("setback", told)
        braced = ChallengeInstance.objects.get(target_object__db_key="the far gate")
        self.assertEqual(braced.severity_adjustment, DIFFICULTY_BAND_STEP)
        self.assertEqual(braced.adjustment_reason, "they braced it")
        self.assertEqual(braced.effective_severity, DIFFICULTY_VALUES[DifficultyChoice.HARD])

        told = self.telnet(
            self.marrow,
            "setsituation challenge Barred Gate=the rusted gate edge=the hinges are half-rusted",
        )
        self.assertIn("Barred Gate placed on the rusted gate (Easy)", told)
        rusted = ChallengeInstance.objects.get(target_object__db_key="the rusted gate")
        self.assertEqual(rusted.severity_adjustment, -DIFFICULTY_BAND_STEP)
        self.assertEqual(rusted.effective_severity, DIFFICULTY_VALUES[DifficultyChoice.EASY])

        self.assertIn(
            "Shift with edge or setback, not both.",
            self.telnet(
                self.ravenna,
                "setsituation challenge Barred Gate=the gate edge=rusted setback=braced",
            ),
        )
        self.assertEqual(ChallengeInstance.objects.count(), 3)

    def test_the_hardest_band_refuses_to_go_harder_and_a_hidden_seam_stays_hidden(self) -> None:
        ChallengeTemplateFactory(
            name="Sealed Vault", severity=DIFFICULTY_VALUES[DifficultyChoice.HARROWING]
        )
        self.assertIn(
            "Already at the hardest band.",
            self.telnet(
                self.ravenna,
                "setsituation challenge Sealed Vault=the vault door setback=and it is warded",
            ),
        )
        self.assertFalse(ChallengeInstance.objects.exists())

        ChallengeTemplateFactory(name="Hidden Seam", discovery_type=DiscoveryType.DISCOVERABLE)
        told = self.telnet(
            self.ravenna, "setsituation challenge Hidden Seam=the seam in the panelling"
        )
        self.assertIn("(hidden until discovered).", told)
        seam = ChallengeInstance.objects.get(target_object__db_key="the seam in the panelling")
        self.assertFalse(seam.is_revealed)

    def test_a_new_gm_suggests_to_the_catalog_and_staff_hear_it(self) -> None:
        told = self.telnet(self.hobb, "gm suggest new_situation=A dockside smuggling scene.")
        self.assertIn("Suggestion submitted to staff for review.", told)
        suggestion = CatalogSuggestion.objects.get()
        self.assertEqual(suggestion.proposal_kind, CatalogSuggestionProposalKind.NEW_SITUATION)
        self.assertEqual(suggestion.proposal_text, "A dockside smuggling scene.")
        self.assertIn(
            "Usage: gm suggest <kind>=<text>",
            self.telnet(self.hobb, "gm suggest not a valid grammar"),
        )
        self.assertIn(
            "Suggesting a pool_guide needs Experienced GM trust or higher.",
            self.telnet(self.hobb, "gm suggest pool_guide=Use the Mishap pool."),
        )
        self.assertIn(
            "GM trust required.", self.telnet(self.ysmay, "gm suggest other=Anything at all.")
        )
        self.assertEqual(CatalogSuggestion.objects.count(), 1)

    def test_the_web_names_the_template_by_id_and_is_sent_to_the_catalog_without_one(self) -> None:
        result = self.web(self.ravenna, "place_challenge", target_object_name="the gate")
        self.assertFalse(result.detail.success)
        self.assertIn(
            "Place which challenge? (try `setsituation find <term>`)", result.detail.message
        )
        result = self.web(
            self.ravenna, "place_challenge", challenge_template_id=999999, target_object_name="x"
        )
        self.assertFalse(result.detail.success)
        self.assertIn("That challenge template does not exist.", result.detail.message)
        result = self.web(self.ravenna, "set_situation")
        self.assertFalse(result.detail.success)
        self.assertIn("Set which situation?", result.detail.message)
        result = self.web(self.ravenna, "set_situation", situation_template_id=999999)
        self.assertFalse(result.detail.success)
        self.assertIn("That situation template does not exist.", result.detail.message)
        result = self.web(self.ravenna, "set_situation", situation_template_id=self.rising_water.pk)
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertTrue(SituationInstance.objects.filter(template=self.rising_water).exists())
