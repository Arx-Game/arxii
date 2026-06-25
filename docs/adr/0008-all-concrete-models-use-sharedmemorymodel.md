# All concrete models use SharedMemoryModel

Every concrete model inherits `SharedMemoryModel` (imported from `evennia.utils.idmapper.models`, never
`evennia.utils.models`) and we trust its identity-map cache rather than hand-rolling `resolve_*` /
`batch_fetch_*` helpers or manual cache-flushing; we rejected plain `models.Model` plus bespoke
caching. Reinventing the cache fights the idmapper instead of using it.

> Status: accepted · Source: sharedmemory-model skill
