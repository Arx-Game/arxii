"""The one-band difficulty shift a GM may apply, with a required reason.

Two GM surfaces adapt an authored difficulty by exactly one band and must state
why: ``InvokeCatalogCheckAction`` shifts a ``DifficultyChoice`` *band* it was
handed (#2118), and ``PlaceChallengeAction`` shifts an authored
``ChallengeTemplate.severity`` expressed in ``DIFFICULTY_VALUES`` *points*
(#2865). Both live here so the bound checks, the mutual-exclusion rule, and the
refusal wording cannot drift apart.

The invariant both share (ADR-0110): **at most one band, never an arbitrary
offset, and never silently clamped.** A shift that would run off either end of
the authored table is refused, not squashed back to the edge — a GM asking for
"harder than Harrowing" is asking for something the catalog does not express.
"""

from __future__ import annotations

from actions.types import ActionResult
from world.scenes.action_constants import (
    DIFFICULTY_BAND_STEP,
    DIFFICULTY_VALUES,
    MAX_DIFFICULTY_POINTS,
    MIN_DIFFICULTY_POINTS,
    DifficultyChoice,
)

# Ascending TRIVIAL..HARROWING order -- DIFFICULTY_VALUES is authored in this order
# and dicts preserve insertion order, so this is the single source of truth for
# "one band up/down" shifts.
DIFFICULTY_ORDER: tuple[str, ...] = tuple(DIFFICULTY_VALUES.keys())

#: Points -> band, for labelling a severity that lands exactly on an authored band.
_POINTS_TO_BAND: dict[int, str] = {points: band for band, points in DIFFICULTY_VALUES.items()}

ERR_BOTH_REASONS = "Shift with edge or setback, not both."
ERR_ALREADY_EASIEST = "Already at the easiest band."
ERR_ALREADY_HARDEST = "Already at the hardest band."


def difficulty_label(points: int) -> str:
    """Human label for a difficulty expressed in points.

    Authored content sits on the band values, so this usually reads
    ``"Hard"``; a value between bands falls back to the raw number rather than
    rounding to a band it isn't.
    """
    band = _POINTS_TO_BAND.get(points)
    return DifficultyChoice(band).label if band is not None else f"difficulty {points}"


def shift_band(band: str, *, easier: bool) -> str | None:
    """Shift *band* exactly one step toward TRIVIAL (easier) or HARROWING (harder).

    Returns ``None`` when the shift would go out of bounds -- callers must refuse
    rather than clamp.
    """
    index = DIFFICULTY_ORDER.index(band)
    new_index = index - 1 if easier else index + 1
    if new_index < 0 or new_index >= len(DIFFICULTY_ORDER):
        return None
    return DIFFICULTY_ORDER[new_index]


def _shift_direction(edge_reason: str, setback_reason: str) -> bool | None | ActionResult:
    """Return ``True`` (easier), ``False`` (harder), ``None`` (no shift), or a refusal."""
    if edge_reason and setback_reason:
        return ActionResult(success=False, message=ERR_BOTH_REASONS)
    if edge_reason:
        return True
    if setback_reason:
        return False
    return None


def resolve_band_shift(
    difficulty: str, edge_reason: str, setback_reason: str
) -> tuple[str, str] | ActionResult:
    """Return ``(effective_band, shift_note)`` for *difficulty*, or a failure result."""
    direction = _shift_direction(edge_reason, setback_reason)
    if isinstance(direction, ActionResult):
        return direction
    if direction is None:
        return difficulty, ""

    shifted = shift_band(difficulty, easier=direction)
    if shifted is None:
        return ActionResult(
            success=False,
            message=ERR_ALREADY_EASIEST if direction else ERR_ALREADY_HARDEST,
        )
    label = DifficultyChoice(shifted).label
    reason = edge_reason if direction else setback_reason
    marker = "edge" if direction else "setback"
    return shifted, f" [{marker} -> {label}: {reason}]"


def resolve_severity_shift(
    severity: int, edge_reason: str, setback_reason: str
) -> tuple[int, str, str] | ActionResult:
    """Return ``(adjustment, reason, shift_note)`` for a points *severity*.

    ``adjustment`` is the signed ``DIFFICULTY_BAND_STEP`` delta to persist on
    ``ChallengeInstance.severity_adjustment`` (0 when no shift was asked for),
    and ``reason`` is the GM's stated why (empty only when ``adjustment`` is 0) —
    the pair the model's ``challenge_instance_adjustment_needs_reason``
    constraint enforces together.
    """
    direction = _shift_direction(edge_reason, setback_reason)
    if isinstance(direction, ActionResult):
        return direction
    if direction is None:
        return 0, "", ""

    adjustment = -DIFFICULTY_BAND_STEP if direction else DIFFICULTY_BAND_STEP
    shifted = severity + adjustment
    if shifted < MIN_DIFFICULTY_POINTS or shifted > MAX_DIFFICULTY_POINTS:
        return ActionResult(
            success=False,
            message=ERR_ALREADY_EASIEST if direction else ERR_ALREADY_HARDEST,
        )
    reason = edge_reason if direction else setback_reason
    marker = "edge" if direction else "setback"
    return adjustment, reason, f" [{marker} -> {difficulty_label(shifted)}: {reason}]"
