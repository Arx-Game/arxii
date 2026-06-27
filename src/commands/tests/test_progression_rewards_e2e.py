"""Full telnet journey (#1348): a player claims kudos, votes, claims a random
scene, declares a path intent, and rests — all via telnet commands converging on
action.run(), the same seam the web uses."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from commands.fatigue import CmdRest
from commands.progression_rewards import CmdKudos, CmdPathIntent, CmdRandomScene, CmdVote
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import PathFactory
from world.fatigue.models import FatiguePool
from world.fatigue.services import get_or_create_fatigue_pool
from world.progression.factories import (
    KudosClaimCategoryFactory,
    KudosPointsDataFactory,
    RandomSceneTargetFactory,
)
from world.progression.models import KudosPointsData, RandomSceneTarget, WeeklyVote
from world.progression.models.path_intent import PathIntent
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import InteractionFactory


def _player():
    sheet = CharacterSheetFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(roster_entry=entry)
    return sheet, sheet.character, tenure.player_data.account


class ProgressionRewardsJourneyTest(TestCase):
    def setUp(self) -> None:
        for model in (
            KudosPointsData,
            RandomSceneTarget,
            WeeklyVote,
            PathIntent,
            FatiguePool,
            ActionPointPool,
        ):
            model.flush_instance_cache()
        from evennia import create_object

        self.sheet, self.character, self.account = _player()
        self.other_sheet, self.other_char, self.other_account = _player()
        self.room = create_object("typeclasses.rooms.Room", key="JourneyHome", nohome=True)
        self.character.location = self.room
        self.character.home = self.room
        self.character.save()
        self.character.msg = MagicMock()

    def _run(self, cmd_cls, args=""):
        cmd = cmd_cls()
        cmd.caller = self.character
        cmd.args = args
        cmd.raw_string = f"{cmd_cls.key} {args}".strip()
        cmd.func()

    def test_full_journey(self) -> None:
        # 1. Claim kudos → XP
        KudosPointsDataFactory(account=self.account, total_earned=100, total_claimed=0)
        category = KudosClaimCategoryFactory(kudos_cost=10, reward_amount=1, is_active=True)
        self._run(CmdKudos, f"claim {category.pk} 50")
        self.account.refresh_from_db()
        self.assertEqual(KudosPointsData.objects.get(account=self.account).total_claimed, 50)

        # 2. Cast a vote on the other player's pose
        interaction = InteractionFactory(persona=self.other_sheet.primary_persona)
        self._run(CmdVote, f"interaction {interaction.pk}")
        self.assertTrue(
            WeeklyVote.objects.filter(voter=self.account, target_id=interaction.pk).exists()
        )

        # 3. Claim a random scene (patch the shared-scene evidence check)
        target = RandomSceneTargetFactory(
            account=self.account, target_persona=self.other_sheet.primary_persona
        )
        with patch(
            "world.progression.services.random_scene.validate_random_scene_claim",
            return_value=True,
        ):
            self._run(CmdRandomScene, f"claim {target.pk}")
        target.refresh_from_db()
        self.assertTrue(target.claimed)

        # 4. Declare a path intent
        path = PathFactory(name="Champion")
        self._run(CmdPathIntent, str(path.pk))
        self.assertTrue(PathIntent.objects.filter(character_sheet=self.sheet).exists())

        # 5. Rest for Well Rested
        ActionPointPool.objects.create(character=self.character, current=200, maximum=200)
        self._run(CmdRest)
        self.assertTrue(get_or_create_fatigue_pool(self.sheet).well_rested)
