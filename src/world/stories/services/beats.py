"""Beat evaluation service for the stories system.

Public API:
    evaluate_auto_beats(progress) — re-evaluates all auto-detected beats in the
        progress's current episode, recording BeatCompletion rows for any that
        transition from UNSATISFIED to a resolved outcome.

    record_gm_marked_outcome(*, progress, beat, outcome, gm_notes) — GM's manual
        call to mark a GM_MARKED beat with SUCCESS or FAILURE.
"""

from world.character_sheets.models import CharacterSheet
from world.classes.models import CharacterClassLevel
from world.roster.models import RosterEntry
from world.stories.constants import BeatOutcome, BeatPredicateType, EraStatus
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
    era = _get_active_era()
    roster_entry = _current_roster_entry(sheet)

    beats = Beat.objects.filter(episode=progress.current_episode)
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
    era = _get_active_era()
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
    if beat.predicate_type == BeatPredicateType.CHARACTER_LEVEL_AT_LEAST:
        required = beat.required_level
        if required is None:
            # Misconfigured beat — treat as unsatisfied rather than crash.
            return BeatOutcome.UNSATISFIED
        if _character_level(progress.character_sheet) >= required:
            return BeatOutcome.SUCCESS
        return BeatOutcome.UNSATISFIED

    # GM_MARKED and any future types not handled here.
    return BeatOutcome.UNSATISFIED


def _character_level(sheet: CharacterSheet) -> int:
    """Return the character's current level via the classes system.

    Level is defined as the highest level held across all of the character's
    CharacterClassLevel records.  Returns 0 if the character has no class
    assignments (e.g. freshly created test characters).

    CharacterSheet shares its pk with ObjectDB (primary_key=True on the
    OneToOne), so sheet.character is the ObjectDB used by CharacterClassLevel.
    """
    result = (
        CharacterClassLevel.objects.filter(character=sheet.character)
        .order_by("-level")
        .values_list("level", flat=True)
        .first()
    )
    return int(result) if result is not None else 0


def _get_active_era() -> Era | None:
    """Return the currently active Era, or None if none is active."""
    return Era.objects.filter(status=EraStatus.ACTIVE).first()


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
