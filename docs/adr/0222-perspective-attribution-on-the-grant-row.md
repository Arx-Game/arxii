# ADR-0222: Perspective attribution lives on the grant row, viewer-only

Date: 2026-08-20. Status: accepted (Tehom ruling).

A codex entry can be a culture's own biased take on its subject rather than
canon-neutral knowledge, and the reader needs to see whose voice it is. A
considered `BeginningsPerspective` model - a standalone table linking a
Beginnings to an entry it holds a perspective on - was rejected as a parallel
implementation of the grant capability: every perspective implies a grant (the
holding culture must already know the entry to have a take on it), so a
separate table would duplicate `BeginningsCodexGrant`'s beginnings-entry link
and need to stay in sync with it. Instead, attribution is a flagged
`BeginningsCodexGrant` row (`is_perspective`) plus a partial unique constraint
(`one_perspective_holder_per_entry`, `condition=Q(is_perspective=True)`)
capping it at one holder per entry. Granting is viewer-only: creating the
flagged row does not teach the viewed culture anything, so its own characters
discover other cultures' takes on them through play, the same as any other
codex entry. Species perspectives are deferred until a `SpeciesCodexGrant`
table exists to carry the flag - species codex access is currently a plain
nullable FK on the species row, not a grant table.
