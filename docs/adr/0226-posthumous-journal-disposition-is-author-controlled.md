# ADR-0226: Posthumous journal disposition is author-controlled, default REVEAL

**Status:** Accepted (2026-08-22, #3287).

Private journal entries previously died with their author — a write-only drawer with no
afterlife, unlike Arx I's black journal, where a private journal becoming the historical
record after death was load-bearing lore (it is what made writing honestly in private carry
stakes). #3287 gives the author two independent, author-controlled dials instead of a staff
or system default: `CharacterSheet.posthumous_journal_disposition` (REVEAL / SEAL, default
REVEAL — the Arx I precedent) sets the sheet-wide default, and a per-entry
`JournalEntry.posthumous_override` (INHERIT / REVEAL / SEAL, default INHERIT) lets a single
entry deviate. Rejected alternative: a staff-curated or system-computed reveal (e.g. "reveal
after N days regardless of author wish") — rejected because it isn't consent-clean; only the
author's own writing is at stake, so only the author's own declared wish should govern it.
Execution rides the shipped, timer-backed `estates.services.execute_settlement` pipeline
(ADR-0133) via two explicit calls (no signals, ADR-0009) —
`reveal_journals_for_settlement` (always runs) and `grant_journal_bequest` (only when the
will carries a new `BequestKind.WRITINGS` line, minting a `JournalBequestGrant` instead of
moving a specific asset, since the deceased's corpus itself is the thing bequeathed) — rather
than a new death hook. A reveal never mutates `is_public`, so authorship history stays true;
SEAL always wins, even over a bequest grant, enforced at the journals read path rather than
by filtering the grant row itself.
