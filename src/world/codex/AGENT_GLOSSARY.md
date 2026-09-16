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

**Organization codex grant**:
An `OrganizationCodexGrant` row (#3780): a `CodexEntry` every active member of one
`Organization` knows. The Deity Editor's "Obscure" visibility tier is exactly this (a being's
page that is not public, known to one organization), the mechanism Dan confirmed on #3776 and
that issue deferred to implementation. Applied on `join_organization`
(`apply_organization_codex_grants`) and to current members when the grant is created
(`grant_organization_entry_to_members`); a plain grant, never a perspective holder.
_Avoid_: "org secret", "faction lore".

**Reach** (#3775, ADR-0303):
How a `CodexEntry` can be known at all: public (`is_public`), granted to a group through
one of the five grant tables (Beginnings, Path, Distinction, Tradition, Organization) or a
species lineage, or found through a Mystery (a `Clue` with `target_kind=CODEX`). An entry
with none of these is **unreachable** - no character can ever come to know it, and no
future character can either until someone adds a route. `ReachListFilter` is the entry
admin's list filter of this name (public / granted to a group / reached by a clue /
unreachable); `known_via` is the paired list-display column naming which routes an entry
has and how many rows each contributes.
_Avoid_: visibility tier, access level.

**Grant to current holders** (#3775, ADR-0303):
`world.codex.services.grant_to_current_holders(grant)`: hands one grant row's entry to
every roster entry its `holder_roster_entries()` names, and returns how many first learned
it. Exists because a grant row created after characters already exist would otherwise be a
dead row until the next character who joins the group - `GrantReachOnSaveMixin` calls it
automatically when an admin saves a new grant row, and the entry admin's "Grant to current
holders" action calls it for every existing grant on the selected entries plus
`grant_entry_to_species_holders` for species. Idempotent, because the `grant_codex_entry`
it calls is idempotent.
_Avoid_: backfill, retroactive grant.
