# Schema-only migrations pre-production

Before launch we write schema migrations only — no `RunPython` data migrations or backfills — because
the dev database is disposable and holds no meaningful rows to preserve; we rejected defensive
backfills. There is nothing to migrate yet, so backfill code would be untested ballast.

> Status: accepted · Source: CLAUDE.md
