# ADR-0094: Mission discovery is world-anchored

## Status

Accepted (2026-07-08)

## Context

Players had only two front doors to find missions — NPC interaction (`hire` offers)
and trigger givers (room entry / examine auto-grants). Both required players to
already know where to look. The missions epic (#2043) identified this as a key gap:
players need things to pursue without a GM.

## Decision

Discovery is **world-anchored**: notice boards and trigger givers are the doors;
the web opportunities tab is a map (convenience layer over the same eligibility
pipeline), never a door. Org postings are a grouping of existing NPCServiceOffer
rows — no new posting model. Follow-on summons (missions that beget missions)
will ride the summons primitive once #2050 lands.

Three surfaces:

1. **Notice boards** — a new `GiverKind.BOARD` turns an examinable object into a
   postings board. Examine renders eligible postings (preview-only, no grant);
   `mission take <n>` (telnet) and the board API re-run eligibility before granting.
2. **Opportunities tab** — `GET /api/missions/journal/opportunities/` + the journal
   tab surface three groups: here (boards in current room), nearby (givers in
   current area — trigger givers show flavor only), your organizations (MISSION
   offers on org-affiliated NPC roles).
3. **Follow-on summons** (deferred to #2050) — `DeedRewardSink.FOLLOW_ON_SUMMONS`
   will route to `create_summons` when the summons primitive lands.

## Rejected

- **A global browse-all mission board** — kills world-anchoring; players would
  never need to be on the grid.
- **Accept-from-panel** — the tab must not be a door; acceptance stays at the
  giver/board in the world.
- **A separate org-posting model** — org postings ride existing NPCServiceOffer
  rows; the tab just groups them.
- **Rumor-based discovery** — Phase 6+ stub stays; discovery must not wait on a
  rumor system.
