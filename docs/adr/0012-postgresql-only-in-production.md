# PostgreSQL-only in production; use PG features directly

Production targets PostgreSQL and we use its features directly — CTEs, partitioning, `DISTINCT ON`,
BRIN, materialized views, JSONB — with no DB-agnostic abstraction layer; we rejected portability. The
cost is real and shows up as occasional SQLite fast-tier divergences, which we accept in exchange for
PG power, with the Postgres parity tier as the gate.

> Status: accepted · Source: CLAUDE.md
