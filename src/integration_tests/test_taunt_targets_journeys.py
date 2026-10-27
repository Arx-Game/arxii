"""Journeys for taunting by name (#4737): a foe draws aggro, an ally is goaded.

Mira and Tomas are played fighters in one declaring round-1 encounter in "The Road", against
a Bandit Captain. `combat taunt <name>` takes either kind of name through the command
handler and declares the same TAUNT maneuver, aimed at the right target. The REST endpoint
and the web dispatch take the same two kinds of target, exactly one at a time.
"""

from __future__ import annotations

from rest_framework import status as http_status

from integration_tests.harness import JourneyCase
from world.combat.constants import CombatManeuver, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatRoundAction
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals

ONE_TARGET_MESSAGE = "Name exactly one target to taunt: an opponent or a participant."


class TauntingByName(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.road = self.make_room("The Road")
        self.mira = self.make_player("Mira", room=self.road)
        self.tomas = self.make_player("Tomas", room=self.road)
        for player in (self.mira, self.tomas):
            CharacterVitals.objects.create(
                character_sheet=player.sheet_data, health=100, max_health=100, base_max_health=100
            )
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.road
        )
        self.mira_seat = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.mira.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )
        self.tomas_seat = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.tomas.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )
        self.captain = CombatOpponentFactory(encounter=self.encounter, name="Bandit Captain")

    def _taunt_action(self) -> CombatRoundAction | None:
        return CombatRoundAction.objects.filter(
            participant=self.mira_seat, round_number=1, maneuver=CombatManeuver.TAUNT
        ).first()

    def test_combat_taunt_ally_by_name_declares(self) -> None:
        out = self.telnet(self.mira, "combat taunt Tomas")

        self.assertIn("You taunt your ally.", out)
        action = self._taunt_action()
        self.assertEqual(action.focused_ally_target, self.tomas_seat)
        self.assertIsNone(action.focused_opponent_target)

    def test_combat_taunt_opponent_still_works(self) -> None:
        out = self.telnet(self.mira, "combat taunt Bandit Captain")

        self.assertIn("You taunt your foe.", out)
        action = self._taunt_action()
        self.assertEqual(action.focused_opponent_target, self.captain)
        self.assertIsNone(action.focused_ally_target)

    def test_taunting_an_unknown_name_says_who_can_be_taunted(self) -> None:
        out = self.telnet(self.mira, "combat taunt Nobody")

        self.assertIn("No active ally or opponent named 'Nobody' in this encounter.", out)
        self.assertIsNone(self._taunt_action())

    def test_taunt_with_no_name_gives_the_usage(self) -> None:
        out = self.telnet(self.mira, "combat taunt")

        self.assertIn("Usage: combat taunt <an opponent or ally>.", out)
        self.assertIsNone(self._taunt_action())

    def test_taunting_yourself_is_refused_in_plain_words(self) -> None:
        out = self.telnet(self.mira, "combat taunt Mira")

        self.assertIn("Cannot taunt yourself.", out)
        self.assertIsNone(self._taunt_action())

    def test_the_web_dispatch_takes_an_ally_too(self) -> None:
        result = self.web(self.mira, "combat_taunt", ally_participant_id=self.tomas_seat.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(self._taunt_action().focused_ally_target, self.tomas_seat)

    def test_naming_both_targets_is_refused(self) -> None:
        result = self.web(
            self.mira,
            "combat_taunt",
            ally_participant_id=self.tomas_seat.pk,
            opponent_id=self.captain.pk,
        )

        self.assertFalse(result.detail.success)
        self.assertEqual(result.detail.message, "Name one target to taunt: an opponent or an ally.")
        self.assertIsNone(self._taunt_action())

    # -- the REST endpoint ----------------------------------------------------

    def _post_taunt(self, body: dict) -> object:
        client = self.api(self.account_of(self.mira))
        return client.post(f"/api/combat/{self.encounter.pk}/taunt/", body, format="json")

    def test_the_rest_endpoint_takes_an_ally(self) -> None:
        response = self._post_taunt({"participant_id": self.tomas_seat.pk})

        self.assertEqual(response.status_code, http_status.HTTP_200_OK, response.content)
        action = self._taunt_action()
        self.assertEqual(action.focused_ally_target, self.tomas_seat)
        self.assertIsNone(action.focused_opponent_target)

    def test_the_rest_endpoint_takes_an_opponent(self) -> None:
        response = self._post_taunt({"opponent_id": self.captain.pk})

        self.assertEqual(response.status_code, http_status.HTTP_200_OK, response.content)
        action = self._taunt_action()
        self.assertEqual(action.focused_opponent_target, self.captain)
        self.assertIsNone(action.focused_ally_target)

    def test_the_rest_endpoint_refuses_two_targets_in_plain_words(self) -> None:
        response = self._post_taunt(
            {"participant_id": self.tomas_seat.pk, "opponent_id": self.captain.pk}
        )

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {"non_field_errors": [ONE_TARGET_MESSAGE]})
        self.assertIsNone(self._taunt_action())

    def test_the_rest_endpoint_refuses_no_target_in_plain_words(self) -> None:
        response = self._post_taunt({})

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json(), {"non_field_errors": [ONE_TARGET_MESSAGE]})
        self.assertIsNone(self._taunt_action())

    def test_taunting_yourself_over_rest_is_a_plain_400(self) -> None:
        response = self._post_taunt({"participant_id": self.mira_seat.pk})

        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("yourself", response.content.decode())
        self.assertIsNone(self._taunt_action())

    def test_a_participant_of_another_encounter_is_a_404(self) -> None:
        stranger = CombatParticipantFactory(
            encounter=CombatEncounterFactory(), status=ParticipantStatus.ACTIVE
        )

        response = self._post_taunt({"participant_id": stranger.pk})

        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)
        self.assertIsNone(self._taunt_action())
