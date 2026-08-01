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
from django.db.models import Prefetch
from django.utils import timezone

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.roster.models import Roster, RosterEntry


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


def current_roster_entry(sheet: CharacterSheet) -> RosterEntry | None:
    """The RosterEntry for this sheet, or None when one doesn't exist.

    RosterEntry is OneToOne to CharacterSheet, accessible as
    ``sheet.roster_entry`` via the reverse relation. Returns None when no
    RosterEntry has been created (valid for test/NPC characters that haven't
    gone through the roster workflow). The public lookup consumed by
    stories' beat-completion attribution and the stakes pillar-12
    player-held gate.
    """
    from world.roster.models import RosterEntry  # noqa: PLC0415

    try:
        return sheet.roster_entry
    except RosterEntry.DoesNotExist:
        return None


def _inactive_tiers() -> frozenset[str]:
    """Tiers at or past the 30-day bar at which a character is marked INACTIVE.

    RECENT_INACTIVE (14d) is deliberately absent — it is a scheduling signal
    ("is anyone even a little inactive?") and flips nothing (#2728 §3).
    """
    from world.character_sheets.types import DecayTier  # noqa: PLC0415

    return frozenset(
        {
            DecayTier.SHORT_INACTIVE,
            DecayTier.LONG_INACTIVE,
            DecayTier.DORMANT,
        },
    )


def sweep_activity_states() -> dict[str, int]:
    """Weekly: demote characters who have stopped showing up, and release them.

    **Demotion only** (#2728 §6). Promotion is event-driven — ``mark_character_active``
    fires on login/puppet, so a returning player is ACTIVE immediately instead of
    waiting up to a week for cron. This sweep therefore never needs to examine a
    non-ACTIVE sheet to catch a return, which is also what keeps its scan bounded
    to the population that can actually change.

    Population is characters on the **Active roster**. A Story NPC sits on the NPC
    shelf and is excluded by construction rather than by a special case (#2728 §10),
    and an unplayed character on Available has no one to go inactive.

    ``ActivityRequirement`` no longer decides *whether* a character is swept — every
    character goes INACTIVE at 30 days so nothing accrues income or takes decay for
    someone who isn't there. It decides which signals count, and whether inactivity
    also releases the character (#2728 §4/§7).

    ``FROZEN`` is never touched by cron; ``HIATUS`` is the player's own exemption and
    is only ended here when it has expired.

    **A swept character costs writes only.** Everything the loop reads is fetched in
    bulk below, so the read cost is flat in the playerbase — pinned by the slope
    guards in ``test_sweep_query_slope`` rather than left to inspection, because a
    per-character read is invisible at ten characters and ruinous at a thousand.

    Returns a small telemetry dict so the scheduler can log per-tick volume.
    """
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
    from world.character_sheets.types import ActivityState  # noqa: PLC0415
    from world.roster.models import Roster, RosterTenure  # noqa: PLC0415
    from world.roster.models.choices import RosterType  # noqa: PLC0415

    flipped_to_inactive = 0
    hiatus_expired = 0
    released = 0

    now = timezone.now()
    on_active_shelf = CharacterSheet.objects.filter(
        roster_entry__roster__roster_type=RosterType.ACTIVE,
    )

    # Resolved once, before any mutation: a release needs the Available shelf, and
    # discovering it is missing halfway through would leave a partially-swept run
    # with some sheets already flipped. Unseeded is a deployment error, so it fails
    # loudly — but it fails before touching anything.
    available_roster = Roster.objects.get(roster_type=RosterType.AVAILABLE)

    # Everything the demotion loop reads is fetched in bulk, so a swept character
    # costs writes only (#2728). Each piece earns its place:
    #   roster_entry__roster   — the shelf, read by ``move_to_roster``
    #   true_profile           — ``CharacterSheet.save`` persists it on every save (#1270)
    #   tenures + their player — ``decay_tier`` walks tenure -> player_data -> account
    #                            for the login signal, and ``RosterTenure``'s
    #                            related-cache clearing touches both again on save
    # ``to_attr`` fills ``RosterEntry.cached_tenures`` directly, which is what
    # ``current_tenure`` reads — and it leaves Django's own prefetch cache alone, so
    # ``entry.tenures`` stays a live relation for anyone else. The prefetch is scoped
    # to this queryset rather than the shared base above because the hiatus pass needs
    # none of it.
    inactive_tiers = _inactive_tiers()
    demotable = (
        on_active_shelf.filter(activity_state=ActivityState.ACTIVE)
        .select_related("roster_entry__roster", "true_profile")
        .prefetch_related(
            Prefetch(
                "roster_entry__tenures",
                queryset=RosterTenure.objects.select_related("player_data__account"),
                to_attr="cached_tenures",
            ),
        )
    )
    for sheet in demotable.iterator(chunk_size=500):
        entry = current_roster_entry(sheet)
        try:
            if sheet.decay_tier not in inactive_tiers:
                continue
            sheet.activity_state = ActivityState.INACTIVE
            sheet.save(update_fields=["activity_state", "updated_date"])
            flipped_to_inactive += 1
            if release_inactive_character(sheet, available_roster=available_roster):
                released += 1
        finally:
            # The filled list lives on the RosterEntry instance, and SharedMemoryModel
            # hands that same instance to every later reader in the process — so
            # leaving it would pin a mid-sweep snapshot of the tenures indefinitely.
            # The sweep cleans up after itself unconditionally, ``continue`` included.
            if entry is not None:
                entry.invalidate_tenure_cache()

    # Hiatus expiry runs AFTER demotion, deliberately. A player's decay clock keeps
    # running through their declared absence, so expiring a hiatus and demoting in
    # the same tick would flag — and for a roster character, release — someone the
    # instant their vacation ended, before they had any chance to log back in. That
    # is the precise outcome the hiatus setting exists to prevent. Expiring here
    # leaves them ACTIVE until the next run, which is the grace period.
    expired_hiatus = on_active_shelf.filter(
        activity_state=ActivityState.HIATUS,
        activity_state_until__lt=now,
    )
    for sheet in expired_hiatus.iterator(chunk_size=500):
        _set_active(sheet)
        hiatus_expired += 1

    return {
        "flipped_to_inactive": flipped_to_inactive,
        "hiatus_expired": hiatus_expired,
        "released": released,
    }


