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
- **Posthumous Disposition** — the fate of a private entry after its author's death (#3287):
  `CharacterSheet.posthumous_journal_disposition` (REVEAL default / SEAL) is the sheet-wide
  default; `JournalEntry.posthumous_override` (INHERIT default / REVEAL / SEAL) lets one entry
  deviate. Resolved by `JournalEntry.effective_posthumous_disposition()`. SEAL always wins,
  even over a bequest grant. _Avoid:_ visibility (that word means the public/private axis, a
  different thing — see Disambiguation below).
- **Reveal** — stamping `JournalEntry.revealed_at`/`revealed_by_settlement` on a private entry
  whose effective disposition is REVEAL, done by
  `services.reveal_journals_for_settlement` at estate settlement (`estates.services.
  execute_settlement`, #3287). Never mutates `is_public` — a revealed entry stays a *private*
  entry that has surfaced, not a converted-to-public one; the public feed includes it via
  `revealed_at__isnull=False`, not `is_public=True`.
- **Journal Bequest Grant** — `JournalBequestGrant` (#3287): a recipient_sheet/deceased_sheet
  pair minted by `services.grant_journal_bequest` only when a will carries an
  `estates.BequestKind.WRITINGS` line, giving the recipient read access to the deceased's
  non-sealed private entries. _Avoid:_ inheritance (too broad — this app never says
  "inherited," estates does).

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
