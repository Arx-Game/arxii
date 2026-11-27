"""Test-only helpers for forcing CheckOutcomes in pipeline tests.

NOT a production code path. ``perform_check`` reads the thread-local
override (set by ``force_check_outcome``) and clears it on first use;
the context manager yields a CheckCapture object the test can inspect
to verify what ``check_type``, ``target_difficulty``, skill terms and
``extra_modifiers`` perform_check was about to use. ``CheckCapture.calls``
keeps one entry per ``perform_check`` call, so a test can count the rolls an
act made and read each one's skill terms (#5308).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from world.character_sheets.models import CharacterSheet
    from world.checks.models import CheckType
    from world.checks.types import ExtraTraitTerm
    from world.traits.models import CheckOutcome


_local = threading.local()


def make_player_character(sheet: CharacterSheet) -> CharacterSheet:
    """Give ``sheet`` an open tenure on a roster entry, so it is a player character.

    ``is_player_character`` holds for a sheet held by an account, whatever the player's
    connection state (#4091). Tests that need a character to count as a PC for an obstacle
    or resist (#5093) use this; a bare ``CharacterSheetFactory`` sheet is an NPC.
    """
    from world.roster.factories import RosterEntryFactory, RosterTenureFactory

    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(roster_entry=entry, end_date=None)
    return sheet


@dataclass(frozen=True)
class CheckCall:
    """The inputs of one ``perform_check`` call, as it was about to use them."""

    check_type: CheckType
    target_difficulty: int | None
    extra_traits: tuple[ExtraTraitTerm, ...]
    extra_modifiers: int | None
    stat_override: str | int | None


@dataclass
class CheckCapture:
    """Records the inputs perform_check was about to use.

    The scalar fields hold the LAST call's inputs; ``calls`` holds every call in order.
    """

    check_type: CheckType | None = None
    target_difficulty: int | None = None
    extra_traits: tuple[ExtraTraitTerm, ...] = ()
    extra_modifiers: int | None = None
    calls: list[CheckCall] = field(default_factory=list)


def _consume_forced_outcome() -> CheckOutcome | None:
    """Read and clear the next thread-local outcome override. Returns None if none left.

    A queue (``force_check_outcome(first, second, ...)``) hands its outcomes out one per
    call; once it is empty, a ``force_every_check_outcome`` outcome, if one is set, answers
    every call after.
    """
    # The attrs are absent until a force context sets them, so read the instance dict.
    state = _local.__dict__
    queue: deque[CheckOutcome] | None = state.get("forced_queue")
    if queue:
        return queue.popleft()
    return state.get("forced_every")


def _record_capture(
    *,
    check_type: CheckType,
    target_difficulty: int | None,
    extra_traits: Sequence[ExtraTraitTerm] = (),
    extra_modifiers: int | None = None,
    stat_override: str | int | None = None,
) -> None:
    """Write into the active CheckCapture, if any. No-op outside a force context."""
    # Suppression justified: threading.local attr absent until a force context sets it.
    capture: CheckCapture | None = getattr(_local, "capture", None)  # noqa: GETATTR_LITERAL
    if capture is not None:
        capture.check_type = check_type
        capture.target_difficulty = target_difficulty
        capture.extra_traits = tuple(extra_traits)
        capture.extra_modifiers = extra_modifiers
        capture.calls.append(
            CheckCall(
                check_type=check_type,
                target_difficulty=target_difficulty,
                extra_traits=tuple(extra_traits),
                extra_modifiers=extra_modifiers,
                stat_override=stat_override,
            )
        )


@contextmanager
def force_check_outcome(outcome: CheckOutcome, *later: CheckOutcome) -> Iterator[CheckCapture]:
    """Force the NEXT perform_check call to return a CheckResult whose
    ``outcome`` field equals ``outcome``. Yields a CheckCapture that
    records ``check_type`` and ``target_difficulty`` as the call was
    about to use them.

    Single-shot: perform_check consumes the override on first call.
    Subsequent perform_check calls in the same context manager run
    real resolution (the capture object is still updated, though).

    Extra outcomes (``force_check_outcome(first, second)``) queue: the calls take them in
    order, one each, and the call after the last runs real resolution (#5308). The
    capture's ``calls`` lists every call, forced or not.

    NOT a production code path; thread-local only.
    """
    capture = CheckCapture()
    _local.forced_queue = deque((outcome, *later))
    _local.forced_every = None
    _local.capture = capture
    try:
        yield capture
    finally:
        _local.forced_queue = None
        _local.forced_every = None
        _local.capture = None


@contextmanager
def force_every_check_outcome(outcome: CheckOutcome) -> Iterator[CheckCapture]:
    """Force EVERY perform_check call in the context to return ``outcome``.

    For an act whose number of rolls is the thing under test, so no roll is left to the dice.
    Yields the same CheckCapture as ``force_check_outcome``. NOT a production code path;
    thread-local only.
    """
    capture = CheckCapture()
    _local.forced_queue = None
    _local.forced_every = outcome
    _local.capture = capture
    try:
        yield capture
    finally:
        _local.forced_every = None
        _local.capture = None


class SeededLevelLadderMixin:
    """Mixin for a ``TestCase`` whose rolls read an authored difficulty level (#5093).

    An authored difficulty is a level, and a level's points are its CHECK baseline row. A test
    database has no rows until something seeds them, and a database with none reads every
    difficulty as 0. Put this ahead of ``TestCase`` to get the seeded ladder (level 1 is 18
    points, each level 8 wider) before the class's own ``setUpTestData``.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        from world.traits.factories import ensure_level_ladder

        super().setUpTestData()  # ty: ignore[unresolved-attribute] - mixed in ahead of TestCase
        ensure_level_ladder()