def may_auto_release(sheet: CharacterSheet) -> bool:
    """Whether an inactive character should be handed back to the roster (#2728 §7).

    The inactivity flag is broad; the release is narrow, and conflating the two is
    the main thing to get right. Taking a character away is only justified when
    someone else is waiting for it — true of a roster character whose authored
    stories block on its absence, not of a player's own creation.

    * ``is_oc`` — **never**. A player's own character is theirs.
    * ``activity_requirement`` NONE — no. That is the authored "this character
      carries no activity expectation" tier.
    * NPCs — excluded by shelf before this is ever called.
    """
    from world.roster.models.choices import ActivityRequirement  # noqa: PLC0415

    if sheet.is_oc:
        return False
    entry = current_roster_entry(sheet)
    if entry is None:
        return False
    return entry.activity_requirement in {
        ActivityRequirement.HIGH,
        ActivityRequirement.LOW,
    }


@transaction.atomic
def release_inactive_character(
    sheet: CharacterSheet,
    *,
    available_roster: Roster | None = None,
) -> bool:
    """End the current tenure and hand the character back to Available.

    Returns True when a release happened. No-op (False) when the character is not
    eligible per ``may_auto_release`` or nobody currently holds it.

    The tenure is *ended*, never deleted — player history is the roster's whole
    point, and a returning player is re-seated onto the same row by
    ``RosterApplication.approve`` rather than becoming "2nd player of X" when they
    are the same person.

    ``available_roster`` lets a bulk caller resolve the shelf once; single callers
    can omit it.
    """
    from world.roster.models import Roster  # noqa: PLC0415
    from world.roster.models.choices import RosterType  # noqa: PLC0415

    if not may_auto_release(sheet):
        return False

    entry = current_roster_entry(sheet)
    if entry is None:
        return False
    tenure = entry.current_tenure
    if tenure is None:
        return False

    if available_roster is None:
        available_roster = Roster.objects.get(roster_type=RosterType.AVAILABLE)

    tenure.end_date = timezone.now()
    tenure.save(update_fields=["end_date"])
    entry.move_to_roster(available_roster)
    # The tenure caches memoise the pre-release state; the caller may go on to read
    # accepts_applications, which would otherwise still see an open tenure.
    entry.invalidate_tenure_cache()
    return True


def mark_character_active(sheet: CharacterSheet) -> bool:
    """Promote a returning player's character on login/puppet (#2728 §6).

    Event-driven so a returning player is playable immediately rather than up to a
    week later. Only INACTIVE is cleared: HIATUS is the player's own declaration
    and ends via ``end_hiatus`` or expiry, and FROZEN carries a cooldown that
    ``unfreeze_character`` enforces. Returns True when a flip happened.
    """
    from world.character_sheets.types import ActivityState  # noqa: PLC0415

    if sheet.activity_state != ActivityState.INACTIVE:
        return False
    _set_active(sheet)
    return True


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
