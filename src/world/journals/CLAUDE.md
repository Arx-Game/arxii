# Journals App

Character journal system for public/private writing (the interface calls these White/Black,
#3941), praise/retort/condemn responses, relationship journals, and weekly XP awards. Read at
**World › Journals**, the Reading Room (#3941) — see `docs/roadmap/journals.md` for the page.

## Models

### JournalEntry
Individual journal entries. FK to CharacterSheet (author). Optional self-FK for responses.
- title, body, is_public (boolean), response_type (praise/retort/condemn/null)
- `about` — nullable FK to `CharacterSheet`: the one character this entry is about (#3941). Not
  a tag (no identity) and not a `CharacterRelationship` (needs the subject's consent, which an
  entry about someone must not require).
- parent FK (self) for response linking
- created_at, edited_at, ic_timestamp (stamped from `game_clock.services.get_ic_now()` at
  creation, #3941; stays null when no `GameClock` is active)

Two related `CharacterSheet` columns live in `character_sheets/models.py`, not here:
`retort_consent` (`RetortConsent`: RIVALS default / ANYONE) and `journals_visited_at` (one
since-last-visit timestamp per character, #3941).

### JournalTag
Freeform tags on entries. FK to JournalEntry. Unique per entry+name.

### WeeklyJournalXP
Per-character weekly XP tracking. Resets after 7 days.
- posts_this_week counter, boolean flags for praise/retort given/received
- Timestamp-based weekly reset (same pattern as relationships app)

## Service Functions

- `create_journal_entry()` — Creates entry (accepts `about`), awards weekly XP, emits achievement stats
- `create_journal_response()` — Creates praise/retort/condemn, awards XP to giver and receiver;
  raises `JournalError.UNAVAILABLE` for retort/condemn when `can_retort()` fails (ADR-0306)
- `edit_journal_entry()` — Edits title/body/about, sets edited_at (about/clear_about alone does not)
- `visible_entries_q(*, viewer_sheet, is_staff)` — the one visibility rule (#3941 Decision 1) as
  a `Q`: public, or revealed at settlement, or the viewer's own, or (staff) everything
- `can_retort(*, viewer_sheet, author)` — ADR-0306 predicate: True when `author.retort_consent`
  is ANYONE, or an active, non-pending `CharacterRelationship` exists between the two (either
  direction) with progress on a negative-sign track
- `annotate_can_retort(queryset, viewer_sheet)` — the same predicate as one `Case` + `Exists`
  annotation (`viewer_can_retort`) on the stream and `mine/` querysets, so a page costs one
  query, not one per row; the serializer prefers the annotation and falls back to `can_retort()`
- `set_retort_consent()` — Sets the caller's `retort_consent`
- `mark_journals_visited()` — Stamps `journals_visited_at` at `at`
- `journal_settings()` — Returns the owner's `JournalSettings` (disposition, retort_consent,
  posts_this_week, rewarded_posts_per_week) for the settings endpoint / desk

## Visibility rule (#3941 Decision 1)

An entry is readable when it is public, or revealed by an estate settlement
(`revealed_at` set), or the caller is its author, or the caller is staff (`is_staff` — staff are
simply not filtered, never a separate read path), or the caller holds a `JournalBequestGrant`
over the author and the entry is not sealed (`entry_visible_via_bequest`, unchanged from #3287).
`get_queryset()` (list) implements the first four as `visible_entries_q()`; `retrieve()` (detail)
uses the same four plus the bequest branch. `?deceased=<id>` (`JournalEntryFilter.filter_deceased`)
replaces the queryset outright for bequest browsing rather than narrowing it — a different shape
(the deceased's non-sealed private+public corpus). Block/mute exclusion
(`exclude_blocked_and_muted_authors`) applies only to the list/feed path (`get_queryset()`) —
`retrieve()` (detail) never calls it; a mute's only effect at the detail path is the separate
response-list filtering described under Integration Points below.

## XP Schedule (weekly reset)

| Action | XP |
|---|---|
| 1st/2nd/3rd post | 5/2/1 |
| Praise given | 2 |
| Praised received | 1 |
| Retort given | 1 |
| Retort received | 3 |
| Condemn given | 1 (`CONDEMN_GIVEN_XP` aliases `RETORT_GIVEN_XP`) |
| Condemn received | 3 (`CONDEMN_RECEIVED_XP` aliases `RETORT_RECEIVED_XP`) |

Condemn shares Retort's weekly flags (`retorted_this_week`/`was_retorted_this_week`) — one
antagonism budget, not two.

## API Endpoints

- `GET /api/journals/entries/` — Visible-entries stream (see Visibility rule above). Filters:
  `author` (id), `writer` (name contains, #3941), `tag`, `about` (sheet id, #3941), `kind`
  (`JournalKind` value or the `introductions` alias, #3941), `post_mortem=1` (revealed entries,
  #3941), `since=<iso datetime>` (entries created after that moment, #3941), `black_only=1`
  (staff only, #3941), `deceased=<sheet_id>` (bequest browsing, #3287). The response carries
  `visited_at` (the caller's visit mark as it stood before this request) and `since_visit_count`
  (entries newer than that mark); `?mark_visit=1` then advances the mark, so the client filters
  its "since your last visit" cut with `since=<visited_at>`. Both keys are absent on a
  `?deceased=` listing. Rows carry `about`, `about_name`, `author_persona_id`, `ic_timestamp`,
  `can_retort`, `is_own` (#3941).
- `GET /api/journals/entries/mine/` — Own entries (includes private)
- `GET /api/journals/entries/<id>/` — Single entry detail
- `POST /api/journals/entries/` — Create entry (accepts `about`, #3941)
- `PATCH /api/journals/entries/<id>/` — Edit entry (owner only; accepts `about`, null clears it)
- `POST /api/journals/entries/<id>/respond/` — Praise, Retort, or Condemn (`response_type`,
  #3941); Retort/Condemn refuse with `JournalError.UNAVAILABLE` when `can_retort()` fails
- `GET/PATCH /api/journals/entries/disposition/` — the owner's journal settings (#3941, widened
  from #3287's disposition-only endpoint): GET returns `posthumous_journal_disposition`,
  `retort_consent`, `posts_this_week`, `rewarded_posts_per_week`; PATCH accepts `disposition`
  and/or `retort_consent` (at least one required), each applied through its own Action
  (`set_journal_disposition` / `set_retort_consent`) — the same seams telnet's `journal
  disposition`/`journal consent` commands use.

## Integration Points

- **Achievements**: Emits `journals.total_written`, `journals.total_public` stats
- **Progression**: Awards XP via `award_xp()` service
- **Fame**: Praises should emit fame signal (not yet built)
- **Relationships (#3941, ADR-0306)**: Retort and Condemn are enforced against
  `world.relationships.models.CharacterRelationship` in `can_retort()` — an active, non-pending
  relationship in either direction with progress on a negative-sign track counts as a rival;
  `retort_consent=ANYONE` bypasses the relationship check entirely. This structural "rival" is
  provisional: a dedicated Rivalry relationship kind is a later relationships-pass item, and
  `can_retort` is the one place that will narrow when it lands.
- **Account block/mute (#2996)**: `services.exclude_blocked_and_muted_authors` filters the
  public feed (`JournalEntryViewSet.list`) — an account-level `Block` hides an author's entries
  from a viewer **both directions** (`world.scenes.block_services.blocked_player_ids_for`); an
  account-level `Mute` only narrows the **muter's own** feed
  (`world.scenes.mute_services.muted_player_ids_for`). `services.create_journal_response` rejects
  a praise/retort/condemn with the neutral `JournalError.UNAVAILABLE` when an account-level
  `Block` sits between the responder and the parent entry's author (`world.scenes.block_services
  .account_block_active`) — one of #2996's two reject-before-write exceptions (the other is
  `friend_services.add_friend`, see `world/scenes/CLAUDE.md`), since the rejection here can't
  leak a block by itself. A `Mute` never rejects a response — it persists
  normally and is excluded only from the entry AUTHOR's own read of responses to their own entry
  (`JournalEntryViewSet.retrieve`, `world.scenes.mute_services.account_muted`); any other viewer
  sees the full list.
