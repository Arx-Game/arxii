"""Journeys for the pact card (#4341): a character reads her pact with a being on the
web and through ``pact`` on telnet, and renounces it on either.

The pact is built from factories with its condition at the first stage, not signed:
signing applies the condition through a PostgreSQL ``DISTINCT ON`` (ADR-0012), and the
card and renouncing are what these journeys prove. The sign path has its own tests in
``world.pacts.tests``.
"""

from __future__ import annotations

from django.utils import timezone

from integration_tests.harness import JourneyCase
from world.conditions.factories import ConditionInstanceFactory
from world.pacts.constants import CharacterPactCommitmentKind, CharacterPactEnding
from world.pacts.factories import (
    CharacterPactFactory,
    PactCreditFactory,
    PactOfferCommitmentFactory,
    PactOfferFactory,
    make_pact_condition,
)
from world.pacts.models import CharacterPact
from world.pacts.services import open_pact_period
from world.worship.constants import PledgeCreditSource
from world.worship.factories import DevotionStandingFactory, WorshippedBeingFactory
from world.worship.models import PatronageValence

CARDS_URL = "/api/pacts/cards/"


class PactCardJourneys(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Hollow")
        self.mira = self.make_player("Mira", room=self.room)
        self.sheet = self.mira.sheet_data
        self.being = WorshippedBeingFactory(name="Hesk")
        condition = make_pact_condition()
        self.offer = PactOfferFactory(being=self.being, name="Hesk pact", condition=condition)
        commitment = PactOfferCommitmentFactory(offer=self.offer, amount=8)
        PactOfferCommitmentFactory(
            offer=self.offer,
            kind=CharacterPactCommitmentKind.CUSTOM,
            amount=0,
            notes="Never refuse shelter to one who asks in Hesk's name.",
        )
        sworn = condition.stages.get(stage_order=1)
        instance = ConditionInstanceFactory(
            target=self.mira, condition=condition, current_stage=sworn, severity=1
        )
        standing = DevotionStandingFactory(
            character_sheet=self.sheet,
            being=self.being,
            valence=PatronageValence.PACT,
            established_at=timezone.now(),
        )
        self.pact = CharacterPactFactory(
            character_sheet=self.sheet,
            offer=self.offer,
            devotion_standing=standing,
            condition_instance=instance,
        )
        period = open_pact_period(self.pact, commitment)
        PactCreditFactory(period=period, source=PledgeCreditSource.DEED, credited=4)
        PactCreditFactory(period=period, source=PledgeCreditSource.RITE, credited=2)
        project = period.project
        project.current_progress = 6
        project.save(update_fields=["current_progress"])

    def test_the_holder_reads_her_card_and_no_one_else_does(self) -> None:
        response = self.api(self.account_of(self.mira)).get(
            CARDS_URL, {"character_sheet": self.sheet.pk}
        )
        self.assertEqual(response.status_code, 200)
        (card,) = response.json()["results"]
        self.assertEqual(card["being_name"], "Hesk")
        self.assertEqual((card["earned"], card["required"]), (6, 8))
        self.assertEqual(
            [(row["label"], row["favor"]) for row in card["sources"]],
            [
                ("Deeds: resonances Hesk favors, from missions and scenes", 4),
                ("Hesk's rite, which you performed", 2),
            ],
        )
        self.assertEqual(
            (card["stage_name"], card["severity"], card["next_stage_threshold"]),
            ("Sworn", 1, 11),
        )
        self.assertEqual(card["promises"], ["Never refuse shelter to one who asks in Hesk's name."])
        self.assertTrue(card["is_active"])

        other = self.make_player("Tobin", room=self.room)
        response = self.api(self.account_of(other)).get(
            CARDS_URL, {"character_sheet": self.sheet.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])

        staff = self.account_of(other)
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])
        response = self.api(staff).get(CARDS_URL, {"character_sheet": self.sheet.pk})
        self.assertEqual(len(response.json()["results"]), 1)

        self.assertEqual(self.api().get(CARDS_URL).status_code, 403)

    def test_telnet_pact_shows_her_card_then_renounces_it(self) -> None:
        told = self.telnet(self.mira, "pact")
        self.assertIn("Hesk - 6 of 8 favor this period", told)
        self.assertIn("Stage: Sworn (severity 1; next at 11).", told)
        self.assertIn("You promised: Never refuse shelter", told)
        self.assertIn("No pacts stand.", told)

        told = self.telnet(self.mira, "pact/renounce hesk")
        self.assertIn("You renounce your pact with Hesk.", told)
        pact = CharacterPact.objects.get(pk=self.pact.pk)
        self.assertEqual(pact.dissolution_reason, CharacterPactEnding.RENOUNCED)

        told = self.telnet(self.mira, "pact")
        self.assertIn("Hesk (ended). Sworn eases by 10 each period until it is gone.", told)

        told = self.telnet(self.mira, "pact/renounce hesk")
        self.assertIn("You hold no pact with that being.", told)

    def test_web_renounce_by_being_id(self) -> None:
        result = self.web(self.mira, "pact_renounce", being_id=self.being.pk).detail
        self.assertTrue(result.success, result.message)
        self.assertIn("Sworn eases by 10 each period until it is gone.", result.message)

        response = self.api(self.account_of(self.mira)).get(
            CARDS_URL, {"character_sheet": self.sheet.pk}
        )
        (card,) = response.json()["results"]
        self.assertFalse(card["is_active"])
        self.assertEqual(card["required"], 0)
