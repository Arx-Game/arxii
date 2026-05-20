"""Test-only helpers for forcing CheckOutcomes in pipeline tests.

NOT a production code path. ``perform_check`` reads the thread-local
override (set by ``force_check_outcome``) and clears it on first use;
the context manager yields a CheckCapture object the test can inspect
to verify what ``check_type`` and ``target_difficulty`` perform_check
was about to use.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.checks.models import CheckType
    from world.traits.models import CheckOutcome


_local = threading.local()


@dataclass
class CheckCapture:
    """Records the inputs perform_check was about to use."""

    check_type: CheckType | None = None
    target_difficulty: int | None = None


def _consume_forced_outcome() -> CheckOutcome | None:
    """Read and clear the thread-local outcome override. Returns None if none active."""
    outcome = getattr(_local, "forced_outcome", None)  # noqa: GETATTR_LITERAL — threading.local has no typed attrs; getattr+default is the idiomatic API
    _local.forced_outcome = None
    return outcome


def _record_capture(*, check_type: CheckType, target_difficulty: int | None) -> None:
    """Write into the active CheckCapture, if any. No-op outside a force context."""
    capture: CheckCapture | None = getattr(_local, "capture", None)  # noqa: GETATTR_LITERAL — threading.local has no typed attrs; getattr+default is the idiomatic API
    if capture is not None:
        capture.check_type = check_type
        capture.target_difficulty = target_difficulty


@contextmanager
def force_check_outcome(outcome: CheckOutcome) -> Iterator[CheckCapture]:
    """Force the NEXT perform_check call to return a CheckResult whose
    ``outcome`` field equals ``outcome``. Yields a CheckCapture that
    records ``check_type`` and ``target_difficulty`` as the call was
    about to use them.

    Single-shot: perform_check consumes the override on first call.
    Subsequent perform_check calls in the same context manager run
    real resolution (the capture object is still updated, though).

    NOT a production code path; thread-local only.
    """
    capture = CheckCapture()
    _local.forced_outcome = outcome
    _local.capture = capture
    try:
        yield capture
    finally:
        _local.forced_outcome = None
        _local.capture = None
