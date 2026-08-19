# Codex glossary

**Codex / CodexEntry**:
The canon-lore store: a `CodexEntry` is an individual piece of reviewed world knowledge (subject, summary, lore and mechanics content, learning costs) nested under a `CodexSubject` and `CodexCategory`. An entry can be `is_public` (visible to everyone including logged-out visitors) and `is_featured` (curated for the front-page onboarding surface). Entries are the only unit of codex secrecy: categories and subjects carry no visibility of their own, and any container whose subtree holds no visible entry is hidden from the reader entirely (ADR-0219). The authorship/canon boundary against a Secret — Codex is canon-true-about-the-world authored under lore authority, where a Secret is a hidden, earned fact about a concrete entity with a keeper and consequences.
_Avoid_: lore entry, wiki article, article.

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
