"""In-memory transient stores (no DB): anti-spam floor + pending soulfray cast."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

_LAST_ACTED: dict[int, float] = {}


def check_anti_spam(sheet_pk: int, seconds: int) -> float | None:
    """Return remaining cooldown seconds if still cooling down, else None."""
    last = _LAST_ACTED.get(sheet_pk)
    if last is None:
        return None
    remaining = seconds - (time.monotonic() - last)
    return remaining if remaining > 0 else None


def mark_acted(sheet_pk: int) -> None:
    _LAST_ACTED[sheet_pk] = time.monotonic()


@dataclass
class PendingCast:
    technique_id: int
    target_persona_id: int | None
    kwargs: dict[str, Any]


_PENDING: dict[int, PendingCast] = {}


def register_pending(sheet_pk: int, pending: PendingCast) -> None:
    _PENDING[sheet_pk] = pending


def pop_pending(sheet_pk: int) -> PendingCast | None:
    return _PENDING.pop(sheet_pk, None)


def peek_pending(sheet_pk: int) -> PendingCast | None:
    return _PENDING.get(sheet_pk)
