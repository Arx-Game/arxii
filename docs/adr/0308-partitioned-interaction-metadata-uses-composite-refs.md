# Partitioned interaction metadata carries the timestamp key

`Interaction` is range-partitioned and its database identity is `(id, timestamp)`, so read receipts and durable pose-submission records carry the timestamp and use PostgreSQL composite foreign keys for integrity and cascade cleanup. Django (including 5.2 `CompositePrimaryKey`) does not support foreign keys to partitioned/composite-key models (django-postgres-extra documents this limitation; Django tickets #35956 and #36034 remain unresolved), so the ORM stores scalar `interaction_id` plus `timestamp` and uses an ORM-only `ForeignObject` relation with `DO_NOTHING`; it must not expose a database `ForeignKey` or rely on id-only cascade behavior. Explicit resolvers and the relation descriptor fail closed if Evennia's scalar-id identity map returns a row with a different timestamp. We reject a single-ID bridge and do not backfill historical rows because the approved environment contains no legacy interaction data; ephemeral submissions remain explicitly null in both reference columns. Numeric interaction IDs are globally unique from the sequence; duplicate IDs across partitions are unsupported by Evennia's identity map and require a future identity-registry redesign.

> Status: accepted · Source: issue #3951 stakeholder approval (2026-09-20)
>
> Implementation evidence: [exact-revision ledger](https://github.com/Arx-Game/arxii/issues/3951#issuecomment-5769223079); live UI acceptance remains tracked under #3751.
> Evidence scope: backend integrity and ORM parity; player-facing acceptance remains outside this ADR.
