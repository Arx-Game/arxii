"""Journeys for playing the cast (#4418): a GM or Guide plays a major NPC in a scene."""

from __future__ import annotations

from rest_framework import status

from actions.factories import ActionTemplateFactory
from integration_tests.harness import JourneyCase
from world.battles.constants import BattleSideRole
from world.battles.resolution import select_surrounded_terminal_pool
from world.battles.services import add_place, add_side, create_battle, enlist_participant
from world.checks.factories import CheckTypeFactory
from world.progression.models import WeeklySocialEngagement
from world.roster.factories import RosterFactory
from world.roster.models.choices import RosterType
from world.scenes.factories import SceneFactory
from world.vitals.constants import POOL_SURROUNDED_TERMINAL_ENEMY
from world.vitals.factories import ensure_surrounded_content


def persona_of(character):
    return character.sheet_data.primary_persona


class APlayedNpcIsAnNpc(JourneyCase):
    """Hobb is a major NPC a GM plays; Ysmay is a player character in the scene."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        # Hobb is held by an account and puppeted, as a GM plays a major NPC.
        entry = self.hobb.sheet_data.roster_entry
        entry.move_to_roster(RosterFactory(roster_type=RosterType.NPC))
        self.scene = SceneFactory(room=self.room)
        ActionTemplateFactory(name="Persuade", check_type=CheckTypeFactory(name="Persuasion"))

    def test_persuade_lands_at_once_on_a_played_npc(self) -> None:
        response = self.api(self.account_of(self.ysmay)).post(
            "/api/action-requests/",
            {
                "scene": self.scene.pk,
                "initiator_persona": persona_of(self.ysmay).pk,
                "target_persona": persona_of(self.hobb).pk,
                "action_key": "persuade",
            },
            format="json",
        )
        self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))
        self.assertEqual(response.json()["status"], "resolved")
        self.assertFalse(
            WeeklySocialEngagement.objects.filter(account=self.account_of(self.hobb)).exists()
        )

    def test_battle_counts_no_pc_opponent_for_a_played_npc(self) -> None:
        content = ensure_surrounded_content()
        battle = create_battle(name="The Lantern Riot")
        attackers = add_side(battle=battle, role=BattleSideRole.ATTACKER)
        defenders = add_side(battle=battle, role=BattleSideRole.DEFENDER)
        place = add_place(battle=battle, name="The Gates")
        isolated = enlist_participant(
            battle=battle,
            character_sheet=self.ysmay.sheet_data,
            side=attackers,
            place=place,
        )
        enlist_participant(
            battle=battle,
            character_sheet=self.hobb.sheet_data,
            side=defenders,
            place=place,
        )
        pool = select_surrounded_terminal_pool(battle=battle, participant=isolated)
        self.assertEqual(pool.name, POOL_SURROUNDED_TERMINAL_ENEMY)
        self.assertEqual(pool, content["pools"]["surrounded_terminal_enemy"])
