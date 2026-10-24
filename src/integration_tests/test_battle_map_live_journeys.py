"""Journeys for a battle map that follows the fight live (#4644).

Hobb and Ada fight on the causeway (Lane - Gate - Yard - Hall - Tower). Ada watches; her
battle map reads positions from the REST encounter and refetches it when her client is
sent a ``combat_encounter_state`` ping for that encounter.

- A wolf at the Tower runs to the Yard during the round. Once the round commits, Ada is
  sent one ping for this encounter (not one per move), and the encounter she then reads
  over REST has the wolf at the Yard.
- Hobb steps from the Gate to the Lane in the web client while the round is declared.
  Once that commits, Ada is sent one ping, and the encounter she reads has Hobb at the Lane.
- Nothing is sent before the commit: a refetch then would read the old positions. The
  wolf's run is a move inside the resolving round, so its single ping also shows that a
  move mid-round adds none of its own.
- The round that ends the fight still sends one, so the map shows how it ended.
- An effect that shoves Ada while the round is declared sends one ping too: every move goes
  through the one position writer.
- Once the fight is over, a step sends nothing.

Expected values come from the issue: every open battle map shows a move as soon as it is
saved, the same as a reload would.
"""

from __future__ import annotations

from integration_tests.test_npcs_close_in_journeys import _TheCauseway
from world.areas.positioning.services import force_move_to_position
from world.combat.factories import CombatOpponentFactory
from world.combat.models import CombatEncounter
from world.scenes.constants import RoundStatus

PING = "combat_encounter_state"


class _TwoOnTheCauseway(_TheCauseway):
    def setUp(self) -> None:
        super().setUp()
        self.hobb = self.fighter("Hobb", at=self.gate)
        self.ada = self.fighter("Ada", at=self.hall)

    def pings(self, character) -> list[dict[str, object]]:
        return [
            kwargs[PING][1] for _args, kwargs in self.mailbox(character).calls if PING in kwargs
        ]

    def positions_ada_reads(self) -> dict[str, str | None]:
        """Who stands where, by name, in the encounter Ada's map refetches over REST."""
        response = self.api(self.account_of(self.ada)).get(f"/api/combat/{self.encounter.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        where: dict[str, str | None] = {}
        for row in body["participants"]:
            spot = row["current_position"]
            where[row["character_name"]] = spot["name"] if spot else None
        for row in body["opponents"]:
            spot = row["current_position"]
            where[row["name"]] = spot["name"] if spot else None
        return where


class AWatcherSeesTheEnemyArrive(_TwoOnTheCauseway):
    def test_one_ping_after_the_round_commits_and_the_wolf_is_where_it_ran(self) -> None:
        self.creature("Grey Wolf", at=self.tower, hops=2)
        self.mailbox(self.ada).calls.clear()

        with self.captureOnCommitCallbacks(execute=False) as pending:
            self.resolve()
        self.assertEqual(self.pings(self.ada), [], "a ping before the commit reads old positions")
        self.assertIn(
            "Grey Wolf moves to Yard.",
            self.mailbox(self.ada).rows,
        )

        for callback in pending:
            callback()
        self.assertEqual(
            self.pings(self.ada),
            [{"encounter_id": self.encounter.pk, "round_number": 1}],
        )
        self.assertEqual(self.positions_ada_reads()["Grey Wolf"], "Yard")


class AWatcherSeesAFriendStep(_TwoOnTheCauseway):
    def setUp(self) -> None:
        super().setUp()
        # Someone to fight, who never acts.
        CombatOpponentFactory(encounter=self.encounter, name="Watcher", threat_pool=None)

    def test_one_ping_after_a_web_move_commits_and_hobb_is_at_the_lane(self) -> None:
        self.mailbox(self.ada).calls.clear()

        with self.captureOnCommitCallbacks(execute=False) as pending:
            result = self.web(self.hobb, "move_to_position", position_id=self.lane.pk).detail
        self.assertTrue(result.success, result.message)
        self.assertEqual(self.pings(self.ada), [])

        for callback in pending:
            callback()
        self.assertEqual(
            self.pings(self.ada),
            [{"encounter_id": self.encounter.pk, "round_number": 1}],
        )
        self.assertEqual(self.positions_ada_reads()["Hobb"], "Lane")


class TheLastRound(_TwoOnTheCauseway):
    def test_the_round_that_ends_the_fight_still_pings_once(self) -> None:
        # Nobody left to fight, so this round ends it.
        self.mailbox(self.ada).calls.clear()

        with self.captureOnCommitCallbacks(execute=True):
            self.resolve()

        self.assertEqual(
            CombatEncounter.objects.get(pk=self.encounter.pk).status, RoundStatus.COMPLETED
        )
        self.assertEqual(
            self.pings(self.ada),
            [{"encounter_id": self.encounter.pk, "round_number": 1}],
        )


class AfterTheFight(_TwoOnTheCauseway):
    def test_a_step_after_the_fight_sends_nothing(self) -> None:
        self.encounter.status = RoundStatus.COMPLETED
        self.encounter.save(update_fields=["status"])
        self.mailbox(self.ada).calls.clear()

        with self.captureOnCommitCallbacks(execute=True):
            result = self.web(self.hobb, "move_to_position", position_id=self.lane.pk).detail

        self.assertTrue(result.success, result.message)
        self.assertEqual(self.pings(self.ada), [])


class AShoveWhileDeclaring(_TwoOnTheCauseway):
    def test_a_forced_move_outside_the_round_pings_once(self) -> None:
        self.mailbox(self.ada).calls.clear()

        with self.captureOnCommitCallbacks(execute=True):
            force_move_to_position(self.ada, self.gate)

        self.assertEqual(
            self.pings(self.ada),
            [{"encounter_id": self.encounter.pk, "round_number": 1}],
        )
