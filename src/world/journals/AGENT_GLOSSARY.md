# Journals glossary

Domain-local vocabulary for `world.journals` (the diary/reflection system, #2160). Root terms
live in `AGENT_GLOSSARY_MAP.md`.

- **Journal Entry** — a `JournalEntry`: a character's own diary/reflection writing, public or
  private, authored by their `CharacterSheet`. This is the canonical "journal" — free-text,
  player-voiced, no mechanical parsing. Web surface: **World › Journals** at `/journals` — one
  stream, newest first, opened in place, with a Search panel, a character-journal view
  (`?writer=<id>`), and "Your journal" (`?mine=1`), #3941 — plus a `JournalTab` quick-compose in
  the in-scene sidebar; telnet: `journal write|respond|edit|disposition|consent`. _Avoid:_ **the journal**
  unqualified when another app's homonym is in scope — see Disambiguation below.
- **White journal / Black journal** — the interface's words for the public/private axis
  (`JournalEntry.is_public`, #3941); the model field itself keeps its name, never renamed to
  match. **White**: everyone who can reach the entry reads it. **Black**: only the writer and
  staff do — staff simply aren't filtered on the same stream, never routed to a separate read
  surface. _Avoid:_ "public"/"private" as interface copy — those are the model's words, not the
  reader's; the band on a black row says only "Black journal," nothing more.
- **About** — `JournalEntry.about`, a nullable FK to `CharacterSheet` naming the one character an
  entry is about (#3941), so the record of a tie reads as a sequence instead of being
  reconstructed from tags. Not a tag (no identity, no machinery) and not a
  `CharacterRelationship` (that needs the subject's mutual consent, which an entry written about
  someone must never require). Filterable from both sides: `?about=<id>` alone is everything
  written about that sheet; combined with the writer filter it narrows to one writer's entries
  about that subject.
- **Introductions** — the three white journals character generation writes in the
  character's own voice (#3621), found by `JournalEntry.kind` (`JournalKind`): the **First
  Journal** (to the Great Archive of Vellichor; offered on an Arx start, otherwise written at
  the Archive in play), **An Application to Shroudwatch Academy**, and **The Whispers**
  (rumors of deeds and misdeeds, one per line, each also a Level-1 flavor Secret with gossip
  heat). _Avoid:_ papers, backstory journals.
- **Praise** — a `JournalEntry` with `response_type=praise`, a self-FK response to another
  entry (via `parent`). Affirms the parent entry; awards weekly XP to both the giver and the
  receiver.
- **Retort** — a `JournalEntry` with `response_type=retort`, the antagonistic counterpart to
  Praise. Also a threaded response via `parent`; awards weekly XP asymmetrically (retort given
  is worth less than retort received — see `journals/CLAUDE.md`'s XP schedule). Consent-gated —
  see Retort Consent below.
- **Condemn** — a `JournalEntry` with `response_type=condemn` (`ResponseType.CONDEMN`, #3941,
  ADR-0307): Praise's antagonistic opposite, a threaded response via `parent` exactly like
  Retort. Gated by the same Retort Consent rule and awards the same weekly XP
  (`CONDEMN_GIVEN_XP`/`CONDEMN_RECEIVED_XP` alias `RETORT_GIVEN_XP`/`RETORT_RECEIVED_XP`).
- **Retort Consent** — `CharacterSheet.retort_consent` (`RetortConsent`: RIVALS default /
  ANYONE, #3941, ADR-0307): who may Retort or Condemn this character's entries. RIVALS means a
  mutual hostile relationship label with the writer (#3957,
  `world.relationships.services.mutual_hostile` — one function, `journals.services.can_retort`
  calls it without reimplementing the predicate); ANYONE opens the door to every reader. Praise
  and a Nomination are never gated by this. _Avoid:_ a per-entry toggle — the dial is about who
  may address the writer, not about any one piece of writing.
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
- **Post Mortem** — the interface's word (#3941) for a revealed `JournalEntry` (`revealed_at` set
  — see Reveal); the band on its row and the Search filter (`?post_mortem=1`) both say "Post
  mortem." Not public, so it takes no Praise, Retort, Condemn, or Nomination — the response and
  nomination paths both check `is_public`, which a reveal never sets. _Avoid:_ "revealed after
  death" as interface copy — that phrasing stays fine in developer prose (this file, ADR-0229),
  but the reader-facing word is "Post mortem."
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
