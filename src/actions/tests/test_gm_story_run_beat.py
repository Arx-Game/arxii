"""Tests for the #3425 session-prep run actions: RunBeatAction, GMListRunnableBeatsAction.

Journey (spec's registry dispatch test seam): author a beat with 2 opponent
lines (one templated boss w/ phases) + 1 situation line; a GM dispatches
``run_beat`` in a live scene; assert CombatEncounter created with
``story_beat=beat`` and mapped ``risk_level``, opponents spawned (count
honored, phases cloned), a SituationInstance placed, and
``Scene.running_beat=beat``. Refusals: non-scene-GM; a beat of a story the GM
doesn't run; TASK/REQUIREMENT kind; re-run while already running (idempotent).
"""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.gm_story import GMListRunnableBeatsAction, RunBeatAction
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import OpponentTier
from world.combat.factories import (
    CreaturePhaseTemplateFactory,
    CreatureTemplateFactory,
    seed_scaling_defaults,
)
from world.combat.models import BossPhase, CombatEncounter, CombatOpponent
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.mechanics.factories import SituationTemplateFactory
from world.mechanics.models import SituationInstance
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.societies.constants import RenownRisk
from world.stories.constants import BeatKind, StoryScope
from world.stories.factories import (
    BeatFactory,
    BeatOpponentLineFactory,
    BeatStagedTemplateFactory,
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.types import StoryStatus


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


class RunBeatActionTestBase(TestCase):
    """Shared fixture: room, scene, Lead GM (JUNIOR+), a story they run."""

    def setUp(self) -> None:
        seed_scaling_defaults()
        self.room = _make_room("RunBeatRoom")

        self.lead_gm_account = AccountFactory(username="runbeatlead")
        self.lead_gm_profile = GMProfileFactory(account=self.lead_gm_account, level=GMLevel.JUNIOR)
        self.gm_table = GMTableFactory(gm=self.lead_gm_profile)
        self.lead_gm_actor, self.lead_gm_sheet = _make_actor_with_account(
            "runbeat_lead_actor", self.room, self.lead_gm_account
        )

        self.player_account = AccountFactory(username="runbeatplayer")
        self.player_actor, _ = _make_actor_with_account(
            "runbeat_player_actor", self.room, self.player_account
        )

        self.scene = SceneFactory(location=self.room, is_active=True)
        SceneParticipationFactory(scene=self.scene, account=self.lead_gm_account, is_gm=True)
        SceneParticipationFactory(scene=self.scene, account=self.player_account, is_gm=False)

        self.story = StoryFactory(
            owners=[self.lead_gm_account],
            scope=StoryScope.CHARACTER,
            primary_table=self.gm_table,
            status=StoryStatus.ACTIVE,
        )
        self.chapter = ChapterFactory(story=self.story)
        self.episode = EpisodeFactory(chapter=self.chapter, order=1)
        self.progress = StoryProgressFactory(
            story=self.story,
            character_sheet=self.lead_gm_sheet,
            current_episode=self.episode,
            is_active=True,
        )


class RunBeatActionEncounterJourneyTests(RunBeatActionTestBase):
    """The full ENCOUNTER-beat journey from the spec's test seam."""

    def setUp(self) -> None:
        super().setUp()
        self.boss_template = CreatureTemplateFactory(tier=OpponentTier.BOSS)
        CreaturePhaseTemplateFactory(creature_template=self.boss_template, phase_number=1)
        CreaturePhaseTemplateFactory(creature_template=self.boss_template, phase_number=2)
        self.mook_template = CreatureTemplateFactory(tier=OpponentTier.MOOK)

        self.beat = BeatFactory(episode=self.episode, kind=BeatKind.ENCOUNTER, risk=RenownRisk.HIGH)
        self.boss_line = BeatOpponentLineFactory(
            beat=self.beat, creature_template=self.boss_template, count=1, order=0
        )
        self.mook_line = BeatOpponentLineFactory(
            beat=self.beat, creature_template=self.mook_template, count=2, order=1
        )

    def test_run_beat_creates_encounter_and_spawns_opponents(self) -> None:
        result = RunBeatAction().run(self.lead_gm_actor, beat_id=self.beat.pk)
        self.assertTrue(result.success, result.message)

        self.scene.refresh_from_db()
        self.assertEqual(self.scene.running_beat_id, self.beat.pk)

        encounter = CombatEncounter.objects.get(scene=self.scene)
        self.assertEqual(encounter.story_beat_id, self.beat.pk)
        # Decision 3 mapping: RenownRisk.HIGH -> combat RiskLevel "high".
        self.assertEqual(encounter.risk_level, "high")

        boss_opponents = CombatOpponent.objects.filter(
            encounter=encounter, creature_template=self.boss_template
        )
        self.assertEqual(boss_opponents.count(), 1)
        self.assertEqual(BossPhase.objects.filter(opponent=boss_opponents.first()).count(), 2)

        mook_opponents = CombatOpponent.objects.filter(
            encounter=encounter, creature_template=self.mook_template
        )
        self.assertEqual(mook_opponents.count(), 2)

        self.assertIn("opponents", result.data)
        self.assertTrue(all(o["success"] for o in result.data["opponents"]))

    def test_rerunning_same_beat_is_idempotent(self) -> None:
        first = RunBeatAction().run(self.lead_gm_actor, beat_id=self.beat.pk)
        self.assertTrue(first.success, first.message)
        second = RunBeatAction().run(self.lead_gm_actor, beat_id=self.beat.pk)
        self.assertTrue(second.success, second.message)
        self.assertTrue(second.data.get("already_running"))
        self.assertEqual(CombatEncounter.objects.filter(scene=self.scene).count(), 1)

    def test_non_scene_gm_denied(self) -> None:
        result = RunBeatAction().run(self.player_actor, beat_id=self.beat.pk)
        self.assertFalse(result.success)
        self.scene.refresh_from_db()
        self.assertIsNone(self.scene.running_beat_id)

    def test_gm_who_does_not_run_the_story_denied(self) -> None:
        """A JUNIOR+ GM who is this scene's GM but NOT this beat's story's Lead GM is refused."""
        other_gm_account = AccountFactory(username="runbeatoutsider")
        GMProfileFactory(account=other_gm_account, level=GMLevel.JUNIOR)
        other_gm_actor, _ = _make_actor_with_account(
            "runbeat_outsider_actor", self.room, other_gm_account
        )
        SceneParticipationFactory(scene=self.scene, account=other_gm_account, is_gm=True)

        result = RunBeatAction().run(other_gm_actor, beat_id=self.beat.pk)
        self.assertFalse(result.success)
        self.scene.refresh_from_db()
        self.assertIsNone(self.scene.running_beat_id)

    def test_task_kind_beat_refused(self) -> None:
        task_beat = BeatFactory(episode=self.episode, kind=BeatKind.TASK)
        result = RunBeatAction().run(self.lead_gm_actor, beat_id=task_beat.pk)
        self.assertFalse(result.success)

    def test_requirement_kind_beat_refused(self) -> None:
        req_beat = BeatFactory(episode=self.episode, kind=BeatKind.REQUIREMENT)
        result = RunBeatAction().run(self.lead_gm_actor, beat_id=req_beat.pk)
        self.assertFalse(result.success)

    def test_scene_already_running_a_different_beat_refused(self) -> None:
        other_beat = BeatFactory(episode=self.episode, kind=BeatKind.ENCOUNTER)
        first = RunBeatAction().run(self.lead_gm_actor, beat_id=other_beat.pk)
        self.assertTrue(first.success, first.message)

        result = RunBeatAction().run(self.lead_gm_actor, beat_id=self.beat.pk)
        self.assertFalse(result.success)
        self.scene.refresh_from_db()
        self.assertEqual(self.scene.running_beat_id, other_beat.pk)


class RunBeatActionSituationJourneyTests(RunBeatActionTestBase):
    """The SITUATION-beat side of the journey: instantiate_situation is called."""

    def setUp(self) -> None:
        super().setUp()
        self.situation_template = SituationTemplateFactory()
        self.beat = BeatFactory(episode=self.episode, kind=BeatKind.SITUATION)
        self.staged_line = BeatStagedTemplateFactory(
            beat=self.beat, situation_template=self.situation_template
        )

    def test_run_beat_instantiates_situation(self) -> None:
        result = RunBeatAction().run(self.lead_gm_actor, beat_id=self.beat.pk)
        self.assertTrue(result.success, result.message)
        self.scene.refresh_from_db()
        self.assertEqual(self.scene.running_beat_id, self.beat.pk)
        self.assertTrue(
            SituationInstance.objects.filter(
                template=self.situation_template, location=self.room
            ).exists()
        )
        self.assertEqual(len(result.data["staged"]), 1)
        self.assertTrue(result.data["staged"][0]["success"])


class GMListRunnableBeatsActionTests(RunBeatActionTestBase):
    """GMListRunnableBeatsAction scopes rows to stories the acting GM runs."""

    def setUp(self) -> None:
        super().setUp()
        self.beat = BeatFactory(episode=self.episode, kind=BeatKind.ENCOUNTER)
        # A TASK beat on the same active episode must not appear (not runnable).
        BeatFactory(episode=self.episode, kind=BeatKind.TASK)

    def test_lead_gm_sees_own_runnable_beats(self) -> None:
        result = GMListRunnableBeatsAction().run(self.lead_gm_actor)
        self.assertTrue(result.success, result.message)
        ids = [row["id"] for row in result.data["beats"]]
        self.assertIn(self.beat.pk, ids)
        self.assertEqual(len(ids), 1)

    def test_non_gm_sees_no_beats(self) -> None:
        result = GMListRunnableBeatsAction().run(self.player_actor)
        self.assertTrue(result.success, result.message)
        self.assertEqual(result.data["beats"], [])

    def test_outsider_gm_does_not_see_this_story(self) -> None:
        """A JUNIOR+ GM running a DIFFERENT story never sees this story's beats."""
        outsider_account = AccountFactory(username="runbeatoutsider2")
        outsider_profile = GMProfileFactory(account=outsider_account, level=GMLevel.JUNIOR)
        GMTableFactory(gm=outsider_profile)
        outsider_actor, _ = _make_actor_with_account(
            "runbeat_outsider2_actor", self.room, outsider_account
        )
        result = GMListRunnableBeatsAction().run(outsider_actor)
        self.assertTrue(result.success, result.message)
        ids = [row["id"] for row in result.data["beats"]]
        self.assertNotIn(self.beat.pk, ids)
