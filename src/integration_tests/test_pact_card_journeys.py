"""Journeys for the pact card (#4341): a character reads her pact with a being on the
web and through ``pact`` on telnet, and renounces it on either.

The pact is built from factories with its condition at the first stage, not signed,
for isolation: the card and renouncing are what these journeys prove; signing is proven
in ``integration_tests.test_pacts_with_beings_journeys``.
"""

from __future__ import annotations

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from integration_tests.harness import JourneyCase
from world.conditions.factories import ConditionInstanceFactory
from world.conditions.services import advance_condition_severity
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

    def test_the_card_list_costs_the_same_queries_however_many_pacts(self) -> None:
        """The cards are built in one batch, not seven queries a pact (#4341 review)."""
        client = self.api(self.account_of(self.mira))

        def count() -> int:
            with CaptureQueriesContext(connection) as queries:
                response = client.get(CARDS_URL, {"character_sheet": self.sheet.pk})
            self.assertEqual(response.status_code, 200)
            return len(queries)

        count()
        one = count()
        for index in range(3):
            being = WorshippedBeingFactory(name=f"Other being {index}")
            condition = make_pact_condition(name=f"Other pact {index}")
            offer = PactOfferFactory(being=being, name=f"Other pact {index}", condition=condition)
            commitment = PactOfferCommitmentFactory(offer=offer, amount=8)
            standing = DevotionStandingFactory(
                character_sheet=self.sheet,
                being=being,
                valence=PatronageValence.PACT,
                established_at=timezone.now(),
            )
            pact = CharacterPactFactory(
                character_sheet=self.sheet, offer=offer, devotion_standing=standing
            )
            period = open_pact_period(pact, commitment)
            PactCreditFactory(period=period, source=PledgeCreditSource.DEED, credited=1)
        count()
        self.assertEqual(count(), one)

    def test_telnet_pact_shows_her_card_then_renounces_it(self) -> None:
        told = self.telnet(self.mira, "pact")
        self.assertIn("Hesk - 6 of 8 favor this period", told)
        self.assertIn("Stage: Sworn (severity 1; next at 11).", told)
        self.assertIn("You promised: Never refuse shelter", told)

        told = self.telnet(self.mira, "pact/renounce hesk")
        self.assertIn("You renounce your pact with Hesk.", told)
        # Renounced at Sworn, the first stage (the pact's benefit): it ends with the pact.
        self.assertIn(f"{self.offer.condition.name} is gone.", told)
        pact = CharacterPact.objects.get(pk=self.pact.pk)
        self.assertEqual(pact.dissolution_reason, CharacterPactEnding.RENOUNCED)
        self.assertIsNone(pact.condition_instance)

        told = self.telnet(self.mira, "pact")
        self.assertNotIn("Hesk", told)
        self.assertIn("No pacts stand.", told)

        told = self.telnet(self.mira, "pact/renounce hesk")
        self.assertIn("You hold no pact with that being.", told)

    def test_web_renounce_by_being_id(self) -> None:
        # At Strained the pact's cost eases out after the end; the card shows it ended.
        advance_condition_severity(self.pact.condition_instance, 14)
        result = self.web(self.mira, "pact_renounce", being_id=self.being.pk).detail
        self.assertTrue(result.success, result.message)
        self.assertIn("Strained eases by 10 each period until it is gone.", result.message)

        response = self.api(self.account_of(self.mira)).get(
            CARDS_URL, {"character_sheet": self.sheet.pk}
        )
        (card,) = response.json()["results"]
        self.assertFalse(card["is_active"])
        self.assertEqual((card["stage_name"], card["severity"]), ("Strained", 15))
        self.assertEqual(card["required"], 0)
