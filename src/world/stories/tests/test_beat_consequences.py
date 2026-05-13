"""Tests for beat resolution consequence pool wiring (Task 13).

Covers the _maybe_fire_pool_on_completion path for all scope/resolution
combinations, LEGEND_AWARD participant guards, and the serializer's
participants/extra_participants fields.
"""

from __future__ import annotations

from evennia.utils.test_resources import EvenniaTestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.gm.factories import GMTableFactory
from world.societies.exceptions import LegendAwardParticipantMissingError, LegendAwardScopeError
from world.societies.factories import LegendSourceTypeFactory
from world.societies.models import LegendEntry, LegendEvent
from world.stories.constants import BeatOutcome, BeatPredicateType, EraStatus, StoryScope
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    EraFactory,
    GlobalStoryProgressFactory,
    GroupStoryProgressFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.models import BeatCompletion
from world.stories.services.beats import record_aggregate_contribution, record_gm_marked_outcome


def _make_legend_award_pool():
    """Create a ConsequencePool containing a LEGEND_AWARD effect."""
    source_type = LegendSourceTypeFactory()
    consequence = ConsequenceFactory()
    ConsequenceEffectFactory(
        consequence=consequence,
        effect_type=EffectType.LEGEND_AWARD,
        legend_base_value=10,
        legend_source_type=source_type,
        legend_description_template="A legendary deed.",
    )
    pool = ConsequencePoolFactory()
    ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
    return pool


def _make_era():
    """Return the single active Era, creating it if absent."""
    from world.stories.models import Era

    try:
        return Era.objects.get_active()
    except Era.DoesNotExist:
        return EraFactory(status=EraStatus.ACTIVE)


class CharacterScopeSuccessPoolTests(EvenniaTestCase):
    """CHARACTER-scope beat with success_consequences pool containing LEGEND_AWARD."""

    @classmethod
    def setUpTestData(cls) -> None:
        _make_era()
        cls.pool = _make_legend_award_pool()
        sheet = CharacterSheetFactory()
        # CharacterSheetFactory creates a PRIMARY persona by default.
        cls.primary_persona = sheet.primary_persona
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        cls.beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,
            success_consequences=cls.pool,
        )
        cls.progress = StoryProgressFactory(story=story, character_sheet=sheet)

    def test_success_pool_fires_on_success_outcome(self) -> None:
        """Marking beat SUCCESS fires the success_consequences pool → LegendEvent + LegendEntry."""
        entry_count_before = LegendEntry.objects.count()

        record_gm_marked_outcome(
            progress=self.progress,
            beat=self.beat,
            outcome=BeatOutcome.SUCCESS,
        )

        new_entries = LegendEntry.objects.count() - entry_count_before
        self.assertEqual(new_entries, 1, "Expected one LegendEntry for the primary persona")
        event = LegendEvent.objects.order_by("-pk").first()
        self.assertIsNotNone(event)
        entry = LegendEntry.objects.filter(event=event).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.persona, self.primary_persona)

    def test_failure_pool_does_not_fire_for_success_outcome(self) -> None:
        """success_consequences pool set but FAILURE outcome → success pool does NOT fire."""
        # Use a separate beat so the previous test's flip doesn't interfere.
        sheet2 = CharacterSheetFactory()
        story2 = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet2)
        chapter2 = ChapterFactory(story=story2)
        episode2 = EpisodeFactory(chapter=chapter2)
        beat2 = BeatFactory(
            episode=episode2,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,
            success_consequences=self.pool,
            failure_consequences=None,
        )
        progress2 = StoryProgressFactory(story=story2, character_sheet=sheet2)

        entry_count_before = LegendEntry.objects.count()
        record_gm_marked_outcome(
            progress=progress2,
            beat=beat2,
            outcome=BeatOutcome.FAILURE,
        )
        new_entries = LegendEntry.objects.count() - entry_count_before
        self.assertEqual(new_entries, 0, "success pool must not fire for FAILURE outcome")


