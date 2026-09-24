"""Character slots: the one place that counts how many characters an account holds.

Policy (#3996, ruled 2026-09-24): an account has ``settings.CHARACTER_SLOTS_BASELINE``
slots plus ``PlayerData.extra_character_slots``. A slot is used by a current tenure
whose character is neither frozen nor retired, by an open ``CharacterDraft`` and by a
pending ``RosterApplication``, so the slot is reserved the moment work on a character
starts. At most one used slot may be a roster character with an activity requirement
(``RosterEntry.activity_requirement`` other than NONE). Staff accounts are exempt.
Freezing an original character keeps its tenure and frees its slot; giving up a roster
character ends the tenure (see ``world.roster.services.activity``).

Every gate (character creation, roster application, reviewer approval, the Hall, telnet
``@characters``) reads ``character_slots`` or ``assert_slot_available``; nothing else
counts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings

from world.character_sheets.types import ActivityState, LifecycleState
from world.roster.models.applications import RosterApplication
from world.roster.models.choices import ActivityRequirement, ApplicationStatus, SlotHolderKind
from world.roster.types import CharacterSlots, SlotHolder

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

ACTIVITY_SLOTS = 1

SLOTS_FULL = "slots_full"
ACTIVITY_SLOT_FULL = "activity_slot_full"


class SlotsFullError(Exception):
    """The account has no free slot of the kind it asked for.

    ``code`` is ``slots_full`` or ``activity_slot_full``; ``holders`` names what the
    player can freeze, give up, finish or withdraw; ``user_message`` is safe to show.
    """

    def __init__(self, code: str, holders: list[SlotHolder], user_message: str) -> None:
        super().__init__(user_message)
        self.code = code
        self.holders = holders
        self.user_message = user_message


def character_slots(
    account: AccountDB,
    *,
    exclude_application: RosterApplication | None = None,
) -> CharacterSlots:
    """Return the account's slot ledger.

    ``exclude_application`` leaves one pending application out of the count, for the
    reviewer's approval re-check where that application is about to become a tenure.
    """
    player_data = account.player_data
    holders: list[SlotHolder] = []

    for tenure in player_data.cached_active_tenures:
        entry = tenure.roster_entry
        sheet = entry.character_sheet
        if sheet.lifecycle_state == LifecycleState.RETIRED:
            continue
        frozen = sheet.activity_state == ActivityState.FROZEN
        holders.append(
            SlotHolder(
                kind=SlotHolderKind.FROZEN if frozen else SlotHolderKind.CHARACTER,
                name=sheet.character.db_key,
                roster_entry_id=entry.pk,
                counts=not frozen,
                activity=not frozen and entry.activity_requirement != ActivityRequirement.NONE,
            )
        )

    holders.extend(
        SlotHolder(
            kind=SlotHolderKind.DRAFT,
            name=str(draft),
            roster_entry_id=None,
            counts=True,
            activity=False,
        )
        for draft in account.character_drafts.all()
    )

    applications = RosterApplication.objects.filter(
        player_data=player_data,
        status=ApplicationStatus.PENDING,
    ).select_related("character__roster_entry", "character__character")
    if exclude_application is not None:
        applications = applications.exclude(pk=exclude_application.pk)
    for application in applications:
        sheet = application.character
        entry = sheet.roster_entry
        holders.append(
            SlotHolder(
                kind=SlotHolderKind.APPLICATION,
                name=sheet.character.db_key,
                roster_entry_id=entry.pk,
                counts=True,
                activity=entry.activity_requirement != ActivityRequirement.NONE,
            )
        )

    total = (
        None
        if account.is_staff
        else settings.CHARACTER_SLOTS_BASELINE + player_data.extra_character_slots
    )
    return CharacterSlots(
        total=total,
        used=sum(1 for holder in holders if holder.counts),
        activity_total=ACTIVITY_SLOTS,
        activity_used=sum(1 for holder in holders if holder.activity),
        holders=holders,
    )


def _slots_full_message(slots: CharacterSlots) -> str:
    characters = [h.name for h in slots.holders if h.kind == SlotHolderKind.CHARACTER]
    pending = [
        h for h in slots.holders if h.kind in {SlotHolderKind.DRAFT, SlotHolderKind.APPLICATION}
    ]
    parts: list[str] = []
    if characters:
        parts.append("freeze or give up one of: " + ", ".join(characters))
    if any(h.kind == SlotHolderKind.DRAFT for h in pending):
        parts.append("finish or discard your draft")
    if any(h.kind == SlotHolderKind.APPLICATION for h in pending):
        parts.append("withdraw a pending application")
    if not parts:
        return "All your character slots are in use."
    return "All your character slots are in use; " + "; or ".join(parts) + "."


def _activity_slot_message(slots: CharacterSlots) -> str:
    names = [h.name for h in slots.holders if h.activity]
    return "You already hold a character with an activity requirement: " + ", ".join(names) + "."


def assert_slot_available(
    account: AccountDB,
    *,
    wants_activity_requirement: bool,
    exclude_application: RosterApplication | None = None,
) -> CharacterSlots:
    """Raise ``SlotsFullError`` unless the account can take on one more character.

    ``wants_activity_requirement`` is True when the character being taken on is a
    roster character with an activity requirement, which also needs the one activity
    slot. Returns the ledger so callers can show it.
    """
    slots = character_slots(account, exclude_application=exclude_application)
    if not slots.has_free_slot:
        raise SlotsFullError(SLOTS_FULL, slots.holders, _slots_full_message(slots))
    if wants_activity_requirement and not slots.has_free_activity_slot:
        raise SlotsFullError(ACTIVITY_SLOT_FULL, slots.holders, _activity_slot_message(slots))
    return slots
