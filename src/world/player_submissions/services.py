"""Error-capture services (#1164) — the bespoke, no-SaaS error path.

``run_safely`` is the boundary for optional / best-effort work: run it, and on failure
capture a deduplicated ``SystemErrorReport`` (so a real fault reaches staff with a traceback
instead of vanishing into the logs) and tell the actor — instead of silently swallowing the
error or letting it break the player's action. Replaces the ad-hoc
``try/except Exception: logger.exception`` blocks (#1162/#1163).
"""

from __future__ import annotations

import hashlib
import logging
import traceback as traceback_module
from typing import TYPE_CHECKING, cast

from django.utils import timezone

from world.player_submissions.models import SystemErrorReport

if TYPE_CHECKING:
    from collections.abc import Callable

    from evennia.objects.models import ObjectDB

    from typeclasses.characters import Character

logger = logging.getLogger(__name__)

# Shown to a player whose action hit an unexpected error. Functional UI string.
PLAYER_ERROR_MESSAGE = (
    "An unexpected error has occurred. Staff has been notified, but please feel free to "
    "leave a bug report under the account menu."
)


def run_safely(label: str, fn: Callable[[], object], *, actor: ObjectDB | None = None) -> object:
    """Run an optional / best-effort callable; on failure capture + notify, never raise.

    Returns ``fn()``'s result, or ``None`` if it raised. A raised exception is captured as a
    deduplicated ``SystemErrorReport`` (visible to staff) and, when ``actor`` is given, the
    generic error line is surfaced to that player — so the failure is neither swallowed
    silently nor allowed to break the player's primary action.
    """
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — this IS the central catch-all boundary, by design
        report_error(exc, label=label, actor=actor)
        if actor is not None:
            _notify_actor(actor)
        return None


def report_error(exc: BaseException, *, label: str, actor: ObjectDB | None = None) -> None:
    """Capture an exception as a deduplicated ``SystemErrorReport`` + a structured log.

    Must never raise — it is the last line of defense. Dedup is by a signature over the
    exception type and the deepest in-app frame, so repeats increment a count instead of
    spawning rows.
    """
    logger.exception("Captured error in %s", label)
    try:
        tb_text = "".join(traceback_module.format_exception(type(exc), exc, exc.__traceback__))
        signature = _signature(exc, label)
        report, created = SystemErrorReport.objects.get_or_create(
            signature=signature,
            defaults={
                "label": label[:200],
                "exception_type": type(exc).__name__[:200],
                "message": str(exc)[:2000],
                "traceback": tb_text,
                "actor_persona": _persona_for(actor),
            },
        )
        if not created:
            # Read-modify-write via save() (not F()+update()) so the cached
            # SharedMemoryModel instance stays in sync — an F-expression .update()
            # leaves later reads of this row stale (idmapper).
            report.occurrence_count += 1
            report.last_seen = timezone.now()
            report.save(update_fields=["occurrence_count", "last_seen"])
    except Exception:
        logger.exception("Failed to record SystemErrorReport for %s", label)


def _notify_actor(actor: ObjectDB) -> None:
    """Push the generic error line to the player; never raise."""
    try:
        actor.msg(PLAYER_ERROR_MESSAGE)
    except Exception:
        logger.exception("Failed to notify actor of error")


def _signature(exc: BaseException, label: str) -> str:
    """Dedup hash: exception type + the deepest frame inside our codebase (else the label)."""
    frame_id = label
    tb = exc.__traceback__
    while tb is not None:
        if "/src/" in tb.tb_frame.f_code.co_filename:
            frame_id = f"{tb.tb_frame.f_code.co_filename.split('/src/')[-1]}:{tb.tb_lineno}"
        tb = tb.tb_next
    return hashlib.sha256(f"{type(exc).__name__}|{frame_id}".encode()).hexdigest()[:64]


def _persona_for(actor: ObjectDB | None) -> object | None:
    """Best-effort presented persona for the actor, or ``None``."""
    if actor is None:
        return None
    try:
        from world.scenes.services import persona_for_character  # noqa: PLC0415

        return persona_for_character(cast("Character", actor))
    except Exception:  # noqa: BLE001 — persona resolution is best-effort context only
        return None
