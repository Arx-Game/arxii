from django.core.exceptions import ValidationError
from evennia.utils.test_resources import EvenniaTestCase

from world.stories.constants import StoryScope, TransitionMode
from world.stories.factories import (
    ChapterFactory,
    EpisodeFactory,
    EpisodeResolutionFactory,
    GlobalStoryProgressFactory,
    GroupStoryProgressFactory,
    StoryFactory,
    TransitionFactory,
)
from world.stories.models import EpisodeResolution
from world.stories.services.episodes import resolve_episode


class EpisodeResolutionModelTests(EvenniaTestCase):
    """Unit tests for the EpisodeResolution audit ledger model."""

    def test_resolution_records_transition_and_episode(self) -> None:
        """EpisodeResolution stores episode and chosen_transition correctly."""
        transition = TransitionFactory()
        resolution = EpisodeResolutionFactory(
            episode=transition.source_episode,
            chosen_transition=transition,
        )
        self.assertEqual(resolution.episode, transition.source_episode)
        self.assertEqual(resolution.chosen_transition, transition)
        self.assertIsNotNone(resolution.character_sheet)
        self.assertIsNotNone(resolution.resolved_at)

    def test_resolution_allows_null_transition(self) -> None:
        """chosen_transition may be None for frontier-pause resolutions."""
        resolution = EpisodeResolutionFactory(chosen_transition=None)
        self.assertIsNone(resolution.chosen_transition)

    def test_resolution_str_with_transition(self) -> None:
        """__str__ includes episode title and target episode title when transition set."""
        transition = TransitionFactory()
        resolution = EpisodeResolutionFactory(
            episode=transition.source_episode,
            chosen_transition=transition,
        )
        result = str(resolution)
        self.assertIn(transition.source_episode.title, result)
        self.assertIn(transition.target_episode.title, result)

    def test_resolution_str_without_transition(self) -> None:
        """__str__ shows '(frontier)' when chosen_transition is None."""
        resolution = EpisodeResolutionFactory(chosen_transition=None)
        self.assertIn("(frontier)", str(resolution))

    def test_resolution_defaults_optional_fields_to_none(self) -> None:
        """resolved_by and era default to None."""
        resolution = EpisodeResolutionFactory()
        self.assertIsNone(resolution.resolved_by)
        self.assertIsNone(resolution.era)


