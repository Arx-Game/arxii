# ADR-4659-A: Any Tradition may teach any Major Gift, and a Gift grant marks a Gift it favors

**Date:** 2026-10-25
**Status:** Accepted (owner ruling 2026-10-25 on the parent spec #4659; built in its slice 1, #4664)
**Issue:** #4659, #4664. Supersedes the tradition-gated Gift availability in ADR-0136.

## Decision

A Tradition no longer limits which Major Gift a character picks at creation. The Gift list for a
draft is every Major Gift whose Path list holds a takeable technique offered to the draft's
Tradition (`cg_catalog.get_gift_options`). A `TraditionGiftGrant` row now means a Gift the
Tradition's teachers favor. Its `special_techniques` still keep those techniques to the listing
Traditions (#4555, ADR-4555-A), so a Tradition's own techniques stay its own. The self-taught
Tradition's grant rows, which existed only to make every Gift pickable, are deleted by migration
0295 (deliberate discard, maintainer sign-off on #4659). The favored Gifts feed the teaching fit
built in slice 2 (#4665): a student whose Gift and affinity suit the Tradition gets more training
and easier courses, never a gate.

## Rejected

- **Keep the whitelist and add fit on top.** A student would still be refused a Gift their
  Tradition did not list, which is the restriction the owner asked to remove: teachers are better
  at some Gifts, they do not forbid the rest.
- **A separate "favored Gift" table beside the grant.** The grant rows already pair a Tradition
  with a Gift and are content-exported; a second table would hold the same pairs.

> Status: accepted · Source: #4659 owner ruling 2026-10-25 · Confidence: built and wired in #4664
