# Partitioned interaction metadata carries the timestamp key

`Interaction` is range-partitioned and its database identity is `(id, timestamp)`, so read receipts and durable pose-submission records carry the timestamp and use PostgreSQL composite foreign keys for integrity and cascade cleanup. We reject a single-ID bridge (which can point at the wrong partition) and do not backfill historical rows because the approved environment contains no legacy interaction data; ephemeral submissions remain explicitly null in both reference columns.

> Status: accepted · Source: issue #3951 stakeholder approval (2026-09-20)
