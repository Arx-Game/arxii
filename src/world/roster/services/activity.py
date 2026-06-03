"""Player inactivity-detection service surface (#671).

Holds the weekly cron sweep that flips ``CharacterSheet.activity_state`` based
on the computed ``decay_tier``, plus the four player-action services
(``declare_hiatus`` / ``end_hiatus`` / ``freeze_character`` /
``unfreeze_character``) and the staff/player lifecycle setter.

The weekly cron is registered in ``world.game_clock.tasks``. Player-action
services are wired into views / commands at the call-site layer.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet


# 30-day cooldown floor on OC freeze/thaw swaps.
FREEZE_COOLDOWN_DAYS = 30

# Maximum hiatus length players can self-declare (1 IRL year).
MAX_HIATUS_DAYS = 365


class InactivityServiceError(Exception):
    """Base class for inactivity-service exceptions.

    Subclasses carry a ``user_message`` attribute so view layers can surface
    a player-friendly string without exposing internal IDs / state.
    """

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


class HiatusError(InactivityServiceError):
    """Hiatus declaration or end is invalid."""


class FreezeError(InactivityServiceError):
    """Freeze or unfreeze action is invalid."""


class LifecycleStateError(InactivityServiceError):
    """Invalid lifecycle_state transition."""


def sweep_activity_states() -> dict[str, int]:
    """Weekly: walk eligible sheets and flip ``activity_state`` per signal.

    Flips:
      * ``ACTIVE → INACTIVE`` when ``decay_tier`` is INACTIVE or higher.
      * ``INACTIVE → ACTIVE`` when the signal recovers (``decay_tier`` is None
        or RECENT_INACTIVE).
      * ``HIATUS → ACTIVE`` when ``activity_state_until`` has passed.

    ``FROZEN`` is never touched by cron — only the player-action services
    ``freeze_character`` / ``unfreeze_character`` mutate it, and the cooldown
    is enforced on demand by ``unfreeze_character``.

    Returns a small telemetry dict so the scheduler can log per-tick volume.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.character_sheets.types import ActivityState, DecayTier  # noqa: PLC0415
    from world.roster.models.choices import ActivityRequirement  # noqa: PLC0415

    flipped_to_inactive = 0
    flipped_to_active = 0
    hiatus_expired = 0

    now = timezone.now()
    qs = CharacterSheet.objects.filter(
        roster_entry__roster__activity_requirement__in=[
            ActivityRequirement.HIGH,
            ActivityRequirement.LOW,
        ]
    ).select_related("roster_entry__roster")

    inactive_tiers = {
        DecayTier.INACTIVE,
        DecayTier.LONG_INACTIVE,
        DecayTier.DORMANT,
    }

    for sheet in qs.iterator(chunk_size=500):
        if sheet.activity_state == ActivityState.HIATUS:
            if sheet.activity_state_until is not None and now > sheet.activity_state_until:
                _set_active(sheet)
                hiatus_expired += 1
            continue

        if sheet.activity_state == ActivityState.FROZEN:
            continue

        tier = sheet.decay_tier
        is_inactive_tier = tier in inactive_tiers

        if sheet.activity_state == ActivityState.ACTIVE and is_inactive_tier:
            sheet.activity_state = ActivityState.INACTIVE
            sheet.save(update_fields=["activity_state", "updated_date"])
            flipped_to_inactive += 1
        elif sheet.activity_state == ActivityState.INACTIVE and not is_inactive_tier:
            _set_active(sheet)
            flipped_to_active += 1

    return {
        "flipped_to_inactive": flipped_to_inactive,
        "flipped_to_active": flipped_to_active,
        "hiatus_expired": hiatus_expired,
    }


def declare_hiatus(sheet: CharacterSheet, end_date: datetime) -> None:
    """Player declares an IRL absence; ``activity_state -> HIATUS until end_date``.

    Raises ``HiatusError`` if ``end_date`` is not in the future or exceeds
    ``MAX_HIATUS_DAYS`` (sanity cap).
    """
    from world.character_sheets.types import ActivityState  # noqa: PLC0415

    now = timezone.now()
    if end_date <= now:
        msg = f"Hiatus end_date {end_date} is not in the future."
        raise HiatusError(msg, user_message="Hiatus end date must be in the future.")

    max_end = now + timedelta(days=MAX_HIATUS_DAYS)
    if end_date > max_end:
        msg = f"Hiatus end_date {end_date} exceeds {MAX_HIATUS_DAYS}-day cap."
        raise HiatusError(
            msg,
            user_message=f"Hiatus cannot exceed {MAX_HIATUS_DAYS} days.",
        )

    with transaction.atomic():
        sheet.activity_state = ActivityState.HIATUS
        sheet.activity_state_until = end_date
        sheet.save(update_fields=["activity_state", "activity_state_until", "updated_date"])


