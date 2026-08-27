# All concrete models use SharedMemoryModel

Every concrete model inherits `SharedMemoryModel` (imported from `evennia.utils.idmapper.models`, never
`evennia.utils.models`) and we trust its identity-map cache rather than hand-rolling `resolve_*` /
`batch_fetch_*` helpers or manual cache-flushing; we rejected plain `models.Model` plus bespoke
caching. Reinventing the cache fights the idmapper instead of using it.

> Status: accepted · Source: sharedmemory-model skill

## Addendum (2026-08-27, Apostate ruling 7): rollback staleness

Trusting the identity-map cache has a sharp edge: a `transaction.atomic()` block that
mutates a cached `SharedMemoryModel` instance in place and *then* raises rolls back the
database row but not the mutated Python object — nothing about a rollback touches
process memory, and Evennia disables the `request_finished` flush that would otherwise
clear it. The phantom value then survives for the process lifetime and poisons the next
read. Ruling: no rollback hook (too expensive, treats the symptom) — instead a
convention (complete all validation/raises before the first in-place mutation inside an
atomic block) enforced by a narrow AST lint,
`tools/lint_idmapper_mutation_order.py` (`# noqa: IDMAPPER_MUTATE_ORDER` to suppress).
Full writeup: `django_notes.md`'s "Idmapper Rollback Staleness" section.
