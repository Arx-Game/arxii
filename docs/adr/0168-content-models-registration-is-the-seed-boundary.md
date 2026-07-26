# CONTENT_MODELS registration *is* the seed/content boundary; seeders look content up and invent only under SEED_SAMPLE_CONTENT

ADR-0142 established that the Big Button loads real content from arx2-lore and that
arxii seeds keep "only non-lore config/lookup tables". It did not say how to decide
which is which, and in practice the decision was made per-model by shape — is this a
singleton, a closed vocabulary, an open-ended named instance — which produced
arguments rather than answers. `CheckType` has the name "Melee Attack" and is plainly
mechanical; `Organization` has the name "Shroudwatch Academy" and is plainly lore; a
`ConditionCategory` is neither obviously.

The cost of getting it wrong is not theoretical. `export_to_content_repo` captures
every row in a `CONTENT_MODELS` model, so a seeded row is indistinguishable from an
authored one once exported. That is how `Beginnings` "Commoner" and "Noble",
`StartingArea` "Arx City" and "Luxen Port" reached the content repo and sat there
looking authored — three of them with 19–50 character descriptions against the
authored set's 924–1511, and no `BeginningTradition` rows at all. Deleting them by
hand doesn't hold: the next press recreates them and the next export re-captures them.

## Decision

**The line is already drawn, in code: `CONTENT_MODELS`.**

> If a model is in `CONTENT_MODELS`, the content repo owns it and no seeder may
> create rows in it. If it is not, the seeder owns it.

No per-model classification, no shape heuristic, no curated allowlist to argue over.
The registration that decides what gets exported is the same registration that decides
what may be seeded — one fact, two consumers, so they cannot drift.

The audit that settled it: **all 70 content models the seeders still populated are
already authored in the content repo**, usually with far more rows —
`magic.technique` 33 seeded against 278 authored, `conditions.conditiontemplate` 48
against 183, `checks.checktype` 42 against 72. Zero exceptions. The seeders were
producing a thin subset of content that already existed, and that overlap is exactly
where slop hides.

The converse holds too, and is why a press stays mandatory: the genuine config the
Big Button must provide — `CheckRank`, `ResultChart`, `CheckOutcome`,
`ConsequencePool`, `ActionTemplate`, `PointConversionRange`, `Pronouns`, `Heritage` —
never appears in that audit, **because none of it is in `CONTENT_MODELS`**. The
seeders own precisely the models the content repo does not. "Just don't press the
button" was never available; without a press no check resolves.

**Seeders look content up; they never create it.** `world.seeds.sample_content.
authored_or_sample()` is the single call site shape — a drop-in for `get_or_create`
that returns the authored row, or returns `None` after logging which row is missing.
A caller that gets `None` skips the config wired to that row; it never falls back to
creating it. Config itself (anything outside `CONTENT_MODELS`) keeps seeding
unconditionally, so the press still yields a bootable game.

**`SEED_SAMPLE_CONTENT` (`ARXII_SEED_SAMPLE_CONTENT`, default off) is the one
exception, and it exists for third parties, not for us.** A clone with no content
repo needs *a* starter set. Maintainers keep it off and author in the content repo.
The sample definitions are gated, never deleted — that path stays covered by tests
carrying `@override_settings(SEED_SAMPLE_CONTENT=True)`.

**The guard is a ratchet that may only shrink.** `world.seeds.tests.
test_no_content_slop` loads a stub content root, snapshots per-model counts,
runs the cluster seeders, and fails naming any `CONTENT_MODELS` entry that gained
rows. Adding an entry to silence a failure is the tempting wrong move and the failure
message says so: a new entry means a seeder began inventing content.

The snapshot is taken **between** the content load and the cluster loop, not across
the whole `seed_dev_database()` call — hence `load_content_first()` being split out.
Measuring across the whole call scores the content loader's own writes as seeder
growth, which put four models on the ratchet that no seeder touches at all.

**Config never goes in `CONTENT_MODELS`, and a wrong registration is fixed by
de-registering — never by authoring** (TehomCD, 2026-07-25). The rule above says
what to do *given* a registration; it does not make every registration correct.
Because the same set now drives both the export and the seeder guard, a
mechanical table registered by mistake does more than bloat the corpus: it tells
the seeder to stop producing something the game needs.

Three pk-keyed tuning singletons were de-registered on that basis:
`magic.fallredemptionconfig`, `covenants.mentorbondconfig`,
`magic.soultetherconfig`. Each declares `NaturalKeyConfig.fields = ["pk"]`, and
the export writes no `pk` — so `load_entries` can never resolve their identity.
Two of them had shipped fixtures sitting in the lore repo carrying real tuned
values (`celestial_to_abyssal_multiplier: 1.50`, `band_width: 2`) that loaded
**zero rows**; the seeder then wrote its own defaults over the top, and
`MentorBondConfig`'s seeder uses `update_or_create`, so those authored numbers
never once reached a database. A "pk" natural key carries no content identity,
and a table whose entire payload is tuning multipliers with model-level defaults
is config.

## What this rejects

**A curated `SEEDER_ALLOWED_CONTENT_MODELS` allowlist.** Earlier drafts proposed one,
reasoning that models like `checks.checktype` are in `CONTENT_MODELS` *and*
legitimately seeded because content fixtures FK them by natural key. That premise is
false: `load_entries` resolves FKs by natural key **against the database**, not
against the fixture set, so the referenced row only has to exist first — which the
seed ordering already guarantees. The working proof is `actions.actiontemplate`,
which is not in `CONTENT_MODELS` while 278 lore `Technique` fixtures FK its
"Technique Cast" row by natural key and load cleanly. An allowlist would have made
every entry a standing argument; the rule makes the target zero.

**Classifying by table shape** (singleton / closed vocabulary / open-ended named
instance). A reasonable proxy that produced real disagreement at the margin. The
registration is the actual line, and it is already written down.

**Moving config *out* of `CONTENT_MODELS`** to make a contentless clone work. That is
a separate migration — it costs writing seeders for ~600 rows of declarative JSON —
and `SEED_SAMPLE_CONTENT` addresses the same need without it.

Related: ADR-0142 (which this sharpens), ADR-0140 (the content pipeline), ADR-0013
(no data migrations pre-production). Issue #2698.
