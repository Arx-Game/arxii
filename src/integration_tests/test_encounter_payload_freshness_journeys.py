"""Journeys for a combat payload that shows what changed since the last read (#4784).

Hobb and Ada fight on the causeway (Lane - Gate - Yard - Hall - Tower). Ada reads the
encounter over REST, something changes, and she reads it again in the same server
process. Each test reads twice so the second read meets the identity-mapped encounter,
room, sheet or bestiary row the first read loaded.

- Wren is added to the fight: Ada's next read lists her, and Wren's own first request on
  the fight is let through as a participant's, not refused as a stranger's.
- A wolf spawns at the Tower: Ada's next read lists it.
- A clash opens on the wolf and the wolf locks Hobb as its foil: Ada's next read shows
  both; once the clash resolves and the lock breaks, her next read shows neither.
- A builder adds a Bridge past the Tower: Ada's next read draws it, joined to the Tower.
- Hobb flees a fight that then ends: while it runs he is not listed; once it is over the
  aftermath lists him again, so he can reach his own digest.
- Hobb takes a new face: his account payload lists it on the next read.
- Staff add a phase to a bestiary entry: the bestiary list says it has phases.

Expected values come from the issue: a participant who joins, an opponent added mid-fight,
a new clash or engagement lock, or a builder's position or edge edit shows up in the next
payload without a server restart.
"""

from __future__ import annotations

from evennia_extensions.factories import AccountFactory
from integration_tests.test_npcs_close_in_journeys import _TheCauseway
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import connect_positions
from world.combat.constants import ClashStatus, EngagementLockStatus, ParticipantStatus
from world.combat.factories import (
    ClashFactory,
    CreaturePhaseTemplateFactory,
    CreatureTemplateFactory,
    EngagementLockFactory,
)
from world.combat.services import add_participant
from world.scenes.constants import PersonaType, RoundStatus
from world.scenes.services import create_persona


class _AdaWatchesTheCauseway(_TheCauseway):
    def setUp(self) -> None:
        super().setUp()
        self.hobb = self.fighter("Hobb", at=self.gate)
        self.ada = self.fighter("Ada", at=self.hall)

    def ada_reads(self) -> dict[str, object]:
        response = self.api(self.account_of(self.ada)).get(f"/api/combat/{self.encounter.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    @staticmethod
    def fighters(body: dict[str, object]) -> list[str]:
        return sorted(row["character_name"] for row in body["participants"])


class ALateJoinerIsInTheFight(_AdaWatchesTheCauseway):
    def test_wren_is_listed_and_her_first_request_is_a_participants(self) -> None:
        self.assertEqual(self.fighters(self.ada_reads()), ["Ada", "Hobb"])

        wren = self.make_player("Wren", room=self.room)
        add_participant(self.encounter, wren.sheet_data)

        self.assertEqual(self.fighters(self.ada_reads()), ["Ada", "Hobb", "Wren"])
        response = self.api(self.account_of(wren)).get(
            f"/api/combat/{self.encounter.pk}/my_action/"
        )
        self.assertEqual(response.status_code, 200, response.content)


class AnEnemyJoinsMidFight(_AdaWatchesTheCauseway):
    def test_the_wolf_is_listed(self) -> None:
        self.assertEqual(self.ada_reads()["opponents"], [])

        self.creature("Grey Wolf", at=self.tower)

        names = [row["name"] for row in self.ada_reads()["opponents"]]
        self.assertEqual(names, ["Grey Wolf"])


class AClashAndAFoil(_AdaWatchesTheCauseway):
    def test_both_show_while_active_and_go_once_ended(self) -> None:
        wolf = self.creature("Grey Wolf", at=self.tower)
        body = self.ada_reads()
        self.assertEqual((body["clashes"], body["engagement_locks"]), ([], []))

        clash = ClashFactory(encounter=self.encounter, npc_opponent=wolf)
        lock = EngagementLockFactory(
            encounter=self.encounter, opponent=wolf, participant=self.participant(self.hobb)
        )

        body = self.ada_reads()
        self.assertEqual([row["id"] for row in body["clashes"]], [clash.pk])
        self.assertEqual([row["id"] for row in body["engagement_locks"]], [lock.pk])

        clash.status = ClashStatus.RESOLVED
        clash.save()
        lock.status = EngagementLockStatus.BROKEN
        lock.save()

        body = self.ada_reads()
        self.assertEqual((body["clashes"], body["engagement_locks"]), ([], []))


class ABuilderAddsAPlace(_AdaWatchesTheCauseway):
    def test_the_bridge_is_drawn_and_joined_to_the_tower(self) -> None:
        names = {node["name"] for node in self.ada_reads()["position_nodes"]}
        self.assertNotIn("Bridge", names)

        bridge = PositionFactory(room=self.room, name="Bridge")
        connect_positions(self.tower, bridge)

        body = self.ada_reads()
        self.assertIn("Bridge", {node["name"] for node in body["position_nodes"]})
        adjacency = {
            row["position_id"]: row["adjacent_position_ids"] for row in body["position_adjacency"]
        }
        self.assertIn(bridge.pk, adjacency[self.tower.pk])


class AFledFighterInTheAftermath(_AdaWatchesTheCauseway):
    def test_hobb_is_listed_again_once_the_fight_is_over(self) -> None:
        self.assertEqual(self.fighters(self.ada_reads()), ["Ada", "Hobb"])

        hobb = self.participant(self.hobb)
        hobb.status = ParticipantStatus.FLED
        hobb.save()
        self.assertEqual(self.fighters(self.ada_reads()), ["Ada"])

        self.encounter.status = RoundStatus.COMPLETED
        self.encounter.save()
        self.assertEqual(self.fighters(self.ada_reads()), ["Ada", "Hobb"])


class ANewFaceOnTheAccount(_AdaWatchesTheCauseway):
    def faces(self) -> list[str]:
        response = self.api(self.account_of(self.hobb)).get("/api/user/")
        self.assertEqual(response.status_code, 200, response.content)
        (entry,) = response.json()["available_characters"]
        return sorted(persona["name"] for persona in entry["personas"])

    def test_the_grey_hood_is_listed(self) -> None:
        self.assertNotIn("The Grey Hood", self.faces())

        create_persona(
            self.hobb.sheet_data, name="The Grey Hood", persona_type=PersonaType.ESTABLISHED
        )

        self.assertIn("The Grey Hood", self.faces())


class ABestiaryEntryGainsAPhase(_TheCauseway):
    def test_the_list_says_it_has_phases(self) -> None:
        staff = AccountFactory(username="bestiary_staff", is_staff=True)
        template = CreatureTemplateFactory(name="Bog Troll")

        def has_phases() -> bool:
            response = self.api(staff).get("/api/combat/creature-templates/?search=Bog")
            self.assertEqual(response.status_code, 200, response.content)
            (row,) = response.json()["results"]
            return row["has_phases"]

        self.assertFalse(has_phases())
        CreaturePhaseTemplateFactory(creature_template=template, phase_number=1)
        self.assertTrue(has_phases())
