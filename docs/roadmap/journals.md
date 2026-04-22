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
- **REST API** — full CRUD with pagination, author/tag filtering, owner-only editing
- **Achievement stats** — emits `journals.total_written`, `journals.total_public`, praise/retort stats
- **JournalError** — custom exception with explicit user-safe message constants
- **Admin interface** — JournalEntryAdmin with tag inline
- **Full test coverage** — 54 tests covering services, views, and edge cases
- **Thread linking** — `JournalEntry.related_threads` M2M to the new `magic.Thread` model
  (Spec A). Replaces the deleted `ThreadJournal` join table; entries can now tag any
  anchored thread (trait, technique, item, room, relationship track, relationship capstone)

## Deferred (depends on systems that don't exist yet)
- **Relationship gating for retorts** — retorts should validate antagonistic relationship (needs relationships system)
- **Fame signal emission from praises** — praises should emit fame signal (needs fame/reputation system)
- **IC timestamp population** — `ic_timestamp` field exists but needs world clock system
- **Read tracking / unread filtering** — track which entries a character has read
- **Mute/follow preferences** — per-character subscription controls for journal feeds
- **Account-level block integration** — respect account blocks in journal visibility
- **Great Archive IC location gating** — IC access point for the journal archive (needs world building)
- **GoalJournal removal** — remove old goal-specific journals once migrated (ThreadJournal already removed; see Thread linking above)
- **Frontend React components** — journal reading, writing, and browsing UI

## Notes
- Retorts award more XP to receiver (3) than giver (1) to incentivize dramatic conflict
- Praises award more XP to giver (2) than receiver (1) to incentivize community engagement
- Party adventure logs deferred — may be better as a scene/story integration feature
- Journal categories (relationship notes, adventure logs) replaced by freeform tags
