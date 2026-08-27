# Schema-only migrations pre-production

**Status: SUPERSEDED (2026-08-26) by
[ADR-0237](0237-alpha-is-durable-the-production-database-is-the-master-copy.md).**
Do not follow this ADR. Its premise expired when alpha authoring began: the
production database now holds authored content that exists nowhere else, and a
migration that drops or renames an authored-content column must carry a
`RunPython` backfill in the same migration. The no-backfill shortcut survives only
for play-state tables, which alpha declares resettable. Historical decisions that
cite this ADR (delete-instead-of-backfill in pre-alpha migrations, ADR-0195's
collapse, ADR-0154's parameter rework) were correct when taken and are not
reopened by this supersession.

*Original text, for the record:*

> Before launch we write schema migrations only — no `RunPython` data migrations or backfills — because
> the dev database is disposable and holds no meaningful rows to preserve; we rejected defensive
> backfills. There is nothing to migrate yet, so backfill code would be untested ballast.
>
> > Status: accepted · Source: CLAUDE.md
