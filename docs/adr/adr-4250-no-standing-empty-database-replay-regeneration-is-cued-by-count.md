# ADR-4250: No standing empty-database migration replay; regeneration is cued by a migration count

The nightly workflow that replayed the whole `arxii` chain into an empty Postgres (ADR-0083's
standing replay coverage) was retired. It proved only that a database can be built from nothing,
which production never does: production applies new migrations on top of its own history, and
the failures that reached it (`0220_upbringings`, the `0149` constraint, the `0170` re-level, see
ADR-4246) were data-dependent, invisible to any empty database. The replay also signalled only
by a cron-failure email and stayed red for five weeks after an unrelated settings change (#3614),
with a false-green replay step hiding that it had applied nothing. In that time #3925 broke
replay-from-zero at `0101`, and nobody saw it. What the replay checked that still matters is
covered where it matters: each regeneration replays the new chain and diffs its schema against
the model-built one (`just verify-regeneration`, ADR-0276), per-PR CI keeps the models-vs-migrations
drift gate, and a data migration is proven against a copy of production
(`reviewing-migrations` skill). The one output nothing else produced, ADR-0276's "regeneration
due" cue, is now a monthly job (`.github/workflows/migration-regeneration-due.yml`) that counts
incremental migrations since the current generation with no database or Django settings and
opens an issue at 100 (`tools/check_regeneration_due.py`). **Accepted:** between regenerations,
the current chain may stop replaying from zero without anyone being told; the next regeneration
replaces it wholesale. **Rejected:** keeping the replay and fixing it (it guards a path production
never takes, and a scheduled job that alerts by email had already failed once); running it per-PR
on migration paths (about 7 minutes per migration-bearing PR to protect the same unused path);
replacing the 30-minute wall-time trigger with another replay (a count needs no database to measure).

> Status: accepted (2026-10-12, TehomCD) · Source: issue #4250 · Amends ADR-0083 and ADR-0276's trigger
