# Codex glossary

**Codex / CodexEntry**:
The canon-lore store: a `CodexEntry` is an individual piece of reviewed world knowledge (subject, summary, lore and mechanics content, learning costs) nested under a `CodexSubject` and `CodexCategory`. An entry can be `is_public` (visible to everyone including logged-out visitors) and `is_featured` (curated for the front-page onboarding surface). Entries are the only unit of codex secrecy: categories and subjects carry no visibility of their own, and any container whose subtree holds no visible entry is hidden from the reader entirely (ADR-0221). The authorship/canon boundary against a Secret — Codex is canon-true-about-the-world authored under lore authority, where a Secret is a hidden, earned fact about a concrete entity with a keeper and consequences (see **Perspective entry** for the attributed-bias carve-out).
_Avoid_: lore entry, wiki article, article.

**Perspective entry**:
A `CodexEntry` whose `BeginningsCodexGrant` or `TraditionCodexGrant` row carries
`is_perspective=True`: a canon-accurate record of a biased in-world voice, attributed to the
culture (Beginnings) or tradition that holds it and surfaced as `perspective_of` on the entry
API. The entry's subject is what the take is about; the grant row's beginnings/tradition is who
holds it; granting is viewer-only (#3277, #3281). An entry has at most one holder across both
tables, not one per table - each table's partial unique constraint only sees its own rows, so
`clean()` on both models cross-checks the other table. This is the carve-out to "Codex is
canon-true": the *attribution* is canon-true, the prose is deliberately partisan.

Because a perspective entry is typically non-public and mid-chargen players have no roster
entry yet, the CG wizard reads it through a dedicated ungated shop-window path rather than the
gated codex API - `GET .../beginnings/{id}/perspectives/` and `GET
.../traditions/{id}/perspectives/` on `world.character_creation` (ADR-0224). That ungated read
is a deliberate carve-out for chargen only; it does not change codex visibility. Corollary
authoring rule: because that shop window has no knowledge gate, a perspective entry must never
carry secret or spoiler material - anyone mid-chargen can read it.
_Avoid_: stereotype (WoD term, fine in discussion, not in code), opinion entry, viewpoint.

**CharacterCodexKnowledge**:
A roster-scoped record of what one character knows or is learning about a `CodexEntry`, carrying a status (UNCOVERED while learning, KNOWN once fully learned), accumulated `learning_progress`, and who taught it. Knowledge belongs to the character itself, so a new player inheriting the character inherits what it knows.
_Avoid_: known lore, learned entry, codex progress.

**Discovery** (this app's usage):
`CodexEntry` can carry a `discovery_achievement` (nullable, from `achievements.DiscoverableContent`)
that fires the shared discovery/achievement ceremony the first time any character learns it, via
`grant_codex_entry`. See `world/achievements/CLAUDE.md`'s `DiscoverableContent`/`announce_access_change`
sections for the full mechanism — including the player-tenure/staff gate and the CG-catalog
exclusion, which mean character-creation grants and common-knowledge entries never fire it (#2899).
_Avoid_: reinventing a codex-local discovery/achievement mechanism.
