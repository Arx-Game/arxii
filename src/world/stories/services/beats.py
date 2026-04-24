"""Beat evaluation service for the stories system.

Public API:
    evaluate_auto_beats(progress) — re-evaluates all auto-detected beats in the
        progress's current episode, recording BeatCompletion rows for any that
        transition from UNSATISFIED to a resolved outcome.

    record_gm_marked_outcome(*, progress, beat, outcome, gm_notes) — GM's manual
        call to mark a GM_MARKED beat with SUCCESS or FAILURE.

    record_aggregate_contribution(*, beat, character_sheet, points, source_note) —
        records a per-character contribution toward an AGGREGATE_THRESHOLD beat and
        re-evaluates the beat within the same atomic transaction.

    expire_overdue_beats(now) — flips UNSATISFIED beats with past deadlines to
        EXPIRED outcome. Idempotent; safe for a cron hook.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.db import transaction

from world.character_sheets.models import CharacterSheet
from world.roster.models import RosterEntry
from world.stories.constants import BeatOutcome, BeatPredicateType, StoryMilestoneType, StoryScope
from world.stories.models import AggregateBeatContribution, Beat, BeatCompletion, Era, StoryProgress
from world.stories.types import AnyStoryProgress, StoryStatus

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import datetime

    from world.stories.models import Episode


def evaluate_auto_beats(progress: AnyStoryProgress) -> None:
    """Re-evaluate all auto-detectable beats in the progress's current episode.

    For each beat whose predicate_type is not GM_MARKED:
        - Evaluate the predicate against the progress's character (CHARACTER scope)
          or skip character-specific checks (GROUP / GLOBAL scope, where auto-beats
          must be non-character predicates such as STORY_AT_MILESTONE).
        - If the beat is currently UNSATISFIED and the predicate now yields a
          resolved outcome (SUCCESS / FAILURE / EXPIRED), flip the outcome
          in-place and write a BeatCompletion row.

    GM_MARKED beats are left completely untouched — they require an explicit
    ``record_gm_marked_outcome`` call.

    Does nothing and returns cleanly when ``progress.current_episode`` is None.

    After beat evaluation, idempotently opens a SessionRequest when the episode
    is now ready-to-run and requires GM involvement.
    """
    if progress.current_episode is None:
        return

    scope = progress.story.scope
    era = Era.objects.get_active()

    # CHARACTER scope: we need the character sheet for predicate evaluation.
    sheet: CharacterSheet | None = None
    roster_entry = None
    if scope == StoryScope.CHARACTER:
        sheet = progress.character_sheet
        roster_entry = _current_roster_entry(sheet)

    beats = Beat.objects.filter(episode=progress.current_episode)
    with transaction.atomic():
        for beat in beats:
            _evaluate_and_record_beat(beat, progress, scope, sheet, roster_entry, era)

        # Write-path hook: open a SessionRequest if the episode is now ready-to-run
        # and requires a GM session. Idempotent — safe to call unconditionally.
        from world.stories.services.scheduling import maybe_create_session_request  # noqa: PLC0415

        maybe_create_session_request(progress)


_GM_MARKED_VALID_OUTCOMES = {BeatOutcome.SUCCESS, BeatOutcome.FAILURE}


def record_gm_marked_outcome(
    *,
    progress: AnyStoryProgress,
    beat: Beat,
    outcome: BeatOutcome,
    gm_notes: str = "",
) -> BeatCompletion:
    """Record a GM's manual outcome on a GM_MARKED beat.

    Works across all three scopes:
      - CHARACTER: writes character_sheet (from StoryProgress).
      - GROUP:     writes gm_table (from GroupStoryProgress).
      - GLOBAL:    writes neither (the beat's story scope is the sole identifier).

    Defensive assertions (programmer errors — the API serializer validates these
    for user-facing calls; assertions guard direct service callers):
        - beat.predicate_type == GM_MARKED
        - outcome in {SUCCESS, FAILURE}

    Flips beat.outcome in-place, creates and returns a BeatCompletion row.
    """
    # Defensive guard: MarkBeatInputSerializer validates this for API callers.
    if beat.predicate_type != BeatPredicateType.GM_MARKED:
        msg = (
            f"Beat {beat.pk} is not GM_MARKED (type={beat.predicate_type}); "
            "only GM_MARKED beats can be resolved via record_gm_marked_outcome."
        )
        raise ValueError(msg)
    # Defensive guard: ChoiceField in MarkBeatInputSerializer validates this.
    if outcome not in _GM_MARKED_VALID_OUTCOMES:
        msg = (
            f"Outcome {outcome!r} is not valid for a GM-marked resolution; "
            f"must be one of {_GM_MARKED_VALID_OUTCOMES}."
        )
        raise ValueError(msg)

    scope = progress.story.scope
    era = Era.objects.get_active()

    completion_kwargs: dict = {
        "beat": beat,
        "outcome": outcome,
        "era": era,
        "gm_notes": gm_notes,
    }
    if scope == StoryScope.CHARACTER:
        sheet: CharacterSheet = progress.character_sheet
        completion_kwargs["character_sheet"] = sheet
        completion_kwargs["roster_entry"] = _current_roster_entry(sheet)
    elif scope == StoryScope.GROUP:
        completion_kwargs["gm_table"] = progress.gm_table
    # GLOBAL: no scope-specific FK

    with transaction.atomic():
        # Flip the outcome in-place and persist.
        beat.outcome = outcome
        beat.save(update_fields=["outcome", "updated_at"])

        completion = BeatCompletion.objects.create(**completion_kwargs)

        # Write-path hook: open a SessionRequest if the episode is now ready-to-run
        # and requires a GM session. Idempotent — safe to call unconditionally.
        from world.stories.services.scheduling import maybe_create_session_request  # noqa: PLC0415

        maybe_create_session_request(progress)

    return completion


def record_aggregate_contribution(
    *,
    beat: Beat,
    character_sheet: CharacterSheet,
    points: int,
    source_note: str = "",
) -> AggregateBeatContribution:
    """Record a character's contribution toward an AGGREGATE_THRESHOLD beat.

    After recording, re-evaluates the beat and flips its outcome to SUCCESS
    if the threshold is met, creating a BeatCompletion row atomically.

    Idempotent with respect to completions: if the beat is already SUCCESS,
    the contribution row is still recorded but no additional BeatCompletion
    is created.

    Raises:
        BeatNotResolvableError: if beat.predicate_type is not AGGREGATE_THRESHOLD,
            or if points <= 0.
    """
    # Defensive guards: ContributeBeatInputSerializer validates these for API callers.
    if beat.predicate_type != BeatPredicateType.AGGREGATE_THRESHOLD:
        msg = "Only AGGREGATE_THRESHOLD beats accept contributions."
        raise ValueError(msg)
    if points <= 0:
        msg = "Contribution points must be positive."
        raise ValueError(msg)

    era = Era.objects.get_active()
    roster_entry = _current_roster_entry(character_sheet)

    story = beat.episode.chapter.story
    scope = story.scope

    with transaction.atomic():
        contrib = AggregateBeatContribution.objects.create(
            beat=beat,
            character_sheet=character_sheet,
            roster_entry=roster_entry,
            era=era,
            points=points,
            source_note=source_note,
        )
        # Re-evaluate only when the beat hasn't already crossed the threshold.
        if beat.outcome != BeatOutcome.SUCCESS:
            new_outcome = _evaluate_aggregate_beat(beat)
            if new_outcome == BeatOutcome.SUCCESS:
                beat.outcome = new_outcome
                beat.save(update_fields=["outcome", "updated_at"])

                # BeatCompletion for aggregate threshold crossing is scope-aware:
                # - CHARACTER: attribute to the character who crossed it.
                # - GROUP: attribute to the group (gm_table); individual contributions
                #   are already in the AggregateBeatContribution ledger.
                # - GLOBAL: no FK required.
                completion_kwargs: dict = {
                    "beat": beat,
                    "outcome": new_outcome,
                    "era": era,
                }
                if scope == StoryScope.CHARACTER:
                    completion_kwargs["character_sheet"] = character_sheet
                    completion_kwargs["roster_entry"] = roster_entry
                elif scope == StoryScope.GROUP:
                    from world.stories.services.progress import (  # noqa: PLC0415
                        get_active_progress_for_story,
                    )

                    group_progress = get_active_progress_for_story(story)
                    if group_progress is not None:
                        completion_kwargs["gm_table"] = group_progress.gm_table
                # GLOBAL: no scope-specific FK

                BeatCompletion.objects.create(**completion_kwargs)

        # Write-path hook: open a SessionRequest if the episode is now ready-to-run
        # and requires a GM session. Walk beat -> episode -> chapter -> story to
        # find the active progress record, then check eligibility.
        from world.stories.services.progress import get_active_progress_for_story  # noqa: PLC0415
        from world.stories.services.scheduling import maybe_create_session_request  # noqa: PLC0415

        progress = get_active_progress_for_story(story)
        if progress is not None:
            maybe_create_session_request(progress)

    return contrib


def expire_overdue_beats(now: datetime | None = None) -> int:
    """Flip outcome to EXPIRED for every UNSATISFIED beat whose deadline has passed.

    Returns count of beats expired. Idempotent — repeated calls do nothing
    to already-expired beats. Safe for a cron hook.

    No BeatCompletion row is created — expiry is system-caused and not
    attributable to a specific character. The beat's updated_at timestamp
    records when the flip happened.
    """
    from django.utils import timezone  # noqa: PLC0415

    if now is None:
        now = timezone.now()

    overdue_qs = Beat.objects.filter(
        outcome=BeatOutcome.UNSATISFIED,
        deadline__isnull=False,
        deadline__lt=now,
    )
    count = 0
    with transaction.atomic():
        for beat in overdue_qs:
            beat.outcome = BeatOutcome.EXPIRED
            beat.save(update_fields=["outcome", "updated_at"])
            count += 1
    return count


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _evaluate_and_record_beat(  # noqa: PLR0913 — scope/sheet/roster_entry/era are tightly coupled
    beat: Beat,
    progress: AnyStoryProgress,
    scope: str,
    sheet: CharacterSheet | None,
    roster_entry: RosterEntry | None,
    era: Era | None,
) -> None:
    """Evaluate a single beat within evaluate_auto_beats and record a completion if resolved.

    Called once per beat in the episode. Skips GM_MARKED and already-resolved beats.
    Must be called inside an atomic transaction (evaluate_auto_beats owns the transaction).
    """
    # GM_MARKED beats are never auto-evaluated.
    if beat.predicate_type == BeatPredicateType.GM_MARKED:
        return

    # Only transition beats that are still UNSATISFIED.
    if beat.outcome != BeatOutcome.UNSATISFIED:
        return

    # Dispatch by scope:
    #   CHARACTER + character-state predicate → evaluate against the owner's sheet.
    #   GROUP/GLOBAL + character-state predicate → ANY-member semantics
    #       (iterate active members; SUCCESS on first match).
    #   Any scope + non-character predicate (STORY_AT_MILESTONE, GM_MARKED skipped above)
    #       → evaluate via the no-sheet path.
    if scope == StoryScope.CHARACTER and sheet is not None:
        new_outcome = _evaluate_predicate(beat, cast(StoryProgress, progress))
    elif _requires_character_sheet(beat):
        new_outcome = _evaluate_predicate_any_member(beat, progress)
    else:
        new_outcome = _evaluate_predicate_no_sheet(beat)
    if new_outcome == BeatOutcome.UNSATISFIED:
        return

    # Flip the outcome in-place and persist.
    beat.outcome = new_outcome
    beat.save(update_fields=["outcome", "updated_at"])

    completion_kwargs: dict = {"beat": beat, "outcome": new_outcome, "era": era}
    if scope == StoryScope.CHARACTER and sheet is not None:
        completion_kwargs["character_sheet"] = sheet
        completion_kwargs["roster_entry"] = roster_entry
    elif scope == StoryScope.GROUP:
        completion_kwargs["gm_table"] = progress.gm_table
    # GLOBAL: no scope-specific FK

    BeatCompletion.objects.create(**completion_kwargs)


# Predicate types that require a CharacterSheet to evaluate.
_CHARACTER_SHEET_PREDICATES = {
    BeatPredicateType.CHARACTER_LEVEL_AT_LEAST,
    BeatPredicateType.ACHIEVEMENT_HELD,
    BeatPredicateType.CONDITION_HELD,
    BeatPredicateType.CODEX_ENTRY_UNLOCKED,
}


def _requires_character_sheet(beat: Beat) -> bool:
    """Return True when this beat's predicate type needs a CharacterSheet to evaluate."""
    return beat.predicate_type in _CHARACTER_SHEET_PREDICATES


def _evaluate_predicate_no_sheet(beat: Beat) -> BeatOutcome:
    """Evaluate predicates that do not require a CharacterSheet.

    Currently only STORY_AT_MILESTONE is supported here; all other types
    return UNSATISFIED (they require a character sheet and should be guarded
    by _requires_character_sheet before calling this).
    """
    if beat.predicate_type == BeatPredicateType.STORY_AT_MILESTONE:
        return _evaluate_story_at_milestone(beat)
    return BeatOutcome.UNSATISFIED


def _evaluate_predicate_any_member(beat: Beat, progress: AnyStoryProgress) -> BeatOutcome:
    """Evaluate character-state predicates for GROUP/GLOBAL scope stories.

    Semantics: "ANY active member satisfies the predicate" — iterate the
    scope's active members and short-circuit on first SUCCESS. Returns
    UNSATISFIED when no member matches.

    SUCCESS is sticky at the caller level — _evaluate_and_record_beat only
    reaches this function for beats still in UNSATISFIED state, so a
    member leaving the group after the beat flipped cannot un-flip it.

    Uses the per-sheet predicate helpers (_evaluate_achievement_held etc.)
    so the member-check logic stays consistent with CHARACTER scope.
    """
    for member_sheet in _members_for_beat(beat, progress):
        match beat.predicate_type:
            case BeatPredicateType.ACHIEVEMENT_HELD:
                if _evaluate_achievement_held(beat, member_sheet) == BeatOutcome.SUCCESS:
                    return BeatOutcome.SUCCESS
            case BeatPredicateType.CONDITION_HELD:
                if _evaluate_condition_held(beat, member_sheet) == BeatOutcome.SUCCESS:
                    return BeatOutcome.SUCCESS
            case BeatPredicateType.CODEX_ENTRY_UNLOCKED:
                if _evaluate_codex_entry_unlocked(beat, member_sheet) == BeatOutcome.SUCCESS:
                    return BeatOutcome.SUCCESS
            case BeatPredicateType.CHARACTER_LEVEL_AT_LEAST:
                if _evaluate_character_level(beat, member_sheet) == BeatOutcome.SUCCESS:
                    return BeatOutcome.SUCCESS
            case _:
                return BeatOutcome.UNSATISFIED
    return BeatOutcome.UNSATISFIED


def _members_for_beat(
    beat: Beat,
    progress: AnyStoryProgress,
) -> Iterator[CharacterSheet]:
    """Yield active member CharacterSheets for the beat's story scope.

    GROUP scope: walk progress.gm_table.memberships filtering on
        left_at__isnull=True (active) → persona → character_sheet.
    GLOBAL scope: walk the story's participants (StoryParticipation with
        is_active=True) → character (ObjectDB) → sheet_data.
    CHARACTER scope: yield the single owning sheet (progress.character_sheet).
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

    story = beat.episode.chapter.story
    match story.scope:
        case StoryScope.CHARACTER:
            if progress.character_sheet_id:
                yield progress.character_sheet
        case StoryScope.GROUP:
            table = progress.gm_table
            memberships = table.memberships.filter(left_at__isnull=True).select_related(
                "persona__character_sheet",
            )
            for membership in memberships:
                persona = membership.persona
                if persona.character_sheet_id:
                    yield persona.character_sheet
        case StoryScope.GLOBAL:
            participations = story.participants.filter(is_active=True).select_related(
                "character",
            )
            for participation in participations:
                try:
                    yield participation.character.sheet_data
                except CharacterSheet.DoesNotExist:
                    continue


def _evaluate_predicate(beat: Beat, progress: StoryProgress) -> BeatOutcome:
    """Dispatch on beat.predicate_type and return the current outcome.

    Returns UNSATISFIED when the predicate is not yet met or the type is
    unknown to this evaluator (e.g., GM_MARKED, future types).

    Note: AGGREGATE_THRESHOLD is intentionally excluded here. Aggregate beats
    are write-path-triggered: record_aggregate_contribution re-evaluates them
    directly when a contribution is recorded. They should not flip silently
    during evaluate_auto_beats, since no contribution event has fired.
    """
    ptype = beat.predicate_type
    sheet = progress.character_sheet

    if ptype == BeatPredicateType.CHARACTER_LEVEL_AT_LEAST:
        return _evaluate_character_level(beat, sheet)
    if ptype == BeatPredicateType.ACHIEVEMENT_HELD:
        return _evaluate_achievement_held(beat, sheet)
    if ptype == BeatPredicateType.CONDITION_HELD:
        return _evaluate_condition_held(beat, sheet)
    if ptype == BeatPredicateType.CODEX_ENTRY_UNLOCKED:
        return _evaluate_codex_entry_unlocked(beat, sheet)
    if ptype == BeatPredicateType.STORY_AT_MILESTONE:
        return _evaluate_story_at_milestone(beat)

    # GM_MARKED, AGGREGATE_THRESHOLD (write-path only), and future types.
    return BeatOutcome.UNSATISFIED


def _evaluate_character_level(beat: Beat, sheet: CharacterSheet) -> BeatOutcome:
    """Evaluate a CHARACTER_LEVEL_AT_LEAST predicate."""
    required = beat.required_level
    if required is None:
        # Misconfigured beat — treat as unsatisfied rather than crash.
        return BeatOutcome.UNSATISFIED
    if _character_level(sheet) >= required:
        return BeatOutcome.SUCCESS
    return BeatOutcome.UNSATISFIED


def _evaluate_achievement_held(beat: Beat, sheet: CharacterSheet) -> BeatOutcome:
    """Evaluate an ACHIEVEMENT_HELD predicate."""
    if beat.required_achievement is None:
        return BeatOutcome.UNSATISFIED
    held = sheet.cached_achievements_held
    return BeatOutcome.SUCCESS if beat.required_achievement in held else BeatOutcome.UNSATISFIED


def _evaluate_condition_held(beat: Beat, sheet: CharacterSheet) -> BeatOutcome:
    """Evaluate a CONDITION_HELD predicate."""
    if beat.required_condition_template is None:
        return BeatOutcome.UNSATISFIED
    active = sheet.cached_active_condition_templates
    if beat.required_condition_template in active:
        return BeatOutcome.SUCCESS
    return BeatOutcome.UNSATISFIED


def _evaluate_codex_entry_unlocked(beat: Beat, sheet: CharacterSheet) -> BeatOutcome:
    """Evaluate a CODEX_ENTRY_UNLOCKED predicate.

    Codex knowledge is tracked per RosterEntry (character-level ownership, not
    per-player). If the sheet has no RosterEntry, the character cannot have
    codex knowledge and the predicate is UNSATISFIED.
    """
    from world.codex.models import CharacterCodexKnowledge  # noqa: PLC0415

    if beat.required_codex_entry is None:
        return BeatOutcome.UNSATISFIED

    try:
        roster_entry = sheet.roster_entry
    except RosterEntry.DoesNotExist:
        return BeatOutcome.UNSATISFIED

    known = CharacterCodexKnowledge.objects.filter(
        roster_entry=roster_entry,
        entry=beat.required_codex_entry,
        status=CharacterCodexKnowledge.Status.KNOWN,
    ).exists()
    return BeatOutcome.SUCCESS if known else BeatOutcome.UNSATISFIED


def _evaluate_story_at_milestone(beat: Beat) -> BeatOutcome:
    """Evaluate a STORY_AT_MILESTONE predicate.

    Dispatches on beat.referenced_milestone_type to per-milestone helpers.
    """
    from world.stories.services.progress import get_active_progress_for_story  # noqa: PLC0415

    if beat.referenced_story is None:
        return BeatOutcome.UNSATISFIED

    milestone = beat.referenced_milestone_type

    if milestone == StoryMilestoneType.STORY_RESOLVED:
        return _milestone_story_resolved(beat)

    progress = get_active_progress_for_story(beat.referenced_story)
    if progress is None or progress.current_episode is None:
        return BeatOutcome.UNSATISFIED

    if milestone == StoryMilestoneType.CHAPTER_REACHED:
        return _milestone_chapter_reached(beat, progress.current_episode)
    if milestone == StoryMilestoneType.EPISODE_REACHED:
        return _milestone_episode_reached(beat, progress.current_episode)

    return BeatOutcome.UNSATISFIED


def _milestone_story_resolved(beat: Beat) -> BeatOutcome:
    """Check whether beat.referenced_story has COMPLETED status."""
    return (
        BeatOutcome.SUCCESS
        if beat.referenced_story.status == StoryStatus.COMPLETED
        else BeatOutcome.UNSATISFIED
    )


def _milestone_chapter_reached(beat: Beat, current_episode: Episode) -> BeatOutcome:
    """Check whether the current episode is at or past beat.referenced_chapter."""
    if beat.referenced_chapter is None:
        return BeatOutcome.UNSATISFIED
    current_chapter = current_episode.chapter
    if current_chapter.story_id != beat.referenced_chapter.story_id:
        return BeatOutcome.UNSATISFIED
    return (
        BeatOutcome.SUCCESS
        if current_chapter.order >= beat.referenced_chapter.order
        else BeatOutcome.UNSATISFIED
    )


def _milestone_episode_reached(beat: Beat, current_episode: Episode) -> BeatOutcome:
    """Check whether the current episode is at or past beat.referenced_episode."""
    if beat.referenced_episode is None:
        return BeatOutcome.UNSATISFIED
    current_chapter = current_episode.chapter
    ref_chapter = beat.referenced_episode.chapter
    if current_chapter.story_id != ref_chapter.story_id:
        return BeatOutcome.UNSATISFIED
    if current_chapter.order > ref_chapter.order:
        return BeatOutcome.SUCCESS
    if current_chapter.order == ref_chapter.order:
        return (
            BeatOutcome.SUCCESS
            if current_episode.order >= beat.referenced_episode.order
            else BeatOutcome.UNSATISFIED
        )
    return BeatOutcome.UNSATISFIED


def _evaluate_aggregate_beat(beat: Beat) -> BeatOutcome:
    """Evaluate an AGGREGATE_THRESHOLD beat by summing its contribution ledger.

    Used exclusively by record_aggregate_contribution. Does not require a
    StoryProgress argument because aggregate beats read the ledger directly.
    """
    if beat.required_points is None:
        return BeatOutcome.UNSATISFIED
    total = AggregateBeatContribution.objects.total_for_beat(beat)
    return BeatOutcome.SUCCESS if total >= beat.required_points else BeatOutcome.UNSATISFIED


def _character_level(sheet: CharacterSheet) -> int:
    """Return the character's current level.

    Delegates to ``CharacterSheet.current_level`` which is a cached_property
    walking ``CharacterClassLevel`` records. First call populates the cache;
    repeat calls within the same request/transaction are free.
    """
    return sheet.current_level


def _current_roster_entry(sheet: CharacterSheet) -> RosterEntry | None:
    """Return the RosterEntry for this sheet, or None if one doesn't exist.

    RosterEntry is OneToOne to CharacterSheet (via character_sheet FK on
    RosterEntry), accessible as sheet.roster_entry via the reverse relation.
    Returns None when no RosterEntry has been created (valid for test/NPC
    characters that haven't gone through the roster workflow).
    """
    try:
        return sheet.roster_entry
    except RosterEntry.DoesNotExist:
        return None
