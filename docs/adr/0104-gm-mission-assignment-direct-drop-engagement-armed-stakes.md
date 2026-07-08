# ADR-0104: GM mission assignment is a direct drop with engagement-armed stakes

**Date:** 2026-07-08
**Status:** Accepted

## Context

Issue #2048: GMs need to assign missions to players from the story surface,
linking them to beats and gating episode progression. The question was
whether a GM "assign" is a directed offer the player accepts (consent + risk-ack
falls out of the existing accept flow) or an admin-style forced drop.

## Decision

GM mission assignment is a **direct drop** via `gm_assign_mission` — the
player consents by pursuing the mission, not by accepting it. Stakes arm
**lazily on the player's first beat action** (engagement-armed stakes), not
at assignment time. An ignored assignment never locks stakes; abandoning
before engagement leaves no contract.

`Beat.required_mission` is wired as the beat's authoring pointer (the GM sets
it on the beat; the drop gesture defaults from it). Template access gates on
risk via the merged GM trust ladder's `GMLevelCap.max_beat_risk` (#2054) —
no separate permission ladder. Permissions: the story's Lead GM or staff
(`IsLeadGMOnStoryOrStaff` pattern, Beat-aware via `CanAssignMissionToBeat`).

## Rejected alternatives

- **Offer-with-accept-gate:** redundant consent given clean abandon
  (`abandon_mission` guarantees a free exit).
- **A separate GM-assignment permission ladder:** consumed #2054's
  `GMLevelCap` instead — no new gate invented.
- **A new mission scope field:** world-impact scope is already carried by
  the beat/stakes machinery the mission feeds — a mission inherits its scope
  gating from the beat it satisfies.
