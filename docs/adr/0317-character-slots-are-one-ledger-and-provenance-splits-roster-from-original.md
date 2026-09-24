# ADR-0317: Character slots are one ledger; provenance splits roster from original character

- **Status:** Accepted
- **Date:** 2026-09-24
- **Issue:** #3996

## Context

Three caps existed and none worked: `CG_MAX_CHARACTERS` counted drafts only (one
per account, deleted at approval, so unreachable), the OC cap helpers in
`character_sheets.services` had no production caller, and roster applications never
looked at what the player already held. "Original character" was a hand-set
`CharacterSheet.is_oc` flag that character creation never wrote, so a player's own
character and a staff-authored roster character looked identical and carried the
same default activity requirement.

## Decision

One service, `world.roster.services.slots`, is the only place that counts. An
account holds `CHARACTER_SLOTS_BASELINE` (4) plus `PlayerData.extra_character_slots`;
a slot is used by a current tenure whose character is neither frozen nor retired, by
an open draft and by a pending application, so the slot is reserved when work starts
and a reviewer never refuses an approval over a cap the player could not see. One slot
may be a roster character with an activity requirement (HIGH or LOW; NONE is free).
Staff are exempt. Character creation, roster application and reviewer approval all
ask the service; approval re-checks with its own application left out.

Roster versus original character is `RosterEntry.creation_provenance`: STAFF and
GM_TABLE are roster characters, PLAYER is an original character, and character
creation finalizes a player's entry with no activity requirement. `is_oc` and
`created_by` are retired. Original characters are frozen (tenure kept, 30-day thaw
cooldown) and roster characters are given up (tenure ended, entry back to Available),
because a frozen lore character would be one hoarded off the roster.

## Rejected

- Counting only approved active characters: lets a player queue five applications.
- Freezing any character: hoards roster characters indefinitely.
- Keeping `is_oc` beside provenance: two sources of truth for one fact.
- A grants table for purchased slots: premature; the per-account integer leaves room.
