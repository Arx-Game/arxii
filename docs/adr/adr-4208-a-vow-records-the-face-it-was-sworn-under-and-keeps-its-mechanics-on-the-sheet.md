# ADR-4208: A vow records the face it was sworn under, and keeps its mechanics on the sheet

**Status:** Accepted (2026-10-09, ApostateCD)
**Issue:** #4208
**Related:** ADR-0253 (titles hang on the persona), ADR-0213 (the Covenant is the party),
#4207 (the sheet's covenant block follows identity reveal), #3906 (covenant roles are public)

## Context

A covenant role is keyed on the character sheet because its mechanics are facts about the
body: engaged role bonuses, COVENANT_ROLE thread pulls, battle command tiers, the Durance's
level gate, fourteen packages reading the row by sheet. Presentation needs the opposite: a
character who swears into a covenant under an established alt should be known there as the
alt, and the alt's sheet should show that covenant while the primary's does not. #4207 could
only hide the block from an undisclosed face; it could not show an alt its own vow.

## Decision

`CharacterCovenantRole.sworn_as` is a required `PROTECT` foreign key to the persona the vow
was sworn under, one of the character's own and PRIMARY or ESTABLISHED (org membership refuses
a mask the same way; a vow binds the body to a face the character keeps). It is presentation
only: the sheet FK stays the mechanical anchor and the active-uniqueness key stays (sheet,
covenant), because one body cannot hold the same vow twice and have it count double. Every
writer resolves the face through one service seam (the active persona when not told); the
induction ritual reads it when it fires rather than storing it on the session. Readers follow
the face: the sheet shows a presented face's rows, other faces' rows only to a viewer who may
read the link between them; the roster names the sworn face. Existing vows were backfilled to
the primary face, so the column is NOT NULL.

## Rejected alternatives

Moving the row onto the persona (a face would become a mechanical unit, and fourteen readers
would change for a presentation need); leaving #4207's reveal gate as the end state (an alt's
own public face could never show its own covenant); storing the face on the ritual session
participant (the face is a fact of the moment the vow is sworn, read then, not a draft field).
