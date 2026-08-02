# ADR-0191: The content export withholds additions by default

**Status:** Accepted · **Date:** 2026-08-02 · **Issue:** #2890 (surfaced by #2736 / ArxII-lore#36)

An export to the content repo may **update** rows the corpus already has, but by default it
will not **add** rows the corpus does not have. A row whose natural key is absent from the
target fixture is withheld and reported; `allow_additions` (a CLI flag and an admin
checkbox) is the authoring path that pushes it. Refuses-by-default, not warns-by-default:
a warning printed after the write has already lost.

**Why.** ADR-0168 settled that a model in `CONTENT_MODELS` is owned by the content repo and
no seeder may create rows in it, and `authored_or_sample` enforces that on the seeding side
— it creates nothing unless `SEED_SAMPLE_CONTENT` is on. But sampling is a *legitimate*
path: it exists so a third party with no content repo gets a bootable starter set. Once
those rows exist they are indistinguishable from authored ones, and the export shipped them
as lore.

That is not a hypothetical. `magic/resonance.json` in the content repo held twelve
resonances, **none of them authored** — eleven were sample rows, one came from a test-only
path — while 22 of the 24 canonical resonances were missing entirely and Praedari carried a
canonically wrong affinity (Primal, where canon has it Abyssal). A design round on #2736 was
built on that invented vocabulary before anyone noticed. So the seeding half of ADR-0168 was
closed and the export half was open; this closes it.

**Rejected.** *A sample-provenance registry* — `authored_or_sample` has exactly one
`create` call serving 420 call sites, so recording `(model_label, natural_key)` there would
be a one-line choke point and precise, with no confirmation step in the good case. It is
**forward-only**: it cannot clean a database sampled before it landed, which is every
existing one, and its backfill would have no ground truth other than "diff against the
corpus" — which is this ADR. *A per-model `is_sample` column* — 145 models across 28 apps.
*Refusing to export from any database ever sampled* — a single boolean cannot be honestly
unset, so one sampling run would bar a maintainer from exporting forever. *Exporting only
natural keys the corpus already has, with no opt-in* — that is this design minus the escape
hatch, and it would stop staff authoring in admin from ever reaching the corpus, which
`EXPORT_FILTERS`' own comment says must keep working.

**Consequences.**

- **Export is no longer one silent command.** A maintainer who authored fifty rows in admin
  confirms fifty additions. The report groups per model to blunt it. This is the cost, and
  it was accepted deliberately over the silent-and-precise alternative.
- **The gate is not sample-specific**, which is a feature: anything a test, a stray script
  or a half-finished import left in a content table is caught by the same rule, with no
  column, table or migration to carry.
- **Three cases bypass it**, because blocking them would be wrong rather than safe: a model
  with no fixture file yet (genuinely new — every row is a first export), a model with no
  usable identity (`NaturalKeyMixin.identity_fields()` returns `None`, including the `["pk"]`
  keys ADR-0168's note already de-registered), and a **prose domain whose directory holds no
  entries**. That last one is the subtle one: prose domains write one markdown file per
  entry, so "file absent" means "new entry", which on a virgin corpus is true of *every*
  entry. Keying the gate per entry silently withheld the entire corpus and surfaced only as
  an unrelated load-sequencing test losing its deferred-FK resolution. The gate keys on the
  domain.
- **A model whose rows are all withheld writes nothing**, rather than `[]` — which would
  empty the corpus file outright, the exact harm the gate exists to prevent.
- **Identity compares serialized field values**, not model-level `natural_key()` tuples, so
  both sides of the diff come from the same serializer settings and cannot disagree about
  how an FK is represented.
- **`NaturalKeyMixin.identity_fields()` is new** — the class-level question "can rows of this
  model be identified at all", as against `natural_key()`'s instance-level "what is this
  row's identity", which raises where this degrades to `None`.
- **This does not fix deletions.** An export still writes only what the database holds, so a
  database that is a subset of the corpus still drops rows from the models it does write.
  That hazard predates this ADR and is out of its scope; the content repo's own README
  already warns about it.

Extends ADR-0168 (the seeding half) rather than superseding it.
