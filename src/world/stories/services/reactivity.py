"""Reactivity hooks called by external systems on character state change.

External apps (progression, achievements, conditions, codex) call the
appropriate entry point after they mutate character state. The hooks
scope re-evaluation to the affected character's active stories and
flip any now-satisfied beats.

Pattern: each hook iterates the character's active stories across all
three scopes (CHARACTER / GROUP / GLOBAL) and calls evaluate_auto_beats
on each. evaluate_auto_beats handles the scope-dispatch internally.

This module has no direct knowledge of the triggering change — callers
pass the character_sheet and whichever domain model mutated. Hooks
re-evaluate all relevant predicate types even if the trigger was more
specific (cheaper to re-evaluate a handful of beats than to route
per-predicate-type).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from world.stories.services.beats import evaluate_auto_beats

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.stories.models import Story
    from world.stories.types import AnyStoryProgress


def on_character_state_changed(sheet: CharacterSheet) -> None:
    """Re-evaluate auto-beats across this character's active stories.

    General-purpose entry point — callable from any mutation site that
    could affect a character-state predicate (level, achievement,
    condition, codex). Specific entry points below just delegate here,
    but exist for clarity at call sites and to allow future per-trigger
    optimization.
    """
    for progress in _active_progress_for_character(sheet):
        evaluate_auto_beats(progress)


def on_character_level_changed(sheet: CharacterSheet) -> None:
    """Called after progression updates CharacterClassLevel.

    Invalidates the sheet's class-level cache defensively (progression
    services should also do this at the mutation site, per Wave 8) then
    re-evaluates active stories.
    """
    sheet.invalidate_class_level_cache()
    on_character_state_changed(sheet)


def on_achievement_earned(sheet: CharacterSheet, achievement: Any) -> None:  # noqa: ARG001
    """Called after achievements service grants an achievement.

    `achievement` is unused today but kept in the signature so callers
    stay explicit about what just happened — useful for future
    per-predicate-type routing or logging.
    """
    sheet.invalidate_achievement_cache()
    on_character_state_changed(sheet)


def on_condition_applied(sheet: CharacterSheet, condition_instance: Any) -> None:  # noqa: ARG001
    """Called after conditions service attaches a ConditionInstance.

    `condition_instance` is unused today — signature kept for clarity at
    call sites and future per-trigger routing.
    """
    sheet.invalidate_condition_cache()
    on_character_state_changed(sheet)


def on_condition_expired(sheet: CharacterSheet, condition_template: Any) -> None:  # noqa: ARG001
    """Called when a ConditionInstance expires or is removed.

    Covers the 'story can't progress while crippled' use case: when the
    condition lifts, re-evaluate in case a beat's predicate (including
    future inverse predicates) has flipped.

    `condition_template` is unused today — signature kept for clarity at
    call sites.
    """
    sheet.invalidate_condition_cache()
    on_character_state_changed(sheet)


def on_codex_entry_unlocked(sheet: CharacterSheet, codex_entry: Any) -> None:  # noqa: ARG001
    """Called after codex service unlocks a CodexEntry for a character.

    Codex knowledge is keyed on RosterEntry (not CharacterSheet) per the
    codex model design, but the reactivity entry point takes the sheet
    because stories predicates walk sheet → roster_entry internally.

    `codex_entry` is unused today — signature kept for clarity at call
    sites.
    """
    on_character_state_changed(sheet)


def on_story_advanced(story: Story) -> None:
    """Re-evaluate any beats referencing this story via STORY_AT_MILESTONE.

    Called internally from resolve_episode after the progression advances.
    Finds every Beat with predicate_type=STORY_AT_MILESTONE and
    referenced_story=story, then walks to each beat's parent progress
    records and re-evaluates any that are currently sitting on that
    beat's episode. Older episodes' beats are historical.
    """
    from world.stories.constants import BeatPredicateType  # noqa: PLC0415
    from world.stories.models import Beat  # noqa: PLC0415

    candidate_beats = Beat.objects.filter(
        predicate_type=BeatPredicateType.STORY_AT_MILESTONE,
        referenced_story=story,
    ).select_related("episode__chapter__story")

    seen_progress: set[tuple[str, int]] = set()
    for beat in candidate_beats:
        beat_story = beat.episode.chapter.story
        for progress in _active_progress_for_story(beat_story):
            if progress.current_episode_id != beat.episode_id:
                continue
            key = (type(progress).__name__, progress.pk)
            if key in seen_progress:
                continue
            seen_progress.add(key)
            evaluate_auto_beats(progress)


def _active_progress_for_character(sheet: CharacterSheet) -> Iterator[AnyStoryProgress]:
    """Yield all active progress records the character participates in.

    CHARACTER scope: StoryProgress where character_sheet=sheet.
    GROUP scope: GroupStoryProgress for any GMTable the character's
        persona has active membership on (GMTableMembership.left_at
        is null).
    GLOBAL scope: GlobalStoryProgress for any story the character has
        an active StoryParticipation on.
    """
    from world.stories.models import (  # noqa: PLC0415
        GlobalStoryProgress,
        GroupStoryProgress,
        StoryProgress,
    )

    yield from StoryProgress.objects.filter(
        character_sheet=sheet,
        is_active=True,
    )

    yield from GroupStoryProgress.objects.filter(
        gm_table__memberships__persona__character_sheet=sheet,
        gm_table__memberships__left_at__isnull=True,
        is_active=True,
    ).distinct()

    yield from GlobalStoryProgress.objects.filter(
        story__participants__character=sheet.character,
        story__participants__is_active=True,
        is_active=True,
    ).distinct()


def _active_progress_for_story(story: Story) -> Iterator[AnyStoryProgress]:
    """Yield active progress records for a story, dispatching on scope."""
    from world.stories.constants import StoryScope  # noqa: PLC0415
    from world.stories.models import GlobalStoryProgress  # noqa: PLC0415

    match story.scope:
        case StoryScope.CHARACTER:
            yield from story.progress_records.filter(is_active=True)
        case StoryScope.GROUP:
            yield from story.group_progress_records.filter(is_active=True)
        case StoryScope.GLOBAL:
            try:
                progress = story.global_progress
            except GlobalStoryProgress.DoesNotExist:
                return
            if progress.is_active:
                yield progress
