# No JSON fields; every setting is a typed, queryable column

Each setting or configuration gets a real column with FKs, validation, and DB constraints so all data
is queryable with the ORM and indexable; we rejected JSON-blob flexibility because it forfeits
queryability and validation. The one ratified exception is the `eligibility_rule` predicate JSONField,
where the value is an opaque rule expression rather than queried state.

> Status: accepted · Source: CLAUDE.md, npc_services/models.py
