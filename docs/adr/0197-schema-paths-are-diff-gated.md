# Schema-construction paths are held equivalent by a nightly diff, names excluded

**Decision:** the two supported schema-construction paths (`arx manage migrate`, production's
path, and `tools/build_schema.py`, used by CI, the Postgres parity tier, and the devcontainer)
are held equivalent by a nightly `pg_catalog` diff (`tools/compare_schemas.py`), and constraint
and index **names** are compared by definition rather than by name.

**Why:** the two paths disagree on roughly fifty object names purely because `schema_editor`
hashes a different construction order; names are not semantic in Postgres and nothing here
depends on ours. A name-sensitive diff would need a fifty-entry allowlist that nobody would
maintain, and noise that large is how a real difference gets missed - which is exactly how
#2982 survived ADR-0195's hand-run diff.

**Rejected:** renaming ~50 constraints and indexes so the allowlist could be empty (semantically
inert churn across a lot of DDL, chasing a hash difference); and asserting only that the
partition exists (guards the one object already known to have been lost, and nothing else).

**Trade-offs:** a genuinely wrong constraint *name* will not be caught. Accepted - no code in
this repo resolves a constraint by name, and `ON CONFLICT ON CONSTRAINT` is unused. Three
vendored Django/allauth through-table PK-width differences remain allowlisted with a stated
reason, since CLAUDE.md forbids editing dependency code.

> Status: accepted · Source: #2982 · Related: ADR-0083 (CI schema from models), ADR-0195
> (single-app collapse's now-corrected equivalence claim), ADR-0018 (range-partition the
> Interaction table)
