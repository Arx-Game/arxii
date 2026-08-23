# Journals & Expression

**Status:** in-progress
**Depends on:** Progression (XP rewards)

## Overview
IC writing by players — journals, praises, retorts, and weekly XP awards. Journals serve dual purposes: creative expression that's fun to write and read, and practical record-keeping that maintains continuity (especially for roster characters that change players).

## Key Design Points
- **XP rewards for writing:** Characters earn diminishing XP for journal entries (5/2/1 for first three per week)
- **Praise/retort system:** Players respond to public entries with praises (agreement) or retorts (disagreement), each awarding XP to both parties
- **Public/private visibility:** Entries are either public or private — no intermediate visibility tiers
- **Freeform tags:** Entries can have multiple tags for filtering and discovery
- **Weekly XP reset:** All XP caps reset weekly based on timestamps (not cron)

## What Exists
- **JournalEntry model** — title, body, is_public, parent self-FK for responses, response_type (praise/retort), timestamps
- **JournalTag model** — freeform tags per entry with unique constraint
- **WeeklyJournalXP model** — per-character weekly tracking with timestamp-based reset
- **Service functions** — `create_journal_entry()`, `create_journal_response()`, `edit_journal_entry()`
- **Action-backed (#1350, ADR-0001)** — the three write services are wrapped by
  REGISTRY Actions in `actions/definitions/journals.py`
  (`create_journal_entry` / `respond_to_journal` / `edit_journal_entry`); both
  the web `JournalEntryViewSet` and the telnet `CmdJournal` (`journal`
  command — `write`/`respond`/`edit` subverbs) dispatch through `action.run()`
  rather than calling services directly. Goals have the same convergence
  (`set_character_goals` / `log_goal_progress` Actions + `CmdGoal`).
- **REST API** — full CRUD with pagination, author/tag filtering, owner-only editing
- **Achievement stats** — emits `journals.total_written`, `journals.total_public`, praise/retort stats
- **JournalError** — custom exception with explicit user-safe message constants
- **Admin interface** — JournalEntryAdmin with tag inline
- **Full test coverage** — 54 tests covering services, views, and edge cases
- **Thread linking** — `JournalEntry.related_threads` M2M to the new `magic.Thread` model
  (Spec A). Replaces the deleted `ThreadJournal` join table; entries can now tag any
  anchored thread (trait, technique, item, room, relationship track, relationship capstone)
- **Frontend React components (#2160)** — `/journals` page (composer, public feed, own-entries
  tab) plus a `JournalTab` quick-compose panel in the in-scene sidebar. The `/journal` route
  (previously a decoy pointing at the unrelated missions ledger) now belongs to this app; the
  missions ledger moved to `/missions/journal`.
- **Account-level block/mute feed visibility + response gating (#2996)** — the public feed
  (`GET /api/journals/entries/`) excludes an account-level-blocked account's entries **both
  directions** (`journals.services.exclude_blocked_and_muted_authors`, called from
  `JournalEntryViewSet.list`) and an account-level-muted account's entries from the **muter's
  own feed only**; both reuse the batched `block_services.blocked_player_ids_for`/
  `mute_services.muted_player_ids_for` helpers, one `.exclude()` per call. Praise/retort
  responses: a block between responder and parent author rejects with the neutral shared
  `JournalError.UNAVAILABLE` (write never happens — the only #2996 seam that rejects instead of
  write-then-filter, since a rejection here can't leak); a mute persists the response normally
  but excludes it from the entry AUTHOR's own read (`JournalEntryViewSet.retrieve`) — any other
  viewer is unaffected.
- **Weekly-vote UI on public journal entries (#3302)** — `VoteButton` (`targetType="journal"`)
  is mounted on `JournalsPage`'s public feed rows and the in-scene `JournalTab`, gated by
  `is_public` and hidden when `entry.author` (a CharacterSheet id) is one of the viewer's own
  roster characters (the backend already refuses self-votes, via
  `services/voting.py::get_author_account_for_target`, so this is a UX-only guard). Shares the
  same weekly budget as pose/action votes and shows up in `VotesPanel`'s history via the
  existing `journal` target-type label; no backend change was needed, since the JOURNAL vote
  target was already fully wired.

## Deferred (depends on systems that don't exist yet)
- **Relationship gating for retorts** — retorts should validate antagonistic relationship (needs relationships system)
- **Fame signal emission from praises** — praises should emit fame signal (needs fame/reputation system)
- **IC timestamp population** — `ic_timestamp` field exists but needs world clock system
- **Read tracking / unread filtering** — track which entries a character has read
- **Great Archive IC location gating** — IC access point for the journal archive (needs world building)
- **GoalJournal removal** — remove old goal-specific journals once migrated (ThreadJournal already removed; see Thread linking above)

## Notes
- Retorts award more XP to receiver (3) than giver (1) to incentivize dramatic conflict
- Praises award more XP to giver (2) than receiver (1) to incentivize community engagement
- Party adventure logs deferred — may be better as a scene/story integration feature
- Journal categories (relationship notes, adventure logs) replaced by freeform tags
