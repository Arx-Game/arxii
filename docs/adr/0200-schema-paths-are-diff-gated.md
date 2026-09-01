# ADR-0200: Schema-construction paths are held equivalent by a nightly diff, names excluded

**Decision:** the two supported schema-construction paths (`arx manage migrate`, production's
path, and `tools/build_schema.py`, used by CI, the Postgres parity tier, and the devcontainer)
are held equivalent by a nightly `pg_catalog` diff (`tools/compare_schemas.py`), and constraint,
index and sequence **names** are compared by definition rather than by name.

**Extended 2026-09-01 (#3544) to sequences.** Sequence rows were originally keyed on the
sequence's own `relname`, which the "names are not semantic" reasoning below should always have
covered. Postgres does not rename a sequence when its owning table is renamed, so every
`RenameModel` left the migrate-built database holding the pre-rename sequence name where
`build_schema.py` had created the post-rename one for an identical column — a guaranteed,
permanent false red per rename, and one that had held the nightly down for six consecutive
nights. Sequence rows now key on the owning `(table, column)` resolved through `pg_depend`,
which preserves the int-vs-bigint PK-width signal the section exists for (that is about the
sequence's *type*) while making a rename a non-event. A sequence with no owning column falls
back to its own name so it is still compared rather than dropped.

**Why:** the two paths disagree on roughly fifty object names purely because `schema_editor`
hashes a different construction order; names are not semantic in Postgres and nothing here
depends on ours. A name-sensitive diff would need a fifty-entry allowlist that nobody would
maintain, and noise that large is how a real difference gets missed - which is exactly how
#2982 survived ADR-0195's hand-run diff.

**Rejected:** renaming ~50 constraints and indexes so the allowlist could be empty (semantically
inert churn across a lot of DDL, chasing a hash difference); and asserting only that the
partition exists (guards the one object already known to have been lost, and nothing else).
For the sequence extension, also rejected: allowlisting each renamed pair (a per-`RenameModel`
treadmill that grows the allowlist with entries that are noise, destroying the property that a
non-empty diff is always signal), and emitting `ALTER SEQUENCE ... RENAME` in each rename
migration (real DDL against production to fix a name nothing reads, and it would have to be
remembered for every future rename).

**Trade-offs:** a genuinely wrong constraint *name* will not be caught. Accepted - no code in
this repo resolves a constraint by name, and `ON CONFLICT ON CONSTRAINT` is unused. Three
vendored Django/allauth through-table PK-width differences remain allowlisted with a stated
reason, since CLAUDE.md forbids editing dependency code. `compare_schemas.py` also does not
compare view and materialized-view defining queries, functions, triggers, or extensions - only
`pg_catalog` object presence and shape. There is no divergence today because both paths apply
the same `.sql` files, but a query, function, trigger, or extension could drift silently
between the two paths without this diff catching it.

> Status: accepted · Source: #2982 (extended by #3544) · Related: ADR-0083 (CI schema from
> models), ADR-0195 (single-app collapse's now-corrected equivalence claim), ADR-0018
> (range-partition the Interaction table)
