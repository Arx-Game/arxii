"""What the story journeys cannot stage of the GM story actions (#1495, #1770).

Every player and GM path of ``complete_story``, ``resolve_episode``, ``promote_episode``,
``mark_beat`` and ``declare_stakes`` is typed or dispatched in
``integration_tests/test_running_a_story_journeys.py`` (``RunningAStory``) and
``integration_tests/test_sharing_a_story_journeys.py`` (``DeclaringTheStakes``). What
stays here: the boundary refusal, which only a patched boundary report can produce (no
authored boundary refuses in a fixture), and the party-sheet helper, which answers a
question (who is present) no reply reads back directly.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from actions.definitions.gm_stories import DeclareStakesAction, _present_participant_sheets
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import SceneFactory
from world.scenes.interaction_services import invalidate_active_scene_cache
from world.societies.constants import RenownRisk
from world.stories.constants import StakeSeverity, StoryScope
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    EpisodeSceneFactory,
    StakeFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.models import StakeContractActivation
from world.stories.types import StakeBoundaryReport, StoryStatus


def _make_room(label: str = "Room") -> object:
    return ObjectDBFactory(db_key=label, db_typeclass_path="typeclasses.rooms.Room")


def _make_actor_with_account(db_key: str, room: object, account: object) -> tuple[object, object]:
    """Create a PC in *room* whose ``active_account`` is *account*."""
    char = CharacterFactory(db_key=db_key, location=room)
    sheet = CharacterSheetFactory(character=char)
    entry = RosterTenureFactory(
        roster_entry__character_sheet=sheet,
        player_data__account=account,
        end_date=None,
    ).roster_entry
    return char, entry.character_sheet


class DeclareStakesEdgeTests(TestCase):
    """The two edges of ``DeclareStakesAction`` a journey cannot reach."""

    def setUp(self) -> None:
        self.room = _make_room("GMStoryRoom")
        self.lead_gm_account = AccountFactory(username="storylead")
        self.lead_gm_profile = GMProfileFactory(account=self.lead_gm_account)
        self.gm_table = GMTableFactory(gm=self.lead_gm_profile)
        self.lead_gm_actor, self.lead_gm_sheet = _make_actor_with_account(
            "story_lead_actor", self.room, self.lead_gm_account
        )
        self.player_account = AccountFactory(username="storyplayer")
        self.player_actor, _ = _make_actor_with_account(
            "story_player_actor", self.room, self.player_account
        )
        self.story = StoryFactory(
            owners=[self.lead_gm_account],
            scope=StoryScope.CHARACTER,
            primary_table=self.gm_table,
            status=StoryStatus.ACTIVE,
        )
        self.chapter = ChapterFactory(story=self.story)
        self.ep1 = EpisodeFactory(chapter=self.chapter, order=1)
        StoryProgressFactory(
            story=self.story,
            character_sheet=self.lead_gm_sheet,
            current_episode=self.ep1,
            is_active=True,
        )
        invalidate_active_scene_cache(self.room)
        self.scene = SceneFactory(
            room=self.room, participants=[self.player_account, self.lead_gm_account]
        )
        self.beat = BeatFactory(episode=self.ep1, risk=RenownRisk.HIGH, target_level=4)
        EpisodeSceneFactory(episode=self.ep1, scene=self.scene)
        StakeFactory(
            beat=self.beat, severity=StakeSeverity.DIRE, player_summary="The healer NPC may die."
        )

    def test_blocked_boundary_returns_generic_failure(self) -> None:
        """A refused boundary never leaks its private reason (ADR-0033)."""
        blocked = StakeBoundaryReport(
            allowed=False, blocked_reason_private="player X never wagers healers"
        )
        with mock.patch(
            "world.stories.services.boundaries.check_stake_boundaries", return_value=blocked
        ):
            result = DeclareStakesAction().run(self.lead_gm_actor, beat_id=self.beat.pk)

        self.assertFalse(result.success)
        self.assertNotIn("healers", result.message)
        self.assertFalse(StakeContractActivation.objects.filter(beat=self.beat).exists())

    def test_off_scene_alts_do_not_join_the_party(self) -> None:
        """Party sheets come from characters PRESENT in the scene's room only."""
        elsewhere = _make_room("Elsewhere")
        alt_char = CharacterFactory(db_key="off_scene_alt", location=elsewhere)
        alt_sheet = CharacterSheetFactory(character=alt_char)
        RosterTenureFactory(
            roster_entry__character_sheet=alt_sheet,
            player_data=self.player_account.player_data,
            end_date=None,
        )

        sheets = _present_participant_sheets(self.scene)

        self.assertNotIn(alt_sheet, sheets)
        present_ids = {obj.pk for obj in self.scene.room.contents}
        self.assertTrue(sheets)
        for sheet in sheets:
            self.assertIn(sheet.character_id, present_ids)
