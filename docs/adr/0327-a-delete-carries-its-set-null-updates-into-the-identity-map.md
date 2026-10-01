# 0327 — A delete carries its SET_NULL updates into the identity map

**Status:** accepted (2026-10-01, #4086)

Deleting a row whose referrers use `on_delete=SET_NULL` makes Django's `Collector` null
those links with one `UPDATE` through the referrer's plain `_base_manager`. That write
skips `ArxSharedMemoryQuerySet`'s guard and never loads the referring rows, so every
referrer already resident in the idmapper cache keeps the deleted row's id until the
process restarts. `refresh_from_db()` and a fresh `get()` hand back that same instance,
and a later `select_related` of the link sets the related object to `None` beside the
stale id. In production an admin delete of a house on 2026-09-29 left every cached
`Title` naming it, and both Almanach ladder endpoints raised on each read for two days
(Sentry ARX2-S, ARX2-T). There are 752 `SET_NULL` links in the codebase, and ADR-0326's
reviewed delete makes deleting an organization a routine staff act. **The ruling:**
`ArxSharedMemoryModel.delete()` and `ArxSharedMemoryQuerySet.delete()` run Django's own
delete with `core.deletion.IdentityMapCollector`, which records every row it removes,
cascades included, and afterwards nulls those ids on cached `SET_NULL` referrers: the
write the `Collector` would have made had they been in memory. Both overrides mirror
Django 5.2's bodies line for line, so a Django upgrade re-checks them. **Rejected:**
(a) guarding the read site (`t.house is not None` instead of `t.house_id`), which
fixes one endpoint and leaves every other reader of a stale id wrong; (b) a per-model
mixin on `Organization`, which leaves the other 751 links, and the referrers a cascade
reaches, still stale; (c) `flush_instance_cache()` on each referrer model after a
delete, which discards whole caches that other holders still reference instead of
correcting them; (d) a `post_delete` signal (ADR-0009); (e) making the base manager
guarded, which changes forward-FK access for every model to fix one write. Like Django
nulling a deleted instance's pk, the correction is not undone if an enclosing
transaction later rolls back. Related: ADR-0008 (SharedMemoryModel everywhere),
ADR-0326.
