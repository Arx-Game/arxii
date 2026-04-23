"""Beat evaluation service for the stories system.

Public API:
    evaluate_auto_beats(progress) — re-evaluates all auto-detected beats in the
        progress's current episode, recording BeatCompletion rows for any that
        transition from UNSATISFIED to a resolved outcome.

    record_gm_marked_outcome(*, progress, beat, outcome, gm_notes) — GM's manual
        call to mark a GM_MARKED beat with SUCCESS or FAILURE.
"""

from django.db import transaction

from world.character_sheets.models import CharacterSheet
from world.roster.models import RosterEntry
from world.stories.constants import BeatOutcome, BeatPredicateType
from world.stories.exceptions import BeatNotResolvableError
from world.stories.models import Beat, BeatCompletion, Era, StoryProgress


def evaluate_auto_beats(progress: StoryProgress) -> None:
    """Re-evaluate all auto-detectable beats in the progress's current episode.

    For each beat whose predicate_type is not GM_MARKED:
        - Evaluate the predicate against the progress's character.
        - If the beat is currently UNSATISFIED and the predicate now yields a
          resolved outcome (SUCCESS / FAILURE / EXPIRED), flip the outcome
          in-place and write a BeatCompletion row.

    GM_MARKED beats are left completely untouched — they require an explicit
    ``record_gm_marked_outcome`` call.

    Does nothing and returns cleanly when ``progress.current_episode`` is None.
    """
    if progress.current_episode is None:
        return

    sheet: CharacterSheet = progress.character_sheet

    era = Era.objects.get_active()
    roster_entry = _current_roster_entry(sheet)

    beats = Beat.objects.filter(episode=progress.current_episode)
    with transaction.atomic():
        for beat in beats:
            # GM_MARKED beats are never auto-evaluated.
            if beat.predicate_type == BeatPredicateType.GM_MARKED:
                continue

            # Only transition beats that are still UNSATISFIED.
            if beat.outcome != BeatOutcome.UNSATISFIED:
                continue

            new_outcome = _evaluate_predicate(beat, progress)
            if new_outcome == BeatOutcome.UNSATISFIED:
                continue

            # Flip the outcome in-place and persist.
            beat.outcome = new_outcome
            beat.save(update_fields=["outcome", "updated_at"])

            BeatCompletion.objects.create(
                beat=beat,
                character_sheet=sheet,
                roster_entry=roster_entry,
                outcome=new_outcome,
                era=era,
            )


def record_gm_marked_outcome(
    *,
    progress: StoryProgress,
    beat: Beat,
    outcome: BeatOutcome,
    gm_notes: str = "",
) -> BeatCompletion:
    """Record a GM's manual outcome on a GM_MARKED beat.

    Validates:
        - beat.predicate_type == GM_MARKED  (else BeatNotResolvableError)
        - outcome in {SUCCESS, FAILURE}      (else BeatNotResolvableError)

    Flips beat.outcome in-place, creates and returns a BeatCompletion row.
    """
    if beat.predicate_type != BeatPredicateType.GM_MARKED:
        msg = (
            f"Beat {beat.pk} is not GM_MARKED (type={beat.predicate_type}); "
            "only GM_MARKED beats can be resolved via record_gm_marked_outcome."
        )
        raise BeatNotResolvableError(msg)

    _VALID_GM_OUTCOMES = {BeatOutcome.SUCCESS, BeatOutcome.FAILURE}
    if outcome not in _VALID_GM_OUTCOMES:
        msg = (
            f"Outcome {outcome!r} is not valid for a GM-marked resolution; "
            f"must be one of {_VALID_GM_OUTCOMES}."
        )
        raise BeatNotResolvableError(msg)

    sheet: CharacterSheet = progress.character_sheet
    era = Era.objects.get_active()
    roster_entry = _current_roster_entry(sheet)

    # Flip the outcome in-place and persist.
    beat.outcome = outcome
    beat.save(update_fields=["outcome", "updated_at"])

    return BeatCompletion.objects.create(
        beat=beat,
        character_sheet=sheet,
        roster_entry=roster_entry,
        outcome=outcome,
        era=era,
        gm_notes=gm_notes,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _evaluate_predicate(beat: Beat, progress: StoryProgress) -> BeatOutcome:
    """Dispatch on beat.predicate_type and return the current outcome.

    Returns UNSATISFIED when the predicate is not yet met or the type is
    unknown to this evaluator (e.g., GM_MARKED, future types).
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

    # GM_MARKED and any future types not handled here.
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
