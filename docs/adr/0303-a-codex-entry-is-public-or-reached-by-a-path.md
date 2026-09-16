# ADR-0303: A codex entry is public or reached by a path, and the admin leads with who knows it

**Date:** 2026-09-16
**Status:** Accepted (Dan, in session)
**Issue:** #3775 (relates ADR-0221, ADR-0222, #2688, #3780)

## Decision

A `CodexEntry` has two states: public (`is_public`, everyone including visitors) or
reached by a path a character takes: born into it (`BeginningsCodexGrant`), taught by a
tradition, on joining an organization (`OrganizationCodexGrant`), by another character
(`CodexTeachingOffer`), or found through a Mystery (`Clue` with `target_kind=CODEX`).
Nothing is shown to visitors or in character creation and later taken away. Routes stack;
only the perspective flag is single-holder. A clue and the public flag refuse each other.
Staff accounts (`is_staff`, never a GM role) read every entry with full content, under a
visible "Staff view" line.

Grants reach the characters already in a group: every admin that creates a grant row
applies it on save, and the entry admin's "Grant to current holders" action catches up
existing characters. That needs a record of where a character started, which the deleted
draft no longer holds, so `ProfileBeginnings` records every origin a character holds with
its why (`character_creation` once per profile, `recovered_memory`, `past_life`); the set
only grows, and adding an origin grants its entries.

## Rejected

Public by default plus a data migration flipping the loaded corpus: withdrawn in the
brainstorm once the lore roster's tiering (globals, realm, insider, identity) was read
against the 265 beginnings-grant rows already encoding it; it would have encoded a content
ruling in the migration chain and contradicted the two-state rule. A single `Profile
.beginnings` FK: a recovered origin would overwrite where play began and cut the character
off from future grants of the origin they still hold. A visitor or CG-only preview tier:
Dan, 2026-09-16, "we aren't going to show knowledge to visitors or in CG and then remove it".
