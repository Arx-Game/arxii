# Journals glossary

Domain-local vocabulary for `world.journals` (the diary/reflection system, #2160). Root terms
live in `AGENT_GLOSSARY_MAP.md`.

- **Journal Entry** — a `JournalEntry`: a character's own diary/reflection writing, public or
  private, authored by their `CharacterSheet`. This is the canonical "journal" — free-text,
  player-voiced, no mechanical parsing. Web surface: `/journals` (composer, feed, own-entries
  tab) plus a `JournalTab` quick-compose in the in-scene sidebar; telnet: `journal
  write|respond|edit`. _Avoid:_ **the journal** unqualified when another app's homonym is in
  scope — see Disambiguation below.
- **Praise** — a `JournalEntry` with `response_type=praise`, a self-FK response to another
  entry (via `parent`). Affirms the parent entry; awards weekly XP to both the giver and the
  receiver.
- **Retort** — a `JournalEntry` with `response_type=retort`, the antagonistic counterpart to
  Praise. Also a threaded response via `parent`; awards weekly XP asymmetrically (retort given
  is worth less than retort received — see `journals/CLAUDE.md`'s XP schedule).
- **Weekly Journal XP** — `WeeklyJournalXP`, a per-character rolling 7-day counter
  (`posts_this_week`, praise/retort given/received flags) gating the diminishing per-post XP
  award. Resets on a timestamp check, not a scheduled job — same pattern as `relationships`.

## Disambiguation — "journal" is a homonym across apps

Three unrelated systems use the word "journal." Always qualify which one is meant:

- **This app's Journal Entry** (above) — a diary/reflection post.
- **The missions ledger** — `world.missions` calls its per-run activity record "the journal"
  (`/api/missions/journal/`, moved off the `/journal` web route in #2160 to free the namespace
  for this app). Per `missions/AGENT_GLOSSARY.md`: "the journal is the ledger; the tale is the
  narration" — the missions journal is a structured run ledger, not free-text reflection, and
  its player-authored counterpart is the `MissionRunTale`, not a Journal Entry.
  _Avoid:_ calling the missions ledger "a journal entry" — that phrase means this app's model.
- **The held-clue journal** — `world.clues`' read surface
  (`GET /api/clues/held/`, `HeldClueSerializer`) is informally called "the held-clue journal" in
  `docs/systems/INDEX.md` — a scoped list of clues a character holds, not a writable diary and
  not owned by this app.