def end_hiatus(sheet: CharacterSheet) -> None:
    """Early-return from hiatus. ``activity_state -> ACTIVE``."""
    from world.character_sheets.types import ActivityState  # noqa: PLC0415

    if sheet.activity_state != ActivityState.HIATUS:
        msg = f"Character {sheet.pk} is not on HIATUS (current: {sheet.activity_state})."
        raise HiatusError(msg, user_message="Character is not on hiatus.")
    _set_active(sheet)


def freeze_character(sheet: CharacterSheet) -> None:
    """Mark an OC FROZEN with a 30-day cooldown.

    Raises ``FreezeError`` if the sheet is not an OC, not currently ACTIVE,
    or not currently ALIVE. The OC cap is enforced at OC creation time, not
    here — freezing a character FREES the slot, it doesn't take one.
    """
    from world.character_sheets.types import ActivityState, LifecycleState  # noqa: PLC0415

    if not sheet.is_oc:
        msg = f"Character {sheet.pk} is not an OC; cannot freeze."
        raise FreezeError(msg, user_message="Only OCs can be frozen.")
    if sheet.activity_state != ActivityState.ACTIVE:
        msg = f"Character {sheet.pk} is not ACTIVE (current: {sheet.activity_state})."
        raise FreezeError(msg, user_message="Only active characters can be frozen.")
    if sheet.lifecycle_state != LifecycleState.ALIVE:
        msg = f"Character {sheet.pk} is not ALIVE (current: {sheet.lifecycle_state})."
        raise FreezeError(msg, user_message="Only living characters can be frozen.")

    now = timezone.now()
    with transaction.atomic():
        sheet.activity_state = ActivityState.FROZEN
        sheet.activity_state_until = now + timedelta(days=FREEZE_COOLDOWN_DAYS)
        sheet.save(update_fields=["activity_state", "activity_state_until", "updated_date"])


def unfreeze_character(sheet: CharacterSheet) -> None:
    """Thaw a frozen character; enforces the 30-day cooldown floor.

    Raises ``FreezeError`` if the sheet is not FROZEN or if the cooldown
    has not yet expired.
    """
    from world.character_sheets.types import ActivityState  # noqa: PLC0415

    if sheet.activity_state != ActivityState.FROZEN:
        msg = f"Character {sheet.pk} is not FROZEN (current: {sheet.activity_state})."
        raise FreezeError(msg, user_message="Character is not frozen.")

    now = timezone.now()
    if sheet.activity_state_until is not None and now < sheet.activity_state_until:
        days_remaining = (sheet.activity_state_until - now).days
        msg = f"Character {sheet.pk} cooldown not yet expired ({days_remaining} days remaining)."
        raise FreezeError(
            msg,
            user_message=f"Cannot thaw for {days_remaining} more days.",
        )
    _set_active(sheet)


def set_lifecycle_state(
    sheet: CharacterSheet,
    state: str,
    *,
    actor: object | None = None,  # noqa: ARG001
) -> None:
    """Set ``lifecycle_state`` on a sheet.

    ``actor`` is reserved for permission checks (staff-authoritative for
    CAPTURED/COMA/DEAD; player-authoritative for RETIRED on their own OCs).
    Permission enforcement lives in the view layer for now — this service
    is the atomic write.
    """
    from world.character_sheets.types import LifecycleState  # noqa: PLC0415

    if state not in LifecycleState.values:
        msg = f"Invalid lifecycle_state {state!r}"
        raise LifecycleStateError(msg, user_message=f"Invalid lifecycle state: {state}")

    now = timezone.now()
    with transaction.atomic():
        sheet.lifecycle_state = state
        sheet.lifecycle_state_at = now
        sheet.save(update_fields=["lifecycle_state", "lifecycle_state_at", "updated_date"])


def _set_active(sheet: CharacterSheet) -> None:
    """Reset activity_state to ACTIVE and clear the state-until timestamp."""
    from world.character_sheets.types import ActivityState  # noqa: PLC0415

    sheet.activity_state = ActivityState.ACTIVE
    sheet.activity_state_until = None
    sheet.save(update_fields=["activity_state", "activity_state_until", "updated_date"])
