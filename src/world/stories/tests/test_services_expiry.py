"""Expiry is a completion (#3558): pool, stakes, activation, ledger."""

from evennia.utils.test_resources import EvenniaTestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.societies.factories import LegendSourceTypeFactory
from world.societies.models import LegendEvent
from world.stories.constants import StoryScope
from world.stories.factories import (
    BeatFactory,
    ChapterFactory,
    EpisodeFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.services.beats import _fire_pool_with_context


def _pool_with_condition_and_legend(template):
    """A pool whose one consequence applies ``template`` to SELF and awards legend."""
    # apply_pool_deterministically fires every pool row unconditionally, so the
    # Consequence's own outcome_tier is irrelevant here; use the factory default
    # (Consequence.outcome_tier is NOT NULL).
    consequence = ConsequenceFactory()
    ConsequenceEffectFactory(
        consequence=consequence,
        effect_type=EffectType.APPLY_CONDITION,
        condition_template=template,
    )
    ConsequenceEffectFactory(
        consequence=consequence,
        effect_type=EffectType.LEGEND_AWARD,
        legend_base_value=10,
        legend_source_type=LegendSourceTypeFactory(),
        legend_description_template="Too slow.",
    )
    pool = ConsequencePoolFactory()
    ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
    return pool


def _pool_with_legend_only():
    """A pool whose one consequence only awards legend (no character-targeted effect).

    Used where no participant/character is resolvable (GROUP scope, no
    participants) — a character-targeted effect (e.g. APPLY_CONDITION to SELF)
    would fail against the unsaved stub ObjectDB that _fire_pool_with_context
    falls back to in that case, which is a pre-existing, unrelated constraint.
    """
    consequence = ConsequenceFactory()
    ConsequenceEffectFactory(
        consequence=consequence,
        effect_type=EffectType.LEGEND_AWARD,
        legend_base_value=10,
        legend_source_type=LegendSourceTypeFactory(),
        legend_description_template="Too slow.",
    )
    pool = ConsequencePoolFactory()
    ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
    return pool


class SkipEffectTypesTests(EvenniaTestCase):
    def test_skip_legend_fires_other_effects_and_no_legend(self) -> None:
        sheet = CharacterSheetFactory()
        story = StoryFactory(scope=StoryScope.CHARACTER, character_sheet=sheet)
        beat = BeatFactory(episode=EpisodeFactory(chapter=ChapterFactory(story=story)))
        progress = StoryProgressFactory(story=story, character_sheet=sheet)
        template = ConditionTemplateFactory()
        pool = _pool_with_condition_and_legend(template)

        _fire_pool_with_context(
            pool=pool,
            beat=beat,
            progress=progress,
            scope=StoryScope.CHARACTER,
            participants=[sheet.primary_persona],
            skip_effect_types=frozenset({EffectType.LEGEND_AWARD}),
        )

        assert ConditionInstance.objects.filter(target=sheet.character, condition=template).exists()
        assert not LegendEvent.objects.exists()

    def test_skip_legend_needs_no_participants(self) -> None:
        """With LEGEND_AWARD skipped the participant guard must not raise."""
        story = StoryFactory(scope=StoryScope.GROUP)
        beat = BeatFactory(episode=EpisodeFactory(chapter=ChapterFactory(story=story)))
        pool = _pool_with_legend_only()

        _fire_pool_with_context(
            pool=pool,
            beat=beat,
            progress=None,
            scope=StoryScope.GROUP,
            participants=[],
            skip_effect_types=frozenset({EffectType.LEGEND_AWARD}),
        )
        assert not LegendEvent.objects.exists()