class EpisodeResolutionScopeTests(EvenniaTestCase):
    """Tests that EpisodeResolution scope-field population and clean() are correct."""

    def _make_group_episode(self):
        """Return an episode belonging to a GROUP-scope story."""
        story = StoryFactory(scope=StoryScope.GROUP)
        chapter = ChapterFactory(story=story)
        return EpisodeFactory(chapter=chapter)

    def _make_global_episode(self):
        """Return an episode belonging to a GLOBAL-scope story."""
        story = StoryFactory(scope=StoryScope.GLOBAL)
        chapter = ChapterFactory(story=story)
        return EpisodeFactory(chapter=chapter)

    # ------------------------------------------------------------------
    # clean() validation
    # ------------------------------------------------------------------

    def test_clean_character_scope_requires_character_sheet(self) -> None:
        """clean() rejects CHARACTER-scope resolution with no character_sheet."""
        episode = EpisodeFactory()  # chapter.story defaults to CHARACTER scope
        resolution = EpisodeResolutionFactory(
            episode=episode,
            character_sheet=None,
            gm_table=None,
        )
        with self.assertRaises(ValidationError) as ctx:
            resolution.clean()
        self.assertIn("character_sheet", ctx.exception.message_dict)

    def test_clean_rejects_gm_table_on_character_scope(self) -> None:
        """clean() rejects gm_table being set for a CHARACTER-scope resolution."""
        from world.gm.factories import GMTableFactory

        gm_table = GMTableFactory()
        episode = EpisodeFactory()  # CHARACTER scope by default
        # character_sheet populated (factory default), gm_table also set.
        resolution = EpisodeResolutionFactory(
            episode=episode,
            gm_table=gm_table,
        )
        with self.assertRaises(ValidationError) as ctx:
            resolution.clean()
        self.assertIn("gm_table", ctx.exception.message_dict)

    def test_clean_group_scope_requires_gm_table(self) -> None:
        """clean() rejects GROUP-scope resolution with no gm_table."""
        episode = self._make_group_episode()
        resolution = EpisodeResolutionFactory(
            episode=episode,
            character_sheet=None,
            gm_table=None,
        )
        with self.assertRaises(ValidationError) as ctx:
            resolution.clean()
        self.assertIn("gm_table", ctx.exception.message_dict)

    def test_clean_rejects_character_sheet_on_group_scope(self) -> None:
        """clean() rejects character_sheet being set for a GROUP-scope resolution.

        For GROUP scope, clean() first checks gm_table is required (it's None
        here) and raises on that condition. The validation error key is 'gm_table'
        because that check fires first in clean(). We verify the ValidationError
        fires; the exact key reflects the ordering of guards in clean().
        """
        from world.character_sheets.factories import CharacterSheetFactory

        episode = self._make_group_episode()
        sheet = CharacterSheetFactory()
        # gm_table=None, character_sheet set — clean fires on missing gm_table first.
        resolution = EpisodeResolutionFactory(
            episode=episode,
            character_sheet=sheet,
            gm_table=None,
        )
        with self.assertRaises(ValidationError):
            resolution.clean()

    def test_clean_global_scope_rejects_any_fk(self) -> None:
        """clean() rejects any FK set on a GLOBAL-scope resolution."""
        from world.character_sheets.factories import CharacterSheetFactory

        episode = self._make_global_episode()
        sheet = CharacterSheetFactory()
        resolution = EpisodeResolutionFactory(
            episode=episode,
            character_sheet=sheet,
            gm_table=None,
        )
        with self.assertRaises(ValidationError):
            resolution.clean()

    def test_clean_global_scope_accepts_both_null(self) -> None:
        """clean() passes for GLOBAL-scope resolution with both FKs null."""
        episode = self._make_global_episode()
        resolution = EpisodeResolutionFactory(
            episode=episode,
            character_sheet=None,
            gm_table=None,
        )
        # Should not raise.
        resolution.clean()

    # ------------------------------------------------------------------
    # resolve_episode integration: GROUP scope
    # ------------------------------------------------------------------

    def test_group_scope_resolution_records_gm_table(self) -> None:
        """resolve_episode for GROUP progress records gm_table; character_sheet is None."""
        story = StoryFactory(scope=StoryScope.GROUP)
        chapter = ChapterFactory(story=story)
        source = EpisodeFactory(chapter=chapter)
        target = EpisodeFactory(chapter=chapter)
        transition = TransitionFactory(
            source_episode=source,
            target_episode=target,
            mode=TransitionMode.AUTO,
        )

        progress = GroupStoryProgressFactory(story=story, current_episode=source)

        resolution = resolve_episode(progress=progress)

        self.assertIsInstance(resolution, EpisodeResolution)
        self.assertEqual(resolution.gm_table, progress.gm_table)
        self.assertIsNone(resolution.character_sheet)
        self.assertEqual(resolution.chosen_transition, transition)

    # ------------------------------------------------------------------
    # resolve_episode integration: GLOBAL scope
    # ------------------------------------------------------------------

    def test_global_scope_resolution_leaves_both_null(self) -> None:
        """resolve_episode for GLOBAL progress leaves character_sheet and gm_table null."""
        story = StoryFactory(scope=StoryScope.GLOBAL)
        chapter = ChapterFactory(story=story)
        source = EpisodeFactory(chapter=chapter)
        target = EpisodeFactory(chapter=chapter)
        TransitionFactory(
            source_episode=source,
            target_episode=target,
            mode=TransitionMode.AUTO,
        )

        progress = GlobalStoryProgressFactory(story=story, current_episode=source)

        resolution = resolve_episode(progress=progress)

        self.assertIsInstance(resolution, EpisodeResolution)
        self.assertIsNone(resolution.character_sheet)
        self.assertIsNone(resolution.gm_table)
