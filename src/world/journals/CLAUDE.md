# Journals App

Character journal system for public/private writing, praises, retorts, and weekly XP awards.

## Models

### JournalEntry
Individual journal entries. FK to CharacterSheet (author). Optional self-FK for responses.
- title, body, is_public (boolean), response_type (praise/retort/null)
- parent FK (self) for response linking
- created_at, edited_at, ic_timestamp (future IC time integration)

### JournalTag
Freeform tags on entries. FK to JournalEntry. Unique per entry+name.

### WeeklyJournalXP
Per-character weekly XP tracking. Resets after 7 days.
- posts_this_week counter, boolean flags for praise/retort given/received
- Timestamp-based weekly reset (same pattern as relationships app)

## Service Functions

- `create_journal_entry()` — Creates entry, awards weekly XP, emits achievement stats
- `create_journal_response()` — Creates praise/retort, awards XP to giver and receiver
- `edit_journal_entry()` — Edits title/body, sets edited_at

## XP Schedule (weekly reset)

| Action | XP |
|---|---|
| 1st/2nd/3rd post | 5/2/1 |
| Praise given | 2 |
| Praised received | 1 |
| Retort given | 1 |
| Retort received | 3 |

## API Endpoints

- `GET /api/journals/entries/` — Public feed with ?author= and ?tag= filters
- `GET /api/journals/entries/mine/` — Own entries (includes private)
- `GET /api/journals/entries/<id>/` — Single entry detail
- `POST /api/journals/entries/` — Create entry
- `PATCH /api/journals/entries/<id>/` — Edit entry (owner only)
- `POST /api/journals/entries/<id>/respond/` — Praise or retort

## Integration Points

- **Achievements**: Emits `journals.total_written`, `journals.total_public` stats
- **Progression**: Awards XP via `award_xp()` service
- **Fame**: Praises should emit fame signal (not yet built)
- **Relationships**: Retorts should validate antagonistic relationship (not yet enforced)