class FailurePoolFiresTests(EvenniaTestCase):
    """failure_consequences pool fires when beat resolves FAILURE."""

    @classmethod
    def setUpTestData(cls) -> None:
        _make_era()
        cls.failure_pool = _make_legend_award_pool()
        sheet = CharacterSheetFactory()
        cls.primary_persona = sheet.primary_persona
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        cls.beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,
            failure_consequences=cls.failure_pool,
        )
        cls.progress = StoryProgressFactory(story=story, character_sheet=sheet)

    def test_failure_pool_fires_on_failure_outcome(self) -> None:
        """Marking beat FAILURE fires failure_consequences pool."""
        entry_count_before = LegendEntry.objects.count()

        record_gm_marked_outcome(
            progress=self.progress,
            beat=self.beat,
            outcome=BeatOutcome.FAILURE,
        )

        new_entries = LegendEntry.objects.count() - entry_count_before
        self.assertEqual(new_entries, 1, "Expected one LegendEntry for the primary persona")


class NoPoolNoConsequencesTests(EvenniaTestCase):
    """Beat with all pool FKs null → marking resolves normally with no effects."""

    @classmethod
    def setUpTestData(cls) -> None:
        _make_era()
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        cls.beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,
            success_consequences=None,
            failure_consequences=None,
            expired_consequences=None,
        )
        cls.progress = StoryProgressFactory(story=story, character_sheet=sheet)

    def test_no_pool_no_consequences(self) -> None:
        """No exception raised, no LegendEntry created when all pools are null."""
        entry_count_before = LegendEntry.objects.count()

        completion = record_gm_marked_outcome(
            progress=self.progress,
            beat=self.beat,
            outcome=BeatOutcome.SUCCESS,
        )

        self.assertIsInstance(completion, BeatCompletion)
        new_entries = LegendEntry.objects.count() - entry_count_before
        self.assertEqual(new_entries, 0)


class GroupScopeLegendAwardRequiresParticipantsTests(EvenniaTestCase):
    """GROUP-scope GM_MARKED beat + LEGEND_AWARD pool + no participants → error."""

    @classmethod
    def setUpTestData(cls) -> None:
        _make_era()
        cls.pool = _make_legend_award_pool()
        story = StoryFactory(scope=StoryScope.GROUP)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        cls.beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,
            success_consequences=cls.pool,
        )
        table = GMTableFactory()
        cls.progress = GroupStoryProgressFactory(story=story, gm_table=table)

    def test_group_scope_legend_award_requires_participants(self) -> None:
        """Empty participants with LEGEND_AWARD pool raises LegendAwardParticipantMissingError."""
        with self.assertRaises(LegendAwardParticipantMissingError):
            record_gm_marked_outcome(
                progress=self.progress,
                beat=self.beat,
                outcome=BeatOutcome.SUCCESS,
                participants=[],
            )

    def test_group_scope_with_participants_fires_pool(self) -> None:
        """Providing participants for GROUP scope fires pool successfully."""
        sheet = CharacterSheetFactory()
        # CharacterSheetFactory creates a PRIMARY persona; use it directly.
        persona = sheet.primary_persona
        # Use a fresh beat so it hasn't been flipped already.
        story2 = StoryFactory(scope=StoryScope.GROUP)
        chapter2 = ChapterFactory(story=story2)
        episode2 = EpisodeFactory(chapter=chapter2)
        beat2 = BeatFactory(
            episode=episode2,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,
            success_consequences=self.pool,
        )
        table2 = GMTableFactory()
        progress2 = GroupStoryProgressFactory(story=story2, gm_table=table2)

        entry_count_before = LegendEntry.objects.count()
        record_gm_marked_outcome(
            progress=progress2,
            beat=beat2,
            outcome=BeatOutcome.SUCCESS,
            participants=[persona],
        )
        new_entries = LegendEntry.objects.count() - entry_count_before
        self.assertEqual(new_entries, 1)


