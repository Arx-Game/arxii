# Journals & Expression

**Status:** in-progress
**Depends on:** Progression (XP rewards)

## Overview
IC writing by players — journals, praises, retorts, and weekly XP awards. Journals serve dual purposes: creative expression that's fun to write and read, and practical record-keeping that maintains continuity (especially for roster characters that change players).

## Key Design Points
- **XP rewards for writing:** Characters earn diminishing XP for journal entries (5/2/1 for first three per week)
- **Praise/retort system:** Players respond to public entries with praises (agreement) or retorts (disagreement), each awarding XP to both parties
- **Public/private visibility:** Entries are either public or private — no intermediate
  visibility tiers. A private entry's death disposition (reveal to the world / seal
  forever / bequeath to a chosen reader) is a separate axis, not a third tier — see
  "Posthumous afterlife" below
- **Freeform tags:** Entries can have multiple tags for filtering and discovery
- **Weekly XP reset:** All XP caps reset weekly based on timestamps (not cron)

## What Exists
- **JournalEntry model** — title, body, is_public, kind (entry, or one of the CG Introductions: first_journal / application / whispers, #3621), parent self-FK for responses, response_type (praise/retort), timestamps
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
- **Nominate UI on public journal entries (#3302; nominations since #3738)** — `NominateButton`
  (`targetType="journal"`) is mounted on `JournalsPage`'s public feed rows and the in-scene
  `JournalTab`, gated by `is_public` and hidden when `entry.author` (a CharacterSheet id) is one
  of the viewer's own roster characters (the backend refuses your own characters through any
  alt, `services/nominations.py`, so this is a UX-only guard). A journal nomination is the same
  one-per-person-per-week nomination as a pose (one pool), shows in `NominationsPanel` under the
  `journal` label, can be the writer's most nominated prose, and the game's single most
  nominated journal each week pays its writer 1 XP (ties pay all).

- **World › Journals: the Reading Room (#3941)** — replaces the old two-list `/journals` page
  wholesale with one centered stream, newest first, of every entry the viewer may read; a row
  shows the writer, the IC date (`ic_timestamp`, click to flip to the posting date), the title,
  "About <name>" when set, and the body clamped to seven lines; one click opens it in place
  (full text, tags, actions, responses, respond form). A Search button folds a panel under the
  header (find a writer by name, About someone, tags, Show: newest / since your last visit with
  a count / Introductions / post mortems / staff-only black-only, plus an index table); closing
  it always returns to the stream. `?writer=<id>` opens a character's journal (pills: All,
  About <name> per subject they've written about, Written about them); `?mine=1` opens **Your
  journal** — the white+black entries together, the after-death and retort-consent switches, and
  Write. Writing (screen 5) picks White/Black first, then title/body, About + tags, then the
  after-death choice for Black, with the week's rewarded-post count shown. Staff read black
  entries in the same stream, banded, with no separate tool (`is_staff`, the Codex precedent).
  Linked from the World menu, the Hall (relabelled "Your journal"), and every character sheet
  (the link shows for every viewer; it leads only to what they may read). The user-ratified
  decisions the demo settled are ADR-0307 and issue #3941's Decisions list.
- **Relationship journals (#3941)** — `JournalEntry.about`, a nullable FK to `CharacterSheet`
  (`SET_NULL`, indexed with `-created_at`), names the one character an entry is about; settable
  on write and edit, filterable from both sides (`?about=<id>` alone is everything written about
  that sheet; with `?writer=<id>` it is one writer's entries about someone). Not a tag — a tag
  has no identity and `CharacterRelationship` needs the subject's mutual consent, which an entry
  about someone must not require.
- **Retort/Condemn consent gate (#3941, ADR-0307)** — `ResponseType.CONDEMN` (praise's
  antagonistic opposite; XP mirrors retort) joins praise/retort. Retort and Condemn are offered
  only when the writer's `CharacterSheet.retort_consent` (`RetortConsent`: `RIVALS` default /
  `ANYONE`) is `ANYONE`, or the viewer holds a mutual hostile relationship label with the writer
  (`world.relationships.services.mutual_hostile`, #3957 — each side must hold its own unended
  HOSTILE-valence label toward the other, at Clandestine or Public awareness, declared under a
  still-open tenure) read via `journals.services.can_retort`. Enforced server-side in
  `create_journal_response`; a refusal is the neutral shared `JournalError.UNAVAILABLE`, never
  naming the reason. Praise and a Nomination are never gated. The owner's consent choice is set
  via `GET/PATCH /api/journals/entries/disposition/` (widened, see below) or telnet `journal
  consent rivals|anyone`.
- **Post mortems (#3941)** — the interface word for a `revealed_at`-stamped entry (ADR-0229's
  mechanics unchanged); banded on the row, filterable (`?post_mortem=1`). A post mortem is not
  public, so it takes no Praise, Retort, Condemn, or Nomination (see `character-progression.md`).
- **Since-your-last-visit (#3941)** — `CharacterSheet.journals_visited_at`, one timestamp per
  character (not per-entry read tracking, a deliberately rejected finer-grained alternative);
  the paginated list response carries `since_visit_count` AND `visited_at`, both computed
  against the mark as it stood before `?mark_visit=1` advances it at the end of the same
  request (`journals.services.mark_journals_visited`). The cut itself is `?since=<iso
  timestamp>`, the client passing that `visited_at` back: a server-side `since_visit=1` flag
  cannot work, because opening the stream has already moved the mark to now, so by the time
  the reader presses the option every entry is older than it.
- **Widened settings endpoint (#3941)** — `GET/PATCH /api/journals/entries/disposition/` now
  reads/writes both `posthumous_journal_disposition` and `retort_consent` (either or both on a
  PATCH), plus read-only `posts_this_week`/`rewarded_posts_per_week`
  (`journals.services.journal_settings`) so the desk can show the week's remaining rewarded
  posts. Telnet `journal disposition` is unchanged; `journal consent rivals|anyone` is new
  alongside it.
- **IC timestamp population (#3941)** — `JournalEntry.ic_timestamp` is now stamped at creation
  from `game_clock.services.get_ic_now()`; stays null when no `GameClock` is active (the row
  then falls back to the posting date on the frontend). Previously a placeholder field nothing
  wrote.
- **Posthumous afterlife (#3287, ADR-0229)** — private entries no longer die with their
  author. `CharacterSheet.posthumous_journal_disposition` (REVEAL default / SEAL) plus a
  per-entry `JournalEntry.posthumous_override` (INHERIT default / REVEAL / SEAL) decide the
  fate; `world.journals.services.reveal_journals_for_settlement` and `.grant_journal_bequest`
  are called explicitly (no signals) from the shipped `estates.services.execute_settlement`
  pipeline (#1985, ADR-0133) — reveal always runs at settlement, the bequest grant only when
  the will carries a `BequestKind.WRITINGS` line. `is_public` is never mutated by a reveal.
  SEAL always wins, even over a bequest grant. Read paths: the public feed includes
  `revealed_at`-stamped entries; a bequest recipient browses the deceased's non-sealed
  private corpus via `GET /api/journals/entries/?deceased=<sheet_id>`; the composer/edit
  surface and telnet `journal disposition` set the sheet default and per-entry override.
  This closes the "no afterlife" gap noted in #3287's spec (private entries were previously
  a write-only drawer that died with the character).
- **Rivalry as a specific relationship kind (#3957, "Ties, redrawn")** — delivered. The
  structural rivalry predicate `can_retort` shipped with (#3941, "an active, non-pending
  `CharacterRelationship` in either direction on a negative-sign track") is gone; the Retort/
  Condemn gate now reads `world.relationships.services.mutual_hostile` — a **mutual** HOSTILE-
  valence `RelationshipLabel` (each side must hold its own, at Clandestine or Public, declared
  under a still-open tenure). This also folded in and deleted the standalone `scenes.Rivalry`
  double-opt-in declaration model, its web/telnet surfaces, and the RIVALS consent mode's
  predicate (`world.consent.services.consent_blocks_targeting`) — one predicate, one place.

## Deferred (depends on systems that don't exist yet)
- **Fame signal emission from praises** — praises should emit fame signal (needs fame/reputation system)
- **Per-entry read tracking / unread filtering** — `journals_visited_at` (#3941) is a single
  since-last-visit mark per character, deliberately not a per-entry read table (Decision 12); a
  finer-grained "which specific entries has this character read" stays deferred
- **Great Archive IC location gating** — writing a First Journal at the Great Archive in play
  still needs no non-standard access point; a standard entry never requires being in-game there
  (#3941 confirms this stays out of scope; needs world building)
- **A game-wide display of the week's most nominated journal** — the payout already runs
  (`progression.constants.MOST_NOMINATED_JOURNAL_XP`); no UI surfaces the week's winner (#3941
  out of scope, a future feature)
- **GoalJournal removal** — remove old goal-specific journals once migrated (ThreadJournal already removed; see Thread linking above)
- **In-life investigation/magic access to private journals (#3287, deferred)** — the clue-grant seam exists (`clues/services.py`) but needs authored Clue content + a ruling on whether living-character journal secrecy is ever pierceable; no physical relic-book item either (no consumer today)

## Notes
- Retorts award more XP to receiver (3) than giver (1) to incentivize dramatic conflict
- Condemn (#3941) mirrors Retort's XP asymmetry exactly (given 1, received 3) and shares its
  weekly flags (`retorted_this_week`/`was_retorted_this_week`) — one antagonism budget, not two
- Praises award more XP to giver (2) than receiver (1) to incentivize community engagement
- Party adventure logs deferred — may be better as a scene/story integration feature
- Journal categories (relationship notes, adventure logs) replaced by freeform tags
