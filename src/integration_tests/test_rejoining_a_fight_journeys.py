"""Journeys for coming back to a fight you fled or left (#4794).

Mira flees an Open Encounter (``combat flee``, the round rolls it, the roll forced to a
clean escape) or walks out between rounds (``combat leave``), then types ``combat join``.
She is told she joins, and she is back on the same participant row, active, with a
combat engagement on this encounter again. Before the fix the join inserted a second row
and raised on the one-row-per-fighter constraint.

Expected values are the rows built here and the action's own join line.
"""

from __future__ import annotations

from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import EncounterType, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatParticipant, FleeConfig
from world.combat.services import resolve_round
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckOutcomeFactory
from world.vitals.models import CharacterVitals


class _MiraInAnOpenFight(JourneyCase):
    """Mira and Tomas in an Open Encounter with a Bandit Captain on the Road."""

    def setUp(self) -> None:
        super().setUp()
        self.road = self.make_room("The Road")
        self.mira = self.make_player("Mira", room=self.road)
        self.tomas = self.make_player("Tomas", room=self.road)
        for fighter in (self.mira, self.tomas):
            CharacterVitals.objects.create(
                character_sheet=fighter.sheet_data, health=100, max_health=100, base_max_health=100
            )
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
            room=self.road,
            encounter_type=EncounterType.OPEN_ENCOUNTER,
        )
        self.seat = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.mira.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )
        # Tomas stays in, so the fight is still running when Mira comes back.
        CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.tomas.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )
        CombatOpponentFactory(encounter=self.encounter, name="Bandit Captain")
        self.watch(self.mira)

    def assert_back_in_the_fight(self, told: str) -> None:
        self.assertIn("You join the fight.", told)
        rows = CombatParticipant.objects.filter(
            encounter=self.encounter, character_sheet=self.mira.sheet_data
        )
        self.assertEqual(list(rows.values_list("pk", "status")), [(self.seat.pk, "active")])
        self.assertTrue(
            CharacterEngagement.objects.filter(
                character=self.mira.sheet_data,
                engagement_type=EngagementType.COMBAT,
                source_id=self.encounter.pk,
            ).exists()
        )


class MiraFleesThenComesBack(_MiraInAnOpenFight):
    def test_she_rejoins_on_her_own_row(self) -> None:
        flee_check = CheckTypeFactory(name="Run for it")
        FleeConfig.objects.filter(pk=1).delete()
        FleeConfig.objects.create(pk=1, check_type=flee_check)
        escape = CheckOutcomeFactory(name="Clean getaway", success_level=2)

        self.telnet(self.mira, "combat flee")
        with force_check_outcome(escape):
            resolve_round(self.encounter)

        self.seat.refresh_from_db()
        self.assertEqual(self.seat.status, ParticipantStatus.FLED)
        self.assertFalse(
            CharacterEngagement.objects.filter(
                character=self.mira.sheet_data, engagement_type=EngagementType.COMBAT
            ).exists()
        )

        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.status, RoundStatus.BETWEEN_ROUNDS)
        told = self.telnet(self.mira, "combat join")

        self.assert_back_in_the_fight(told)


class MiraWalksOutThenComesBack(_MiraInAnOpenFight):
    def test_she_rejoins_on_her_own_row(self) -> None:
        self.encounter.status = RoundStatus.BETWEEN_ROUNDS
        self.encounter.save(update_fields=["status"])

        self.telnet(self.mira, "combat leave")
        self.seat.refresh_from_db()
        self.assertEqual(self.seat.status, ParticipantStatus.REMOVED)

        told = self.telnet(self.mira, "combat join")

        self.assert_back_in_the_fight(told)

    def test_joining_twice_is_still_refused(self) -> None:
        told = self.telnet(self.mira, "combat join")

        self.assertIn("Already participating in this encounter.", told)
