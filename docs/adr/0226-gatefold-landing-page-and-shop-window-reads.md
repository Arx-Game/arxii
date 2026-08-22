# ADR-0226: The Gatefold landing page reads existing endpoints, not a new realms API

**Status:** Accepted (2026-08-22) - extends ADR-0224, precedented by ADR-0146.

The public front page (issue #3305, three prototypes plus a 3-round adversarial
review and user testing, ApostateCD-approved) is a scroll-through folio ("Gatefold"):
a night cover, Chapter I realms-first pitch (public starting areas + expandable
Beginnings), Chapter II codex drop-cap, Chapter III scene excerpt, a
registration-aware Door, and a motto imprint. Ruling: it serves realm/Beginnings
pitch content by opening the existing `world/character_creation`
`StartingAreaViewSet`/`BeginningsViewSet` to anonymous reads (queryset-gated, not
permission-gated - the same shop-window shape ADR-0224 established for CG
perspective content) and by adding an anonymous, page-capped branch to
`InteractionViewSet.list` plus a `finished_after` scene filter, rather than
standing up a `world/realms` read API. The old `evennia_replacements` homepage
components and the `/api/status/` stats/news portal (character/room counts, recent
activity) were deleted outright rather than kept alongside the new page - the
Gatefold's chapters supersede that surface, not extend it. The landing route also
forces the `arx` realm's palette via the theme provider's `setForcedRealm` for the
duration of the visit, restoring the visitor's own stored theme choice on
navigating away.

**Rejected:**
- A dedicated `world/realms` API for pitch content - `Realm` is already reachable
  as an FK off `StartingArea`, and a parallel read surface for the same content
  the existing CG endpoints already serve would be a duplicate implementation with
  no capability gain, the same reasoning ADR-0146 used to reject a second media
  model.
- Keeping `/api/status/` as a stats/news portal page alongside the Gatefold -
  the folio's Chapter III scene excerpt and monthly count already cover the
  "the game is alive" signal; a separate portal page would be redundant surface
  with its own maintenance cost.