class GlobalScopeLegendAwardRaisesTests(EvenniaTestCase):
    """GLOBAL-scope beat with LEGEND_AWARD pool → LegendAwardScopeError."""

    @classmethod
    def setUpTestData(cls) -> None:
        _make_era()
        cls.pool = _make_legend_award_pool()
        story = StoryFactory(scope=StoryScope.GLOBAL)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        cls.beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,
            success_consequences=cls.pool,
        )
        cls.progress = GlobalStoryProgressFactory(story=story)

    def test_global_scope_legend_award_raises_scope_error(self) -> None:
        """GLOBAL scope + LEGEND_AWARD in pool raises LegendAwardScopeError."""
        with self.assertRaises(LegendAwardScopeError):
            record_gm_marked_outcome(
                progress=self.progress,
                beat=self.beat,
                outcome=BeatOutcome.SUCCESS,
            )


class AggregateThresholdAutoDerivesParticipantsTests(EvenniaTestCase):
    """AGGREGATE_THRESHOLD beat: participants auto-derived from contribution rows."""

    @classmethod
    def setUpTestData(cls) -> None:
        _make_era()
        cls.pool = _make_legend_award_pool()
        story = StoryFactory(scope=StoryScope.GROUP)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        cls.beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.AGGREGATE_THRESHOLD,
            outcome=BeatOutcome.UNSATISFIED,
            required_points=1,
            success_consequences=cls.pool,
        )
        cls.table = GMTableFactory()
        cls.progress = GroupStoryProgressFactory(story=story, gm_table=cls.table)
        # Contributor sheet with a PRIMARY persona.
        cls.sheet = CharacterSheetFactory()
        cls.primary_persona = cls.sheet.primary_persona

    def test_aggregate_threshold_auto_derives_participants(self) -> None:
        """AGGREGATE_THRESHOLD crossing auto-derives primary personas of contributors."""
        entry_count_before = LegendEntry.objects.count()

        record_aggregate_contribution(
            beat=self.beat,
            character_sheet=self.sheet,
            points=5,
        )

        new_entries = LegendEntry.objects.count() - entry_count_before
        self.assertEqual(
            new_entries, 1, "Expected 1 LegendEntry for the auto-derived primary persona"
        )
        entry = LegendEntry.objects.order_by("-pk").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.persona, self.primary_persona)


class CharacterExtraParticipantsTests(EvenniaTestCase):
    """CHARACTER-scope mark with extra_participants extends credit beyond primary persona."""

    @classmethod
    def setUpTestData(cls) -> None:
        _make_era()
        cls.pool = _make_legend_award_pool()
        sheet = CharacterSheetFactory()
        cls.primary_persona = sheet.primary_persona
        # Extra persona on a different sheet.
        extra_sheet = CharacterSheetFactory()
        cls.extra_persona = extra_sheet.primary_persona
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        cls.beat = BeatFactory(
            episode=episode,
            predicate_type=BeatPredicateType.GM_MARKED,
            outcome=BeatOutcome.UNSATISFIED,
            success_consequences=cls.pool,
        )
        cls.progress = StoryProgressFactory(story=story, character_sheet=sheet)

    def test_character_extra_participants_extends_credit(self) -> None:
        """Both primary + extra personas get LegendEntries from the same event."""
        entry_count_before = LegendEntry.objects.count()

        record_gm_marked_outcome(
            progress=self.progress,
            beat=self.beat,
            outcome=BeatOutcome.SUCCESS,
            extra_participants=[self.extra_persona],
        )

        new_entries = LegendEntry.objects.count() - entry_count_before
        self.assertEqual(
            new_entries, 2, "Expected 2 LegendEntries: primary persona + extra persona"
        )
        event = LegendEvent.objects.order_by("-pk").first()
        personas_credited = set(
            LegendEntry.objects.filter(event=event).values_list("persona_id", flat=True)
        )
        self.assertIn(self.primary_persona.pk, personas_credited)
        self.assertIn(self.extra_persona.pk, personas_credited)
