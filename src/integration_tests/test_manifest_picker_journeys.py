"""Journeys for the technique picker (#4341): a character chooses which bound being or
companion her manifesting technique brings into a fight, on telnet (``manifest``), on the
web (``manifest_set`` dispatch) and reads her options through the API.

The patronage is a PACT-valence standing built from a factory, the bond a pact signing
leaves behind, for isolation; signing is proven in
``integration_tests.test_pacts_with_beings_journeys``.
"""

from __future__ import annotations

from django.utils import timezone

from integration_tests.harness import JourneyCase
from world.companions.factories import CompanionArchetypeFactory, CompanionFactory
from world.magic.factories import (
    CharacterTechniqueFactory,
    KnownUltimateFactory,
    TechniqueFactory,
    TechniqueManifestOptionFactory,
    UltimateTechniqueFactory,
)
from world.magic.models import CharacterManifestation
from world.worship.factories import DevotionStandingFactory, WorshippedBeingFactory
from world.worship.models import PatronageValence

CHOICES_URL = "/api/magic/manifest-choices/"


class ChoosingWhatATechniqueBrings(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Hollow")
        self.mira = self.make_player("Mira", room=self.room)
        self.sheet = self.mira.sheet_data
        self.hesk = WorshippedBeingFactory(name="Hesk")
        self.wolf = CompanionArchetypeFactory(name="Wolf")
        self.summon = TechniqueFactory(name="Summon")
        CharacterTechniqueFactory(character=self.sheet, technique=self.summon)
        self.hesk_option = TechniqueManifestOptionFactory(technique=self.summon, being=self.hesk)
        self.wolf_option = TechniqueManifestOptionFactory(
            technique=self.summon, being=None, archetype=self.wolf
        )
        DevotionStandingFactory(
            character_sheet=self.sheet,
            being=self.hesk,
            valence=PatronageValence.PACT,
            established_at=timezone.now(),
        )

    def _pick(self) -> CharacterManifestation | None:
        return CharacterManifestation.objects.filter(
            character=self.sheet, technique=self.summon
        ).first()

    def test_manifest_lists_each_option_and_why_one_cannot_be_chosen(self) -> None:
        told = self.telnet(self.mira, "manifest")
        self.assertIn("|wSummon|n brings into a fight:", told)
        self.assertIn("Hesk (your patron)", told)
        self.assertIn("Wolf - unavailable: you have no Wolf companion", told)

    def test_she_chooses_her_patron_and_is_told_so(self) -> None:
        told = self.telnet(self.mira, "manifest Summon=Hesk")
        self.assertIn("Summon will bring Hesk into a fight.", told)
        pick = self._pick()
        self.assertEqual(pick.option, self.hesk_option)
        self.assertIsNone(pick.companion)
        self.assertIn("Hesk (your patron) - chosen", self.telnet(self.mira, "manifest"))

    def test_an_option_whose_bond_does_not_hold_is_refused_with_the_reason(self) -> None:
        told = self.telnet(self.mira, "manifest Summon=Wolf")
        self.assertIn("You have no Wolf companion.", told)
        self.assertIsNone(self._pick())

    def test_a_released_companion_is_named_as_the_reason(self) -> None:
        CompanionFactory(
            owner=self.sheet, archetype=self.wolf, name="Fang", released_at=timezone.now()
        )
        told = self.telnet(self.mira, "manifest Summon=Wolf")
        self.assertIn("Your Wolf companion was released.", told)

    def test_on_the_web_she_switches_to_her_companion(self) -> None:
        self.web(
            self.mira, "manifest_set", technique_id=self.summon.pk, option_id=self.hesk_option.pk
        )
        fang = CompanionFactory(owner=self.sheet, archetype=self.wolf, name="Fang")
        result = self.web(
            self.mira, "manifest_set", technique_id=self.summon.pk, option_id=self.wolf_option.pk
        )
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, "Summon will bring Fang into a fight.")
        pick = self._pick()
        self.assertEqual((pick.option, pick.companion), (self.wolf_option, fang))
        self.assertEqual(CharacterManifestation.objects.filter(character=self.sheet).count(), 1)

    def test_the_api_lists_her_choices_for_her_and_no_one_else(self) -> None:
        CompanionFactory(owner=self.sheet, archetype=self.wolf, name="Fang")
        ultimate = UltimateTechniqueFactory(name="Hesk Unbound")
        KnownUltimateFactory(character=self.sheet, technique=ultimate)
        TechniqueManifestOptionFactory(technique=ultimate, being=self.hesk)
        self.web(
            self.mira, "manifest_set", technique_id=self.summon.pk, option_id=self.hesk_option.pk
        )

        response = self.api(self.account_of(self.mira)).get(
            CHOICES_URL, {"character_sheet": self.sheet.pk}
        )
        self.assertEqual(response.status_code, 200)
        by_name = {c["technique_name"]: c for c in response.json()["results"]}
        self.assertEqual(set(by_name), {"Summon", "Hesk Unbound"})
        summon = by_name["Summon"]
        self.assertEqual(summon["chosen_option_id"], self.hesk_option.pk)
        self.assertEqual(
            [(o["label"], o["available"]) for o in summon["options"]],
            [("Hesk (your patron)", True), ("Fang (your Wolf)", True)],
        )

        unnamed = self.api(self.account_of(self.mira)).get(CHOICES_URL)
        self.assertEqual(unnamed.status_code, 400)

        other = self.make_player("Hobb", room=self.room)
        response = self.api(self.account_of(other)).get(
            CHOICES_URL, {"character_sheet": self.sheet.pk}
        )
        self.assertEqual(response.json()["results"], [])
